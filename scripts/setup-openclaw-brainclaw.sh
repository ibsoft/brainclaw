#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_USER="${OPENCLAW_USER:-openclaw}"
OPENCLAW_GROUP="${OPENCLAW_GROUP:-$OPENCLAW_USER}"
OPENCLAW_HOME="${OPENCLAW_HOME:-/home/${OPENCLAW_USER}}"
OPENCLAW_INSTALL_DIR="${OPENCLAW_INSTALL_DIR:-${OPENCLAW_HOME}/.openclaw}"
OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX:-${OPENCLAW_INSTALL_DIR}/npm}"
OPENCLAW_WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-${OPENCLAW_HOME}/workspace}"
OPENCLAW_AGENT_ID="${OPENCLAW_AGENT_ID:-Kim}"
OPENCLAW_WORKSPACE="${OPENCLAW_WORKSPACE:-Kims-workspace}"

BRAINCLAW_REPO="${BRAINCLAW_REPO:-https://github.com/ibsoft/brainclaw.git}"
BRAINCLAW_DIR="${BRAINCLAW_DIR:-/opt/brainclaw}"
BRAINCLAW_SERVICE_NAME="${BRAINCLAW_SERVICE_NAME:-brainclaw}"
BRAINCLAW_PYTHON_BIN="${BRAINCLAW_PYTHON_BIN:-python3.12}"
BRAINCLAW_URL="${BRAINCLAW_URL:-http://127.0.0.1:8757}"

NODE_MAJOR="${NODE_MAJOR:-22}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if [[ -t 1 ]]; then
  BOLD="$(printf '\033[1m')"
  DIM="$(printf '\033[2m')"
  GREEN="$(printf '\033[32m')"
  BLUE="$(printf '\033[34m')"
  YELLOW="$(printf '\033[33m')"
  RED="$(printf '\033[31m')"
  RESET="$(printf '\033[0m')"
else
  BOLD=""; DIM=""; GREEN=""; BLUE=""; YELLOW=""; RED=""; RESET=""
fi

banner() {
  cat <<EOF
${BLUE}${BOLD}
╔══════════════════════════════════════════════════════════╗
║              OpenClaw + BrainClaw Setup                 ║
║        local gateway, memory service, systemd            ║
╚══════════════════════════════════════════════════════════╝
${RESET}
EOF
}

step() {
  printf '\n%s%s▶ %s%s\n' "${BLUE}" "${BOLD}" "$1" "${RESET}"
}

ok() {
  printf '%s✓%s %s\n' "${GREEN}" "${RESET}" "$1"
}

warn() {
  printf '%s!%s %s\n' "${YELLOW}" "${RESET}" "$1"
}

fail() {
  printf '%s✗%s %s\n' "${RED}" "${RESET}" "$1" >&2
  exit 1
}

spin_run() {
  local label="$1"
  shift
  local log_file
  log_file="$(mktemp)"
  printf '%s ' "${label}"
  "$@" >"${log_file}" 2>&1 &
  local pid=$!
  local frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  local i=0
  while kill -0 "${pid}" 2>/dev/null; do
    printf '\r%s %s' "${label}" "${frames:i++%${#frames}:1}"
    sleep 0.08
  done
  if wait "${pid}"; then
    printf '\r%s %s\n' "${label}" "${GREEN}done${RESET}"
    rm -f "${log_file}"
  else
    printf '\r%s %s\n' "${label}" "${RED}failed${RESET}"
    cat "${log_file}" >&2
    rm -f "${log_file}"
    exit 1
  fi
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

apt_install() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y "$@"
}

node_major() {
  if ! need_cmd node; then
    echo 0
    return
  fi
  node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || echo 0
}

install_nodejs() {
  local current
  current="$(node_major)"
  if (( current >= NODE_MAJOR )); then
    ok "Node.js $(node --version) already installed"
    return
  fi
  step "Installing Node.js ${NODE_MAJOR}.x"
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
  apt-get install -y nodejs
  ok "Node.js $(node --version) installed"
}

