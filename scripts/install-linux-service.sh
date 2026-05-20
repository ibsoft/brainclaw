#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-brainclaw}"
SERVICE_USER="${SERVICE_USER:-brainclaw}"
SERVICE_GROUP="${SERVICE_GROUP:-$SERVICE_USER}"
INSTALL_DIR="${INSTALL_DIR:-/opt/brainclaw}"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl is required." >&2
  exit 1
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "${PYTHON_BIN} is not installed. Set PYTHON_BIN=python3.11 if needed." >&2
  exit 1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! getent group "${SERVICE_GROUP}" >/dev/null; then
  groupadd --system "${SERVICE_GROUP}"
fi

if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --gid "${SERVICE_GROUP}" --home-dir "${INSTALL_DIR}" --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 "${INSTALL_DIR}"

rsync -a \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude "data/indexes" \
  --exclude "data/uploads" \
  "${SRC_DIR}/" "${INSTALL_DIR}/"

install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 "${INSTALL_DIR}/data"
install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 "${INSTALL_DIR}/data/indexes"
install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" -m 0750 "${INSTALL_DIR}/data/uploads"

if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
  cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
  memory_key="$("${PYTHON_BIN}" -c 'import secrets; print(secrets.token_urlsafe(32))')"
  session_secret="$("${PYTHON_BIN}" -c 'import secrets; print(secrets.token_urlsafe(32))')"
  sed -i "s/replace-with-a-long-random-local-key/${memory_key}/" "${INSTALL_DIR}/.env"
  sed -i "s/replace-with-a-long-random-session-secret/${session_secret}/" "${INSTALL_DIR}/.env"
fi

chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_DIR}"
chmod 0640 "${INSTALL_DIR}/.env"

sudo -u "${SERVICE_USER}" "${PYTHON_BIN}" -m venv "${INSTALL_DIR}/.venv"
sudo -u "${SERVICE_USER}" "${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip
sudo -u "${SERVICE_USER}" "${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

cp "${INSTALL_DIR}/brainclaw.service" "${UNIT_PATH}"
sed -i \
  -e "s#User=brainclaw#User=${SERVICE_USER}#" \
  -e "s#Group=brainclaw#Group=${SERVICE_GROUP}#" \
  -e "s#WorkingDirectory=/opt/brainclaw#WorkingDirectory=${INSTALL_DIR}#" \
  -e "s#EnvironmentFile=-/opt/brainclaw/.env#EnvironmentFile=-${INSTALL_DIR}/.env#" \
  -e "s#ExecStart=/opt/brainclaw/.venv/bin/uvicorn#ExecStart=${INSTALL_DIR}/.venv/bin/uvicorn#" \
  -e "s#ReadWritePaths=/opt/brainclaw/data#ReadWritePaths=${INSTALL_DIR}/data#" \
  -e "s#Documentation=file:/opt/brainclaw/README.md#Documentation=file:${INSTALL_DIR}/README.md#" \
  "${UNIT_PATH}"

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

echo "Installed and started ${SERVICE_NAME}."
echo "Admin UI: http://127.0.0.1:8757/admin"
echo "Check status: sudo systemctl status ${SERVICE_NAME}"
echo "Logs: sudo journalctl -u ${SERVICE_NAME} -f"
