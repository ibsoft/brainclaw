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
BRAINCLAW_PYTHON_BIN="${BRAINCLAW_PYTHON_BIN:-python3}"
BRAINCLAW_URL="${BRAINCLAW_URL:-http://127.0.0.1:8757}"
BRAINCLAW_PORT="${BRAINCLAW_PORT:-8757}"

NODE_MAJOR="${NODE_MAJOR:-22}"
ASSUME_YES="${ASSUME_YES:-0}"
SKIP_OPENCLAW_GATEWAY="${SKIP_OPENCLAW_GATEWAY:-0}"

export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-180}"
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo $0" >&2
  exit 1
fi

if [[ -t 1 ]]; then
  BOLD="$(printf '\033[1m')"
  GREEN="$(printf '\033[32m')"
  BLUE="$(printf '\033[34m')"
  YELLOW="$(printf '\033[33m')"
  RED="$(printf '\033[31m')"
  RESET="$(printf '\033[0m')"
else
  BOLD=""
  GREEN=""
  BLUE=""
  YELLOW=""
  RED=""
  RESET=""
fi

banner() {
  cat <<EOF
${BLUE}${BOLD}
╔══════════════════════════════════════════════════════════╗
║              OpenClaw + BrainClaw Setup                  ║
║              Ioannis (Yannis) A. Bouhras                 ║
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

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

installed_pkg() {
  dpkg -s "$1" >/dev/null 2>&1
}

version_ge() {
  printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

install_missing_packages() {
  local missing=()

  for pkg in "$@"; do
    if ! installed_pkg "$pkg"; then
      missing+=("$pkg")
    fi
  done

  if (( ${#missing[@]} == 0 )); then
    ok "Required packages already installed"
    return 0
  fi

  export DEBIAN_FRONTEND=noninteractive

  step "Installing missing packages"
  apt-get update
  apt-get install -y "${missing[@]}"
}

detect_python() {
  local candidates=(
    "${BRAINCLAW_PYTHON_BIN}"
    python3.13
    python3
  )

  local py
  local ver

  for py in "${candidates[@]}"; do
    [[ -z "${py}" ]] && continue

    if need_cmd "${py}"; then
      ver="$("${py}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"

      if [[ -n "${ver}" ]] && version_ge "${ver}" "3.12"; then
        BRAINCLAW_PYTHON_BIN="${py}"
        ok "Using Python ${ver}: $(command -v "${py}")"
        return 0
      fi
    fi
  done

  fail "Python >= 3.12 is required. On Kali rolling, python3 should usually be Python 3.13."
}

python_minor() {
  "${BRAINCLAW_PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
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
    return 0
  fi

  step "Installing Node.js ${NODE_MAJOR}.x"

  install_missing_packages ca-certificates curl gnupg

  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
  apt-get install -y nodejs

  current="$(node_major)"

  if (( current < NODE_MAJOR )); then
    fail "Node.js installation failed or installed version is lower than ${NODE_MAJOR}."
  fi

  ok "Node.js $(node --version) installed"
}

install_dependencies() {
  step "Checking OS dependencies"

  if ! need_cmd apt-get; then
    fail "This installer supports Debian, Ubuntu, and Kali systems with apt-get."
  fi

  install_missing_packages \
    ca-certificates \
    curl \
    gnupg \
    git \
    rsync \
    sudo \
    systemd \
    build-essential \
    pkg-config \
    libsqlite3-dev \
    libffi-dev \
    libssl-dev \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev

  detect_python
  install_nodejs
}

read_password_from_tty() {
  local pw1
  local pw2

  if [[ -n "${OPENCLAW_PASSWORD:-}" ]]; then
    printf '%s' "${OPENCLAW_PASSWORD}"
    return 0
  fi

  if [[ ! -r /dev/tty || ! -w /dev/tty ]]; then
    warn "No interactive TTY detected. Skipping Linux password setup for ${OPENCLAW_USER}."
    warn "Set it later with: sudo passwd ${OPENCLAW_USER}"
    return 1
  fi

  while true; do
    read -r -s -p "Set Linux password for ${OPENCLAW_USER}, or leave empty to skip: " pw1 < /dev/tty
    printf '\n' > /dev/tty

    if [[ -z "${pw1}" ]]; then
      warn "Skipping Linux password setup for ${OPENCLAW_USER}."
      return 1
    fi

    read -r -s -p "Confirm password: " pw2 < /dev/tty
    printf '\n' > /dev/tty

    if [[ "${pw1}" != "${pw2}" ]]; then
      warn "Passwords do not match."
      continue
    fi

    printf '%s' "${pw1}"
    return 0
  done
}

set_openclaw_password_if_supplied() {
  local password

  if ! password="$(read_password_from_tty)"; then
    return 0
  fi

  if [[ -z "${password}" ]]; then
    return 0
  fi

  if ! printf '%s:%s\n' "${OPENCLAW_USER}" "${password}" | chpasswd; then
    warn "Password change failed through chpasswd."
    passwd -S "${OPENCLAW_USER}" || true
    passwd -u "${OPENCLAW_USER}" >/dev/null 2>&1 || true

    if ! printf '%s:%s\n' "${OPENCLAW_USER}" "${password}" | chpasswd; then
      fail "Could not set password for ${OPENCLAW_USER}. Run manually: sudo passwd ${OPENCLAW_USER}"
    fi
  fi

  ok "Linux password configured for ${OPENCLAW_USER}"
}

create_openclaw_user() {
  step "Preparing Linux user ${OPENCLAW_USER}"

  if ! getent group "${OPENCLAW_GROUP}" >/dev/null; then
    groupadd "${OPENCLAW_GROUP}"
    ok "Created group ${OPENCLAW_GROUP}"
  else
    ok "Group ${OPENCLAW_GROUP} already exists"
  fi

  if ! id -u "${OPENCLAW_USER}" >/dev/null 2>&1; then
    useradd \
      --create-home \
      --home-dir "${OPENCLAW_HOME}" \
      --gid "${OPENCLAW_GROUP}" \
      --shell /bin/bash \
      "${OPENCLAW_USER}"

    ok "Created user ${OPENCLAW_USER}"
  else
    ok "User ${OPENCLAW_USER} already exists"
  fi

  if getent group sudo >/dev/null 2>&1; then
    usermod -aG sudo "${OPENCLAW_USER}" || warn "Could not add ${OPENCLAW_USER} to sudo group"
  fi

  set_openclaw_password_if_supplied

  install -d -o "${OPENCLAW_USER}" -g "${OPENCLAW_GROUP}" -m 0750 "${OPENCLAW_INSTALL_DIR}"
  install -d -o "${OPENCLAW_USER}" -g "${OPENCLAW_GROUP}" -m 0750 "${OPENCLAW_NPM_PREFIX}"
  install -d -o "${OPENCLAW_USER}" -g "${OPENCLAW_GROUP}" -m 0750 "${OPENCLAW_NPM_PREFIX}/bin"
  install -d -o "${OPENCLAW_USER}" -g "${OPENCLAW_GROUP}" -m 0750 "${OPENCLAW_WORKSPACE_DIR}"

  ok "OpenClaw directories prepared"
}

install_openclaw() {
  step "Installing latest OpenClaw for ${OPENCLAW_USER}"

  if ! need_cmd npm; then
    fail "npm was not found after Node.js installation."
  fi

  sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc '
    mkdir -p "$OPENCLAW_NPM_PREFIX/bin"
    npm config set prefix "$OPENCLAW_NPM_PREFIX"
  '

  if sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc '
    export PATH="$OPENCLAW_NPM_PREFIX/bin:$PATH"
    command -v openclaw >/dev/null 2>&1
  '; then
    ok "OpenClaw already installed for ${OPENCLAW_USER}"
  else
    step "Installing OpenClaw npm package"

    sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc '
      export PATH="$OPENCLAW_NPM_PREFIX/bin:$PATH"
      npm install -g --prefix "$OPENCLAW_NPM_PREFIX" openclaw@latest
    '
  fi

  if ! sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc '
    export PATH="$OPENCLAW_NPM_PREFIX/bin:$PATH"
    command -v openclaw >/dev/null 2>&1
  '; then
    fail "OpenClaw installed but is not discoverable for ${OPENCLAW_USER}."
  fi

  ok "OpenClaw available under ${OPENCLAW_NPM_PREFIX}"
}

checkout_brainclaw() {
  step "Checking out BrainClaw"

  if [[ -d "${BRAINCLAW_DIR}/.git" ]]; then
    git -C "${BRAINCLAW_DIR}" pull --ff-only || warn "Git pull failed. Continuing with existing BrainClaw directory."
  else
    rm -rf "${BRAINCLAW_DIR}"
    git clone "${BRAINCLAW_REPO}" "${BRAINCLAW_DIR}"
  fi

  if [[ ! -d "${BRAINCLAW_DIR}" ]]; then
    fail "BrainClaw directory was not created: ${BRAINCLAW_DIR}"
  fi
}

patch_brainclaw_requirements_for_py313() {
  step "Patching BrainClaw requirements for Python 3.13"

  local req="${BRAINCLAW_DIR}/requirements.txt"

  if [[ ! -f "${req}" ]]; then
    warn "requirements.txt not found. Creating minimal fallback requirements.txt."
    cat > "${req}" <<'EOF'
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.9.0
python-dotenv>=1.0.1
requests>=2.32.0
numpy>=2.1.0
faiss-cpu>=1.10.0
sentence-transformers>=3.3.0
transformers>=4.46.0
torch>=2.6.0
pypdf>=5.0.0
python-docx>=1.1.2
pandas>=2.2.3
EOF
    return 0
  fi

  cp -a "${req}" "${req}.bak.$(date +%Y%m%d-%H%M%S)"

  sed -i \
    -e 's/^faiss-cpu==.*/faiss-cpu>=1.10.0/' \
    -e 's/^numpy==.*/numpy>=2.1.0/' \
    -e 's/^scipy==.*/scipy>=1.14.0/' \
    -e 's/^scikit-learn==.*/scikit-learn>=1.5.0/' \
    -e 's/^pandas==.*/pandas>=2.2.3/' \
    -e 's/^pydantic==.*/pydantic>=2.9.0/' \
    -e 's/^fastapi==.*/fastapi>=0.115.0/' \
    -e 's/^uvicorn==.*/uvicorn>=0.30.0/' \
    -e 's/^sentence-transformers==.*/sentence-transformers>=3.3.0/' \
    -e 's/^transformers==.*/transformers>=4.46.0/' \
    -e 's/^torch==.*/torch>=2.6.0/' \
    -e 's/^python-dotenv==.*/python-dotenv>=1.0.1/' \
    -e 's/^requests==.*/requests>=2.32.0/' \
    -e 's/^pypdf==.*/pypdf>=5.0.0/' \
    -e 's/^python-docx==.*/python-docx>=1.1.2/' \
    "${req}"

  ok "requirements.txt patched. Backup created."
}

create_brainclaw_env_if_missing() {
  step "Ensuring BrainClaw .env exists"

  local env_file="${BRAINCLAW_DIR}/.env"

  if [[ -f "${env_file}" ]]; then
    ok "BrainClaw .env already exists"
    return 0
  fi

  local memory_key
  memory_key="$(openssl rand -hex 32 2>/dev/null || python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"

  cat > "${env_file}" <<EOF
MEMORY_API_KEY=${memory_key}
HOST=127.0.0.1
PORT=${BRAINCLAW_PORT}
DATABASE_PATH=${BRAINCLAW_DIR}/data/brainclaw.sqlite3
DATA_DIR=${BRAINCLAW_DIR}/data
EOF

  chmod 0640 "${env_file}"
  chown "${BRAINCLAW_SERVICE_NAME}:${BRAINCLAW_SERVICE_NAME}" "${env_file}" 2>/dev/null || true

  ok "BrainClaw .env created"
}

find_brainclaw_app() {
  local candidates=(
    "app.main:app"
    "main:app"
    "brainclaw.main:app"
    "brainclaw.app:app"
    "server.main:app"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    local module="${candidate%%:*}"
    if sudo -u "${BRAINCLAW_SERVICE_NAME}" -H bash -lc "cd '${BRAINCLAW_DIR}' && source .venv/bin/activate && python - <<PY
import importlib
try:
    importlib.import_module('${module}')
    print('OK')
except Exception:
    raise
PY" >/dev/null 2>&1; then
      printf '%s' "${candidate}"
      return 0
    fi
  done

  printf 'main:app'
  return 0
}

manual_brainclaw_install() {
  step "Manual BrainClaw installation fallback"

  if ! id -u "${BRAINCLAW_SERVICE_NAME}" >/dev/null 2>&1; then
    useradd --system --home-dir "${BRAINCLAW_DIR}" --shell /usr/sbin/nologin "${BRAINCLAW_SERVICE_NAME}" || true
  fi

  install -d -o "${BRAINCLAW_SERVICE_NAME}" -g "${BRAINCLAW_SERVICE_NAME}" -m 0750 "${BRAINCLAW_DIR}"
  install -d -o "${BRAINCLAW_SERVICE_NAME}" -g "${BRAINCLAW_SERVICE_NAME}" -m 0750 "${BRAINCLAW_DIR}/data"

  chown -R "${BRAINCLAW_SERVICE_NAME}:${BRAINCLAW_SERVICE_NAME}" "${BRAINCLAW_DIR}"

  sudo -u "${BRAINCLAW_SERVICE_NAME}" -H "${BRAINCLAW_PYTHON_BIN}" -m venv "${BRAINCLAW_DIR}/.venv"

  sudo -u "${BRAINCLAW_SERVICE_NAME}" -H "${BRAINCLAW_DIR}/.venv/bin/python" -m pip install --upgrade pip setuptools wheel

  sudo -u "${BRAINCLAW_SERVICE_NAME}" -H env \
    PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT}" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1 \
    "${BRAINCLAW_DIR}/.venv/bin/pip" install --prefer-binary -r "${BRAINCLAW_DIR}/requirements.txt"

  create_brainclaw_env_if_missing

  local app_target
  app_target="$(find_brainclaw_app)"

  step "Creating systemd service for BrainClaw using ${app_target}"

  cat > "/etc/systemd/system/${BRAINCLAW_SERVICE_NAME}.service" <<EOF
[Unit]
Description=BrainClaw local memory service
After=network.target

[Service]
Type=simple
User=${BRAINCLAW_SERVICE_NAME}
Group=${BRAINCLAW_SERVICE_NAME}
WorkingDirectory=${BRAINCLAW_DIR}
EnvironmentFile=${BRAINCLAW_DIR}/.env
ExecStart=${BRAINCLAW_DIR}/.venv/bin/uvicorn ${app_target} --host 127.0.0.1 --port ${BRAINCLAW_PORT}
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=false
ReadWritePaths=${BRAINCLAW_DIR}

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable "${BRAINCLAW_SERVICE_NAME}"
  systemctl restart "${BRAINCLAW_SERVICE_NAME}"

  ok "Manual BrainClaw service installation completed"
}

install_brainclaw_service() {
  step "Installing BrainClaw service"

  local installer="${BRAINCLAW_DIR}/scripts/install-linux-service.sh"

  step "Stopping old BrainClaw service if present"
  systemctl stop "${BRAINCLAW_SERVICE_NAME}" 2>/dev/null || true

  step "Removing old BrainClaw virtual environment"
  rm -rf "${BRAINCLAW_DIR}/.venv"

  patch_brainclaw_requirements_for_py313

  if [[ -f "${installer}" ]]; then
    step "Running BrainClaw original installer with ${BRAINCLAW_PYTHON_BIN}"

    if env \
      SERVICE_NAME="${BRAINCLAW_SERVICE_NAME}" \
      INSTALL_DIR="${BRAINCLAW_DIR}" \
      PYTHON_BIN="${BRAINCLAW_PYTHON_BIN}" \
      PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT}" \
      PIP_DISABLE_PIP_VERSION_CHECK=1 \
      PIP_NO_INPUT=1 \
      bash "${installer}"; then

      ok "BrainClaw original installer finished"
      return 0
    fi

    warn "Original BrainClaw installer failed. Trying manual fallback."
  else
    warn "BrainClaw original service installer not found. Trying manual fallback."
  fi

  manual_brainclaw_install
}

install_prompt_integration() {
  step "Installing OpenClaw BrainClaw prompt integration"

  local env_file="${BRAINCLAW_DIR}/.env"
  local prompt_installer="${BRAINCLAW_DIR}/scripts/install-openclaw-prompt.sh"
  local memory_key=""

  create_brainclaw_env_if_missing

  memory_key="$(sed -n 's/^MEMORY_API_KEY=//p' "${env_file}" | head -n 1)"

  if [[ -z "${memory_key}" ]]; then
    fail "Could not read MEMORY_API_KEY from ${env_file}"
  fi

  if [[ -f "${prompt_installer}" ]]; then
    env \
      BRAINCLAW_URL="${BRAINCLAW_URL}" \
      BRAINCLAW_API_KEY="${memory_key}" \
      OPENCLAW_AGENT_ID="${OPENCLAW_AGENT_ID}" \
      OPENCLAW_WORKSPACE="${OPENCLAW_WORKSPACE}" \
      OPENCLAW_WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR}" \
      OPENCLAW_WORKSPACE_UID="$(id -u "${OPENCLAW_USER}")" \
      OPENCLAW_WORKSPACE_GID="$(id -g "${OPENCLAW_USER}")" \
      bash "${prompt_installer}"
  else
    warn "OpenClaw prompt installer not found. Creating minimal /etc/openclaw/environment.conf."

    install -d -m 0750 -o root -g "${OPENCLAW_GROUP}" /etc/openclaw

    cat > /etc/openclaw/environment.conf <<EOF
BRAINCLAW_URL=${BRAINCLAW_URL}
BRAINCLAW_API_KEY=${memory_key}
OPENCLAW_AGENT_ID=${OPENCLAW_AGENT_ID}
OPENCLAW_WORKSPACE=${OPENCLAW_WORKSPACE}
OPENCLAW_WORKSPACE_DIR=${OPENCLAW_WORKSPACE_DIR}
EOF
  fi

  if [[ -f /etc/openclaw/environment.conf ]]; then
    if grep -q '^BRAINCLAW_API_KEY=' /etc/openclaw/environment.conf; then
      sed -i "s#^BRAINCLAW_API_KEY=.*#BRAINCLAW_API_KEY=${memory_key}#" /etc/openclaw/environment.conf
    else
      printf '\nBRAINCLAW_API_KEY=%s\n' "${memory_key}" >> /etc/openclaw/environment.conf
    fi

    if grep -q '^BRAINCLAW_URL=' /etc/openclaw/environment.conf; then
      sed -i "s#^BRAINCLAW_URL=.*#BRAINCLAW_URL=${BRAINCLAW_URL}#" /etc/openclaw/environment.conf
    else
      printf 'BRAINCLAW_URL=%s\n' "${BRAINCLAW_URL}" >> /etc/openclaw/environment.conf
    fi

    chown root:"${OPENCLAW_GROUP}" /etc/openclaw/environment.conf || true
    chmod 0640 /etc/openclaw/environment.conf
  fi

  ok "Prompt integration installed"
}

setup_openclaw_gateway() {
  step "Setting up OpenClaw gateway service"

  if [[ "${SKIP_OPENCLAW_GATEWAY}" == "1" ]]; then
    warn "Skipping OpenClaw gateway setup because SKIP_OPENCLAW_GATEWAY=1"
    return 0
  fi

  if need_cmd loginctl; then
    loginctl enable-linger "${OPENCLAW_USER}" || warn "Could not enable linger. User service may require active login."
  else
    warn "loginctl not found. Skipping linger setup."
  fi

  if sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc '
    export PATH="$OPENCLAW_NPM_PREFIX/bin:$PATH"
    openclaw gateway install
  '; then
    ok "OpenClaw gateway installer completed"
  else
    warn "openclaw gateway install failed. Continuing with status check."
  fi

  sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc '
    export PATH="$OPENCLAW_NPM_PREFIX/bin:$PATH"
    openclaw gateway status
  ' || warn "Gateway status check failed. Run manually: sudo -iu ${OPENCLAW_USER} ${OPENCLAW_NPM_PREFIX}/bin/openclaw gateway status"
}

cleanup_previous_hanging_install() {
  step "Checking for previous hanging BrainClaw pip installers"

  local pids
  pids="$(pgrep -f '/opt/brainclaw/.venv/bin/pip install' || true)"

  if [[ -n "${pids}" ]]; then
    warn "Found previous BrainClaw pip installer process:"
    ps -fp ${pids} || true

    if [[ -r /dev/tty && -w /dev/tty ]]; then
      read -r -p "Kill these old pip processes? [y/N] " kill_confirm < /dev/tty

      if [[ "${kill_confirm}" =~ ^[Yy]$ ]]; then
        kill ${pids} 2>/dev/null || true
        sleep 2
        kill -9 ${pids} 2>/dev/null || true
        ok "Old pip processes killed"
      else
        warn "Leaving old pip processes running"
      fi
    else
      kill ${pids} 2>/dev/null || true
      sleep 2
      kill -9 ${pids} 2>/dev/null || true
      ok "Old pip processes killed"
    fi
  else
    ok "No old BrainClaw pip installer process found"
  fi
}

test_brainclaw_service() {
  step "Testing BrainClaw service"

  systemctl daemon-reload
  systemctl restart "${BRAINCLAW_SERVICE_NAME}" || true
  sleep 3

  if systemctl is-active --quiet "${BRAINCLAW_SERVICE_NAME}"; then
    ok "BrainClaw service is active"
  else
    warn "BrainClaw service is not active. Showing logs:"
    journalctl -u "${BRAINCLAW_SERVICE_NAME}" -n 80 --no-pager || true
  fi

  if need_cmd curl; then
    curl -fsS "${BRAINCLAW_URL}/" >/dev/null 2>&1 && ok "BrainClaw HTTP endpoint responded" || warn "BrainClaw HTTP endpoint did not respond at ${BRAINCLAW_URL}"
  fi
}

print_summary() {
  cat <<EOF

${GREEN}${BOLD}Setup complete.${RESET}

OpenClaw user:
  ${OPENCLAW_USER}

OpenClaw home:
  ${OPENCLAW_HOME}

OpenClaw workspace:
  ${OPENCLAW_WORKSPACE_DIR}

OpenClaw npm prefix:
  ${OPENCLAW_NPM_PREFIX}

BrainClaw:
  ${BRAINCLAW_DIR}
  ${BRAINCLAW_URL}/admin

Python used for BrainClaw:
  ${BRAINCLAW_PYTHON_BIN} $(${BRAINCLAW_PYTHON_BIN} --version 2>/dev/null || true)

Useful commands:

  sudo systemctl status ${BRAINCLAW_SERVICE_NAME}

  sudo journalctl -u ${BRAINCLAW_SERVICE_NAME} -n 100 --no-pager

  sudo -iu ${OPENCLAW_USER}
  ${OPENCLAW_NPM_PREFIX}/bin/openclaw gateway status

Start OpenClaw with BrainClaw environment:

  sudo -iu ${OPENCLAW_USER}
  openclaw-brainclaw ${OPENCLAW_NPM_PREFIX}/bin/openclaw

If password setup was skipped:

  sudo passwd ${OPENCLAW_USER}

EOF
}

confirm_run() {
  if [[ "${ASSUME_YES}" == "1" ]]; then
    return 0
  fi

  if [[ ! -r /dev/tty || ! -w /dev/tty ]]; then
    fail "No interactive TTY detected. Re-run with ASSUME_YES=1 for non-interactive installation."
  fi

  warn "This script installs packages, creates or updates a Linux user, clones repositories, and enables services."
  read -r -p "Continue? [y/N] " confirm < /dev/tty

  if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
    fail "Cancelled."
  fi
}

main() {
  banner
  confirm_run

  cleanup_previous_hanging_install
  install_dependencies
  create_openclaw_user
  install_openclaw
  checkout_brainclaw
  install_brainclaw_service
  install_prompt_integration
  setup_openclaw_gateway
  test_brainclaw_service
  print_summary
}

main "$@"