read_password() {
  local pw1 pw2
  while true; do
    read -r -s -p "Set Linux password for ${OPENCLAW_USER}: " pw1
    printf '\n'
    read -r -s -p "Confirm password: " pw2
    printf '\n'
    if [[ -z "${pw1}" ]]; then
      warn "Password cannot be empty."
    elif [[ "${pw1}" != "${pw2}" ]]; then
      warn "Passwords do not match."
    else
      printf '%s' "${pw1}"
      return
    fi
  done
}

create_openclaw_user() {
  step "Preparing Linux user ${OPENCLAW_USER}"
  if ! getent group "${OPENCLAW_GROUP}" >/dev/null; then
    groupadd "${OPENCLAW_GROUP}"
  fi
  if ! id -u "${OPENCLAW_USER}" >/dev/null 2>&1; then
    useradd --create-home --home-dir "${OPENCLAW_HOME}" --gid "${OPENCLAW_GROUP}" --shell /bin/bash "${OPENCLAW_USER}"
    ok "Created user ${OPENCLAW_USER}"
  else
    ok "User ${OPENCLAW_USER} already exists"
  fi
  local password
  password="$(read_password)"
  printf '%s:%s\n' "${OPENCLAW_USER}" "${password}" | chpasswd
  install -d -o "${OPENCLAW_USER}" -g "${OPENCLAW_GROUP}" -m 0750 "${OPENCLAW_INSTALL_DIR}"
  install -d -o "${OPENCLAW_USER}" -g "${OPENCLAW_GROUP}" -m 0750 "${OPENCLAW_NPM_PREFIX}"
  install -d -o "${OPENCLAW_USER}" -g "${OPENCLAW_GROUP}" -m 0750 "${OPENCLAW_NPM_PREFIX}/bin"
  install -d -o "${OPENCLAW_USER}" -g "${OPENCLAW_GROUP}" -m 0750 "${OPENCLAW_WORKSPACE_DIR}"
}

install_dependencies() {
  step "Installing OS dependencies"
  if ! need_cmd apt-get; then
    fail "This automatic setup currently supports Debian/Ubuntu systems with apt-get."
  fi
  spin_run "Installing packages" apt_install \
    ca-certificates curl gnupg git rsync sudo systemd \
    build-essential pkg-config \
    python3 python3-venv python3-pip python3-dev python3.12 python3.12-venv
  install_nodejs
}

install_openclaw() {
  step "Installing latest OpenClaw for ${OPENCLAW_USER}"
  sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc 'mkdir -p "$OPENCLAW_NPM_PREFIX/bin"'
  sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc 'npm config set prefix "$OPENCLAW_NPM_PREFIX"'
  spin_run "npm install openclaw@latest" sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc 'export PATH="$OPENCLAW_NPM_PREFIX/bin:$PATH"; npm install -g --prefix "$OPENCLAW_NPM_PREFIX" openclaw@latest'
  if ! sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc 'export PATH="$OPENCLAW_NPM_PREFIX/bin:$PATH"; command -v openclaw >/dev/null'; then
    fail "OpenClaw installed but is not discoverable for ${OPENCLAW_USER}."
  fi
  ok "OpenClaw installed under ${OPENCLAW_NPM_PREFIX}"
}

setup_openclaw_gateway() {
  step "Setting up OpenClaw gateway service"
  loginctl enable-linger "${OPENCLAW_USER}" || warn "Could not enable linger; user service may require login."
  if sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc 'export PATH="$OPENCLAW_NPM_PREFIX/bin:$PATH"; openclaw gateway install'; then
    ok "OpenClaw gateway installer completed"
  else
    warn "openclaw gateway install failed. Trying direct systemd user enable."
  fi
  sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc 'export PATH="$OPENCLAW_NPM_PREFIX/bin:$PATH"; openclaw gateway status' || warn "Gateway status check failed; run: sudo -iu '"${OPENCLAW_USER}"' ${OPENCLAW_NPM_PREFIX}/bin/openclaw gateway status"
}

