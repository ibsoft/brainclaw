#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${OPENCLAW_ENV_FILE:-/etc/openclaw/environment.conf}"

if [[ -e "${ENV_FILE}" && ! -r "${ENV_FILE}" ]]; then
  echo "BrainClaw environment config exists but is not readable: ${ENV_FILE}" >&2
  exit 1
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "${ENV_FILE}"
  set +a
fi

export BRAINCLAW_URL="${BRAINCLAW_URL:-http://127.0.0.1:8757}"
export BRAINCLAW_API_KEY="${BRAINCLAW_API_KEY:-${MEMORY_API_KEY:-}}"
export OPENCLAW_AGENT_ID="${OPENCLAW_AGENT_ID:-${AGENT_ID:-openclaw}}"
export OPENCLAW_WORKSPACE="${OPENCLAW_WORKSPACE:-${WORKSPACE:-default}}"
export OPENCLAW_SYSTEM_PROMPT="${OPENCLAW_SYSTEM_PROMPT:-/etc/openclaw/OpenClaw.md}"
export OPENCLAW_DEFAULTS_DIR="${OPENCLAW_DEFAULTS_DIR:-/etc/openclaw/defaults}"

# Export common aliases used by different launchers. OpenClaw must still be
# configured to consume at least one of these.
export OPENCLAW_PROMPT_FILE="${OPENCLAW_PROMPT_FILE:-${OPENCLAW_SYSTEM_PROMPT}}"
export OPENCLAW_INSTRUCTIONS_FILE="${OPENCLAW_INSTRUCTIONS_FILE:-${OPENCLAW_SYSTEM_PROMPT}}"
export SYSTEM_PROMPT_FILE="${SYSTEM_PROMPT_FILE:-${OPENCLAW_SYSTEM_PROMPT}}"
export OPENCLAW_AGENTS_FILE="${OPENCLAW_AGENTS_FILE:-${OPENCLAW_DEFAULTS_DIR}/AGENTS.md}"
export OPENCLAW_BOOTSTRAP_FILE="${OPENCLAW_BOOTSTRAP_FILE:-${OPENCLAW_DEFAULTS_DIR}/BOOTSTRAP.md}"

if [[ -z "${BRAINCLAW_API_KEY}" ]]; then
  echo "BRAINCLAW_API_KEY or MEMORY_API_KEY is missing." >&2
  exit 1
fi

if [[ ! -r "${OPENCLAW_SYSTEM_PROMPT}" ]]; then
  echo "OpenClaw system prompt is not readable: ${OPENCLAW_SYSTEM_PROMPT}" >&2
  exit 1
fi

if [[ ! -d "${OPENCLAW_DEFAULTS_DIR}" ]]; then
  echo "OpenClaw defaults directory is not readable: ${OPENCLAW_DEFAULTS_DIR}" >&2
  exit 1
fi

if [[ "$#" -eq 0 ]]; then
  cat >&2 <<EOF
Usage:
  openclaw-brainclaw <openclaw command> [args...]

Example:
  openclaw-brainclaw openclaw

Loaded:
  BRAINCLAW_URL=${BRAINCLAW_URL}
  OPENCLAW_AGENT_ID=${OPENCLAW_AGENT_ID}
  OPENCLAW_WORKSPACE=${OPENCLAW_WORKSPACE}
  OPENCLAW_SYSTEM_PROMPT=${OPENCLAW_SYSTEM_PROMPT}
  OPENCLAW_DEFAULTS_DIR=${OPENCLAW_DEFAULTS_DIR}
EOF
  exit 2
fi

exec "$@"
