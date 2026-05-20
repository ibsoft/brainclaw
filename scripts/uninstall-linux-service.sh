#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-brainclaw}"
SERVICE_USER="${SERVICE_USER:-brainclaw}"
INSTALL_DIR="${INSTALL_DIR:-/opt/brainclaw}"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
REMOVE_DATA="${REMOVE_DATA:-false}"
REMOVE_USER="${REMOVE_USER:-false}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
  systemctl disable "${SERVICE_NAME}" 2>/dev/null || true
fi

rm -f "${UNIT_PATH}"

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl reset-failed "${SERVICE_NAME}" 2>/dev/null || true
fi

if [[ "${REMOVE_DATA}" == "true" ]]; then
  rm -rf "${INSTALL_DIR}"
  echo "Removed ${INSTALL_DIR}."
else
  echo "Kept ${INSTALL_DIR}. Set REMOVE_DATA=true to remove installed files and memory data."
fi

if [[ "${REMOVE_USER}" == "true" ]]; then
  userdel "${SERVICE_USER}" 2>/dev/null || true
  echo "Removed user ${SERVICE_USER} if it existed."
else
  echo "Kept user ${SERVICE_USER}. Set REMOVE_USER=true to remove it."
fi

echo "Uninstalled ${SERVICE_NAME} service."