checkout_brainclaw() {
  step "Checking out BrainClaw"
  if [[ -d "${BRAINCLAW_DIR}/.git" ]]; then
    spin_run "Updating ${BRAINCLAW_DIR}" git -C "${BRAINCLAW_DIR}" pull --ff-only
  else
    rm -rf "${BRAINCLAW_DIR}"
    spin_run "Cloning ${BRAINCLAW_REPO}" git clone "${BRAINCLAW_REPO}" "${BRAINCLAW_DIR}"
  fi
}

install_brainclaw_service() {
  step "Installing BrainClaw service"
  spin_run "Running BrainClaw service installer" env \
    SERVICE_NAME="${BRAINCLAW_SERVICE_NAME}" \
    INSTALL_DIR="${BRAINCLAW_DIR}" \
    PYTHON_BIN="${BRAINCLAW_PYTHON_BIN}" \
    bash "${BRAINCLAW_DIR}/scripts/install-linux-service.sh"
  ok "BrainClaw service installed"
}

install_prompt_integration() {
  step "Installing OpenClaw BrainClaw prompt integration"
  local memory_key
  memory_key="$(sed -n 's/^MEMORY_API_KEY=//p' "${BRAINCLAW_DIR}/.env" | head -n 1)"
  if [[ -z "${memory_key}" ]]; then
    fail "Could not read MEMORY_API_KEY from ${BRAINCLAW_DIR}/.env"
  fi
  spin_run "Installing prompt/default files" env \
    BRAINCLAW_URL="${BRAINCLAW_URL}" \
    BRAINCLAW_API_KEY="${memory_key}" \
    OPENCLAW_AGENT_ID="${OPENCLAW_AGENT_ID}" \
    OPENCLAW_WORKSPACE="${OPENCLAW_WORKSPACE}" \
    OPENCLAW_WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR}" \
    OPENCLAW_WORKSPACE_UID="$(id -u "${OPENCLAW_USER}")" \
    OPENCLAW_WORKSPACE_GID="$(id -g "${OPENCLAW_USER}")" \
    bash "${BRAINCLAW_DIR}/scripts/install-openclaw-prompt.sh"

  if grep -q '^BRAINCLAW_API_KEY=replace-with-brainclaw-api-key' /etc/openclaw/environment.conf; then
    sed -i "s#^BRAINCLAW_API_KEY=.*#BRAINCLAW_API_KEY=${memory_key}#" /etc/openclaw/environment.conf
  elif ! grep -q '^BRAINCLAW_API_KEY=' /etc/openclaw/environment.conf; then
    printf '\nBRAINCLAW_API_KEY=%s\n' "${memory_key}" >> /etc/openclaw/environment.conf
  fi
  chown root:"${OPENCLAW_GROUP}" /etc/openclaw/environment.conf || true
  chmod 0640 /etc/openclaw/environment.conf
}

print_summary() {
  cat <<EOF

${GREEN}${BOLD}Setup complete.${RESET}

OpenClaw user:
  ${OPENCLAW_USER}

OpenClaw workspace:
  ${OPENCLAW_WORKSPACE_DIR}

OpenClaw npm prefix:
  ${OPENCLAW_NPM_PREFIX}

BrainClaw:
  ${BRAINCLAW_DIR}
  ${BRAINCLAW_URL}/admin

Services:
  sudo systemctl status ${BRAINCLAW_SERVICE_NAME}
  sudo -iu ${OPENCLAW_USER} ${OPENCLAW_NPM_PREFIX}/bin/openclaw gateway status

Start OpenClaw with BrainClaw environment:
  sudo -iu ${OPENCLAW_USER}
  openclaw-brainclaw ${OPENCLAW_NPM_PREFIX}/bin/openclaw

${YELLOW}Next:${RESET}
  Open ${BRAINCLAW_URL}/admin and complete first-run admin setup if needed.
EOF
}

banner
warn "This script installs packages, creates a Linux user, clones repositories, and enables services."
read -r -p "Continue? [y/N] " confirm
if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
  fail "Cancelled."
fi

install_dependencies
create_openclaw_user
install_openclaw
checkout_brainclaw
install_brainclaw_service
install_prompt_integration
setup_openclaw_gateway
print_summary
