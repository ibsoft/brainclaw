#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_DIR="${OPENCLAW_DIR:-/etc/openclaw}"
PROMPT_TARGET="${PROMPT_TARGET:-${OPENCLAW_DIR}/OpenClaw.md}"
ENV_TARGET="${ENV_TARGET:-${OPENCLAW_DIR}/environment.conf}"
DEFAULTS_TARGET="${OPENCLAW_DEFAULTS_DIR:-${OPENCLAW_DIR}/defaults}"
strip_cr() {
  tr -d '\r'
}

BRAINCLAW_URL_VALUE="$(printf '%s' "${BRAINCLAW_URL:-http://127.0.0.1:8757}" | strip_cr)"
OPENCLAW_AGENT_ID_VALUE="$(printf '%s' "${OPENCLAW_AGENT_ID:-Kim}" | strip_cr)"
OPENCLAW_WORKSPACE_VALUE="$(printf '%s' "${OPENCLAW_WORKSPACE:-Kims-workspace}" | strip_cr)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPENCLAW_SOURCE_DIR="${OPENCLAW_SOURCE_DIR:-${SRC_DIR}/openclaw}"
WORKSPACE_TARGET="${OPENCLAW_WORKSPACE_DIR:-${SRC_DIR}}"
WORKSPACE_OWNER_UID="${OPENCLAW_WORKSPACE_UID:-${SUDO_UID:-}}"
WORKSPACE_OWNER_GID="${OPENCLAW_WORKSPACE_GID:-${SUDO_GID:-}}"
OPENCLAW_DEFAULT_FILES=(
  AGENTS.md
  BOOTSTRAP.md
  HEARTBEAT.md
  IDENTITY.md
  MEMORY.md
  SOUL.md
  TOOLS.md
  USER.md
)
if [[ ! -f "${OPENCLAW_SOURCE_DIR}/OpenClaw.md" ]]; then
  echo "OpenClaw source files not found: ${OPENCLAW_SOURCE_DIR}" >&2
  exit 1
fi

install_if_different() {
  local src="$1"
  local dst="$2"

  if [[ "$(realpath -m "${src}")" == "$(realpath -m "${dst}")" ]]; then
    return 0
  fi

  install -m 0644 "${src}" "${dst}"
}

render_openclaw_file() {
  local src="$1"
  local dst="$2"
  local tmp

  tmp="$(mktemp)"
  python3 - "${src}" "${tmp}" "${BRAINCLAW_URL_VALUE}" <<'PY'
from pathlib import Path
import sys

src, dst, brainclaw_url = sys.argv[1:4]
text = Path(src).read_text(encoding="utf-8")
text = text.replace("http://127.0.0.1:8757", brainclaw_url)
Path(dst).write_text(text, encoding="utf-8")
PY
  install -m 0644 "${tmp}" "${dst}"
  rm -f "${tmp}"
}

render_if_different() {
  local src="$1"
  local dst="$2"

  if [[ "$(realpath -m "${src}")" == "$(realpath -m "${dst}")" ]]; then
    return 0
  fi

  render_openclaw_file "${src}" "${dst}"
}

set_env_value() {
  local key="$1"
  local value="$2"
  local escaped

  escaped="$(printf '%s' "${value}" | sed 's/[\/&]/\\&/g')"
  if grep -q "^${key}=" "${ENV_TARGET}"; then
    sed -i "s/^${key}=.*/${key}=${escaped}/" "${ENV_TARGET}"
  else
    printf '%s=%s\n' "${key}" "${value}" >> "${ENV_TARGET}"
  fi
}

install -d -m 0755 "${OPENCLAW_DIR}"
install -d -m 0755 "${DEFAULTS_TARGET}"
render_openclaw_file "${OPENCLAW_SOURCE_DIR}/OpenClaw.md" "${PROMPT_TARGET}"
install -m 0755 "${SRC_DIR}/scripts/openclaw-brainclaw-wrapper.sh" /usr/local/bin/openclaw-brainclaw

for file in "${OPENCLAW_DEFAULT_FILES[@]}"; do
  render_openclaw_file "${OPENCLAW_SOURCE_DIR}/${file}" "${DEFAULTS_TARGET}/${file}"
done

if [[ -n "${WORKSPACE_TARGET}" ]]; then
  install -d -m 0755 "${WORKSPACE_TARGET}"
  render_if_different "${OPENCLAW_SOURCE_DIR}/OpenClaw.md" "${WORKSPACE_TARGET}/OpenClaw.md"
  for file in "${OPENCLAW_DEFAULT_FILES[@]}"; do
    render_if_different "${OPENCLAW_SOURCE_DIR}/${file}" "${WORKSPACE_TARGET}/${file}"
  done
  if [[ -n "${WORKSPACE_OWNER_UID}" && -n "${WORKSPACE_OWNER_GID}" ]]; then
    chown_targets=("${WORKSPACE_TARGET}/OpenClaw.md")
    for file in "${OPENCLAW_DEFAULT_FILES[@]}"; do
      if [[ -f "${WORKSPACE_TARGET}/${file}" ]]; then
        chown_targets+=("${WORKSPACE_TARGET}/${file}")
      fi
    done
    chown "${WORKSPACE_OWNER_UID}:${WORKSPACE_OWNER_GID}" "${chown_targets[@]}"
  fi
fi

if [[ ! -f "${ENV_TARGET}" ]]; then
  cat > "${ENV_TARGET}" <<EOF
BRAINCLAW_URL=${BRAINCLAW_URL_VALUE}
BRAINCLAW_API_KEY=replace-with-brainclaw-api-key
OPENCLAW_AGENT_ID=${OPENCLAW_AGENT_ID_VALUE}
OPENCLAW_WORKSPACE=${OPENCLAW_WORKSPACE_VALUE}
OPENCLAW_SYSTEM_PROMPT=${PROMPT_TARGET}
OPENCLAW_DEFAULTS_DIR=${DEFAULTS_TARGET}
OPENCLAW_WORKSPACE_DIR=${WORKSPACE_TARGET}
EOF
  chmod 0640 "${ENV_TARGET}"
else
  set_env_value "BRAINCLAW_URL" "${BRAINCLAW_URL_VALUE}"
  set_env_value "OPENCLAW_AGENT_ID" "${OPENCLAW_AGENT_ID_VALUE}"
  set_env_value "OPENCLAW_WORKSPACE" "${OPENCLAW_WORKSPACE_VALUE}"
  set_env_value "OPENCLAW_SYSTEM_PROMPT" "${PROMPT_TARGET}"
  set_env_value "OPENCLAW_DEFAULTS_DIR" "${DEFAULTS_TARGET}"
  set_env_value "OPENCLAW_WORKSPACE_DIR" "${WORKSPACE_TARGET}"
fi

echo "Installed OpenClaw prompt: ${PROMPT_TARGET}"
echo "Installed OpenClaw defaults: ${DEFAULTS_TARGET}"
echo "OpenClaw source files: ${OPENCLAW_SOURCE_DIR}"
echo "Injected OpenClaw workspace files: ${WORKSPACE_TARGET}"
echo "Installed wrapper: /usr/local/bin/openclaw-brainclaw"
echo "Environment config: ${ENV_TARGET}"
echo "BrainClaw URL: ${BRAINCLAW_URL_VALUE}"
echo
echo "Edit ${ENV_TARGET} and set BRAINCLAW_API_KEY."
echo "Start OpenClaw through the wrapper, for example: openclaw-brainclaw <your-openclaw-command>"
echo "Also configure OpenClaw to load OPENCLAW_SYSTEM_PROMPT and the workspace default files on every session, including after /new."
