#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_DIR="${OPENCLAW_DIR:-/etc/openclaw}"
PROMPT_TARGET="${PROMPT_TARGET:-${OPENCLAW_DIR}/OpenClaw.md}"
ENV_TARGET="${ENV_TARGET:-${OPENCLAW_DIR}/environment.conf}"
DEFAULTS_TARGET="${OPENCLAW_DEFAULTS_DIR:-${OPENCLAW_DIR}/defaults}"
BRAINCLAW_URL_VALUE="${BRAINCLAW_URL:-http://127.0.0.1:8757}"
OPENCLAW_AGENT_ID_VALUE="${OPENCLAW_AGENT_ID:-Kim}"
OPENCLAW_WORKSPACE_VALUE="${OPENCLAW_WORKSPACE:-Kims-workspace}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

install_if_different() {
  local src="$1"
  local dst="$2"

  if [[ "$(realpath -m "${src}")" == "$(realpath -m "${dst}")" ]]; then
    return 0
  fi

  install -m 0644 "${src}" "${dst}"
}

install -d -m 0755 "${OPENCLAW_DIR}"
install -d -m 0755 "${DEFAULTS_TARGET}"
install -m 0644 "${SRC_DIR}/OpenClaw.md" "${PROMPT_TARGET}"
install -m 0755 "${SRC_DIR}/scripts/openclaw-brainclaw-wrapper.sh" /usr/local/bin/openclaw-brainclaw

for file in "${OPENCLAW_DEFAULT_FILES[@]}"; do
  install -m 0644 "${SRC_DIR}/${file}" "${DEFAULTS_TARGET}/${file}"
done

if [[ -n "${WORKSPACE_TARGET}" ]]; then
  install -d -m 0755 "${WORKSPACE_TARGET}"
  install_if_different "${SRC_DIR}/OpenClaw.md" "${WORKSPACE_TARGET}/OpenClaw.md"
  for file in "${OPENCLAW_DEFAULT_FILES[@]}"; do
    install_if_different "${SRC_DIR}/${file}" "${WORKSPACE_TARGET}/${file}"
  done
  if [[ -n "${WORKSPACE_OWNER_UID}" && -n "${WORKSPACE_OWNER_GID}" ]]; then
    chown "${WORKSPACE_OWNER_UID}:${WORKSPACE_OWNER_GID}" \
      "${WORKSPACE_TARGET}/OpenClaw.md" \
      "${WORKSPACE_TARGET}/AGENTS.md" \
      "${WORKSPACE_TARGET}/BOOTSTRAP.md" \
      "${WORKSPACE_TARGET}/HEARTBEAT.md" \
      "${WORKSPACE_TARGET}/IDENTITY.md" \
      "${WORKSPACE_TARGET}/MEMORY.md" \
      "${WORKSPACE_TARGET}/SOUL.md" \
      "${WORKSPACE_TARGET}/TOOLS.md" \
      "${WORKSPACE_TARGET}/USER.md"
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
  if ! grep -q '^OPENCLAW_SYSTEM_PROMPT=' "${ENV_TARGET}"; then
    printf '\nOPENCLAW_SYSTEM_PROMPT=%s\n' "${PROMPT_TARGET}" >> "${ENV_TARGET}"
  fi
  if ! grep -q '^OPENCLAW_DEFAULTS_DIR=' "${ENV_TARGET}"; then
    printf '\nOPENCLAW_DEFAULTS_DIR=%s\n' "${DEFAULTS_TARGET}" >> "${ENV_TARGET}"
  fi
  if ! grep -q '^OPENCLAW_WORKSPACE_DIR=' "${ENV_TARGET}"; then
    printf '\nOPENCLAW_WORKSPACE_DIR=%s\n' "${WORKSPACE_TARGET}" >> "${ENV_TARGET}"
  fi
fi

echo "Installed OpenClaw prompt: ${PROMPT_TARGET}"
echo "Installed OpenClaw defaults: ${DEFAULTS_TARGET}"
echo "Injected OpenClaw workspace files: ${WORKSPACE_TARGET}"
echo "Installed wrapper: /usr/local/bin/openclaw-brainclaw"
echo "Environment config: ${ENV_TARGET}"
echo
echo "Edit ${ENV_TARGET} and set BRAINCLAW_API_KEY."
echo "Start OpenClaw through the wrapper, for example: openclaw-brainclaw <your-openclaw-command>"
echo "Also configure OpenClaw to load OPENCLAW_SYSTEM_PROMPT and the workspace default files on every session, including after /new."
