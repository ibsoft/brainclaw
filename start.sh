#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env}"
ENV_EXAMPLE="${ROOT_DIR}/.env.example"

if [[ -t 1 ]]; then
  clear
fi

cd "${ROOT_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
  if [[ ! -f "${ENV_EXAMPLE}" ]]; then
    echo ".env is missing and .env.example was not found." >&2
    exit 1
  fi

  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  "${PYTHON_BIN}" - <<'PY'
from pathlib import Path
import secrets

env = Path(".env")
text = env.read_text()
text = text.replace("replace-with-a-long-random-local-key", secrets.token_urlsafe(32))
text = text.replace("replace-with-a-long-random-session-secret", secrets.token_urlsafe(32))
env.write_text(text)
PY
  chmod 0600 "${ENV_FILE}" 2>/dev/null || true
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

if [[ ! -x "${VENV_DIR}/bin/uvicorn" ]]; then
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip
  "${VENV_DIR}/bin/pip" install -r "${ROOT_DIR}/requirements.txt"
fi

set -a
source "${ENV_FILE}"
set +a

strip_cr() {
  tr -d '\r'
}

HOST="$(printf '%s' "${HOST:-127.0.0.1}" | strip_cr)"
PORT="$(printf '%s' "${PORT:-8757}" | strip_cr)"
BRAINCLAW_SSL_CERTFILE="$(printf '%s' "${BRAINCLAW_SSL_CERTFILE:-}" | strip_cr)"
BRAINCLAW_SSL_KEYFILE="$(printf '%s' "${BRAINCLAW_SSL_KEYFILE:-}" | strip_cr)"

ssl_args=()
if [[ -n "${BRAINCLAW_SSL_CERTFILE}" && -n "${BRAINCLAW_SSL_KEYFILE}" ]]; then
  ssl_args=(--ssl-certfile "${BRAINCLAW_SSL_CERTFILE}" --ssl-keyfile "${BRAINCLAW_SSL_KEYFILE}")
fi

exec "${VENV_DIR}/bin/uvicorn" app.main:app --host "${HOST}" --port "${PORT}" "${ssl_args[@]}" "$@"
