#!/usr/bin/env bash
set -euo pipefail

OPENCLAW_USER="${OPENCLAW_USER:-openclaw}"
OPENCLAW_GROUP="${OPENCLAW_GROUP:-$OPENCLAW_USER}"
OPENCLAW_HOME="${OPENCLAW_HOME:-/home/${OPENCLAW_USER}}"
OPENCLAW_INSTALL_DIR="${OPENCLAW_INSTALL_DIR:-${OPENCLAW_HOME}/.openclaw}"
OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX:-${OPENCLAW_INSTALL_DIR}/npm}"
OPENCLAW_WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-${OPENCLAW_INSTALL_DIR}/workspace}"
OPENCLAW_AGENT_ID="${OPENCLAW_AGENT_ID:-Kim}"
OPENCLAW_WORKSPACE="${OPENCLAW_WORKSPACE:-Kims-workspace}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRAINCLAW_SOURCE_DIR="${BRAINCLAW_SOURCE_DIR:-${SCRIPT_DIR}}"
BRAINCLAW_REPO="${BRAINCLAW_REPO:-}"
BRAINCLAW_DIR="${BRAINCLAW_DIR:-/opt/brainclaw}"
BRAINCLAW_SERVICE_NAME="${BRAINCLAW_SERVICE_NAME:-brainclaw}"
BRAINCLAW_PYTHON_BIN="${BRAINCLAW_PYTHON_BIN:-python3}"
BRAINCLAW_HOST="${BRAINCLAW_HOST:-}"
BRAINCLAW_URL="${BRAINCLAW_URL:-}"
BRAINCLAW_PORT="${BRAINCLAW_PORT:-8757}"
BRAINCLAW_SCHEME="${BRAINCLAW_SCHEME:-${BRAINCLAW_PROTOCOL:-http}}"
BRAINCLAW_SSL_CERTFILE="${BRAINCLAW_SSL_CERTFILE:-}"
BRAINCLAW_SSL_KEYFILE="${BRAINCLAW_SSL_KEYFILE:-}"
BRAINCLAW_FAISS_PACKAGE="${BRAINCLAW_FAISS_PACKAGE:-faiss-cpu==1.8.0.post1}"
BRAINCLAW_NUMPY_PACKAGE="${BRAINCLAW_NUMPY_PACKAGE:-numpy==1.26.4}"

NODE_MAJOR="${NODE_MAJOR:-22}"
ASSUME_YES="${ASSUME_YES:-0}"
SKIP_OPENCLAW_GATEWAY="${SKIP_OPENCLAW_GATEWAY:-0}"
REMOVE_DATA="${REMOVE_DATA:-0}"
REMOVE_OPENCLAW="${REMOVE_OPENCLAW:-0}"
REMOVE_OPENCLAW_USER="${REMOVE_OPENCLAW_USER:-0}"

export PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT:-180}"
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1

if [[ "${EUID}" -ne 0 && ! "${1:-}" =~ ^(-h|--help|help)$ ]]; then
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

strip_cr() {
  tr -d '\r'
}

version_ge() {
  printf '%s\n%s\n' "$2" "$1" | sort -V -C
}

package_manager() {
  if need_cmd apt-get; then
    echo apt
  elif need_cmd dnf; then
    echo dnf
  elif need_cmd yum; then
    echo yum
  elif need_cmd pacman; then
    echo pacman
  elif need_cmd zypper; then
    echo zypper
  elif need_cmd apk; then
    echo apk
  else
    echo none
  fi
}

install_packages() {
  if (( $# == 0 )); then
    return 0
  fi

  case "$(package_manager)" in
    apt)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update
      apt-get install -y "$@"
      ;;
    dnf)
      dnf install -y "$@"
      ;;
    yum)
      yum install -y "$@"
      ;;
    pacman)
      pacman -Sy --needed --noconfirm "$@"
      ;;
    zypper)
      zypper --non-interactive install "$@"
      ;;
    apk)
      apk add --no-cache "$@"
      ;;
    *)
      fail "No supported package manager found. Install dependencies manually, then rerun this script."
      ;;
  esac
}

install_os_dependencies() {
  step "Installing OS dependencies"

  case "$(package_manager)" in
    apt)
      install_packages \
        ca-certificates curl gnupg git rsync sudo systemd build-essential pkg-config \
        libsqlite3-dev libffi-dev libssl-dev python3 python3-venv python3-pip python3-dev
      ;;
    dnf|yum)
      install_packages \
        ca-certificates curl gnupg git rsync sudo systemd gcc gcc-c++ make pkgconf-pkg-config \
        sqlite-devel libffi-devel openssl-devel python3 python3-pip python3-devel
      ;;
    pacman)
      install_packages \
        ca-certificates curl gnupg git rsync sudo systemd base-devel pkgconf \
        sqlite libffi openssl python python-pip
      ;;
    zypper)
      install_packages \
        ca-certificates curl gpg2 git rsync sudo systemd gcc gcc-c++ make pkg-config \
        sqlite3-devel libffi-devel libopenssl-devel python3 python3-pip python3-devel
      ;;
    apk)
      install_packages \
        ca-certificates curl gnupg git rsync sudo build-base pkgconf \
        sqlite-dev libffi-dev openssl-dev python3 py3-pip
      ;;
    *)
      fail "No supported package manager found. Install dependencies manually, then rerun this script."
      ;;
  esac
}

detect_python() {
  local candidates=(
    "${BRAINCLAW_PYTHON_BIN}"
    python3.12
    python3.11
    python3.13
    python3
    python
  )

  local py
  local ver

  for py in "${candidates[@]}"; do
    [[ -z "${py}" ]] && continue

    if need_cmd "${py}"; then
      ver="$("${py}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"

      if [[ -n "${ver}" ]] && version_ge "${ver}" "3.11"; then
        BRAINCLAW_PYTHON_BIN="${py}"
        ok "Using Python ${ver}: $(command -v "${py}")"
        return 0
      fi
    fi
  done

  fail "Python > 3.10 is required. Install Python 3.11 or newer, or set BRAINCLAW_PYTHON_BIN."
}

python_minor() {
  "${BRAINCLAW_PYTHON_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
}

valid_bind_host() {
  local host="$1"
  if [[ "${host}" == "localhost" || "${host}" == "127.0.0.1" || "${host}" == "0.0.0.0" ]]; then
    return 0
  fi
  [[ "${host}" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
}

url_host_for_bind() {
  case "$1" in
    localhost|127.0.0.1|0.0.0.0)
      printf '127.0.0.1'
      ;;
    *)
      printf '%s' "$1"
      ;;
  esac
}

configure_brainclaw_bind() {
  local choice
  local custom
  local url_host

  BRAINCLAW_SCHEME="$(printf '%s' "${BRAINCLAW_SCHEME}" | strip_cr)"
  BRAINCLAW_SSL_CERTFILE="$(printf '%s' "${BRAINCLAW_SSL_CERTFILE}" | strip_cr)"
  BRAINCLAW_SSL_KEYFILE="$(printf '%s' "${BRAINCLAW_SSL_KEYFILE}" | strip_cr)"
  if [[ "${BRAINCLAW_SCHEME}" != "http" && "${BRAINCLAW_SCHEME}" != "https" ]]; then
    fail "BRAINCLAW_SCHEME must be http or https."
  fi

  if [[ -n "${BRAINCLAW_HOST}" ]]; then
    BRAINCLAW_HOST="$(printf '%s' "${BRAINCLAW_HOST}" | strip_cr)"
    if ! valid_bind_host "${BRAINCLAW_HOST}"; then
      fail "Invalid BRAINCLAW_HOST: ${BRAINCLAW_HOST}"
    fi
  elif [[ "${ASSUME_YES}" == "1" ]]; then
    BRAINCLAW_HOST="127.0.0.1"
  else
    if [[ ! -r /dev/tty || ! -w /dev/tty ]]; then
      fail "No interactive TTY detected. Set BRAINCLAW_HOST=127.0.0.1, 0.0.0.0, or an IP address."
    fi

    while true; do
      cat > /dev/tty <<EOF

Bind BrainClaw to:
  1) localhost only (127.0.0.1)
  2) all interfaces (0.0.0.0)
  3) custom IP address
EOF
      read -r -p "Choose bind address [1]: " choice < /dev/tty
      case "${choice:-1}" in
        1)
          BRAINCLAW_HOST="127.0.0.1"
          break
          ;;
        2)
          BRAINCLAW_HOST="0.0.0.0"
          break
          ;;
        3)
          read -r -p "Enter IP address to bind: " custom < /dev/tty
          if valid_bind_host "${custom}"; then
            BRAINCLAW_HOST="${custom}"
            break
          fi
          warn "Invalid bind address: ${custom}"
          ;;
        *)
          warn "Choose 1, 2, or 3."
          ;;
      esac
    done
  fi

  url_host="$(url_host_for_bind "${BRAINCLAW_HOST}")"
  BRAINCLAW_URL="$(printf '%s' "${BRAINCLAW_URL}" | strip_cr)"
  BRAINCLAW_URL="${BRAINCLAW_URL:-${BRAINCLAW_SCHEME}://${url_host}:${BRAINCLAW_PORT}}"
  if [[ "${BRAINCLAW_HOST}" == "0.0.0.0" ]]; then
    warn "Binding to 0.0.0.0 exposes BrainClaw on all network interfaces. Use firewalling and keep the API key private."
  fi
  if [[ "${BRAINCLAW_SCHEME}" == "https" && ( -z "${BRAINCLAW_SSL_CERTFILE}" || -z "${BRAINCLAW_SSL_KEYFILE}" ) ]]; then
    warn "BRAINCLAW_SCHEME=https is set without BRAINCLAW_SSL_CERTFILE and BRAINCLAW_SSL_KEYFILE. URLs will use https, but Uvicorn will not serve TLS unless certificate paths are configured."
  fi
  ok "BrainClaw will bind to ${BRAINCLAW_HOST}; local URL is ${BRAINCLAW_URL}"
}

load_brainclaw_env_settings() {
  local env_file="${BRAINCLAW_DIR}/.env"
  [[ -f "${env_file}" ]] || return 0

  if [[ -z "${BRAINCLAW_HOST}" ]]; then
    BRAINCLAW_HOST="$(sed -n 's/^HOST=//p' "${env_file}" | head -n 1 | strip_cr)"
  fi
  if [[ "${BRAINCLAW_PORT}" == "8757" ]]; then
    BRAINCLAW_PORT="$(sed -n 's/^PORT=//p' "${env_file}" | head -n 1 | strip_cr)"
    BRAINCLAW_PORT="${BRAINCLAW_PORT:-8757}"
  fi
  if [[ "${BRAINCLAW_SCHEME}" == "http" ]]; then
    BRAINCLAW_SCHEME="$(sed -n 's/^BRAINCLAW_SCHEME=//p' "${env_file}" | head -n 1 | strip_cr)"
    BRAINCLAW_SCHEME="${BRAINCLAW_SCHEME:-http}"
  fi
  if [[ -z "${BRAINCLAW_SSL_CERTFILE}" ]]; then
    BRAINCLAW_SSL_CERTFILE="$(sed -n 's/^BRAINCLAW_SSL_CERTFILE=//p' "${env_file}" | head -n 1 | strip_cr)"
  fi
  if [[ -z "${BRAINCLAW_SSL_KEYFILE}" ]]; then
    BRAINCLAW_SSL_KEYFILE="$(sed -n 's/^BRAINCLAW_SSL_KEYFILE=//p' "${env_file}" | head -n 1 | strip_cr)"
  fi
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

  if [[ "$(package_manager)" == "apt" ]]; then
    install_packages ca-certificates curl gnupg
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
    apt-get install -y nodejs
  else
    warn "NodeSource automatic setup is only used on apt-based systems. Installing Node.js from the system package manager."
    case "$(package_manager)" in
      dnf|yum|zypper)
        install_packages nodejs npm
        ;;
      pacman)
        install_packages nodejs npm
        ;;
      apk)
        install_packages nodejs npm
        ;;
      *)
        fail "No supported package manager found for Node.js installation."
        ;;
    esac
  fi

  current="$(node_major)"

  if (( current < NODE_MAJOR )); then
    fail "Node.js installation failed or installed version is lower than ${NODE_MAJOR}."
  fi

  ok "Node.js $(node --version) installed"
}

install_dependencies() {
  step "Checking OS dependencies"

  install_os_dependencies
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
    fail "Could not set password for ${OPENCLAW_USER}. Run manually: sudo passwd ${OPENCLAW_USER}"
  fi

  passwd -S "${OPENCLAW_USER}" >/dev/null 2>&1 || true
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

  if [[ -n "${BRAINCLAW_REPO}" ]]; then
    if [[ -d "${BRAINCLAW_DIR}/.git" ]]; then
      git -C "${BRAINCLAW_DIR}" pull --ff-only || warn "Git pull failed. Continuing with existing BrainClaw directory."
    else
      rm -rf "${BRAINCLAW_DIR}"
      git clone "${BRAINCLAW_REPO}" "${BRAINCLAW_DIR}"
    fi
  else
    if [[ ! -f "${BRAINCLAW_SOURCE_DIR}/requirements.txt" || ! -d "${BRAINCLAW_SOURCE_DIR}/app" ]]; then
      fail "BRAINCLAW_SOURCE_DIR does not look like a BrainClaw checkout: ${BRAINCLAW_SOURCE_DIR}"
    fi

    install -d -m 0750 "${BRAINCLAW_DIR}"
    rsync -a \
      --delete \
      --exclude ".git" \
      --exclude ".venv" \
      --exclude "__pycache__" \
      --exclude "data/backups" \
      --exclude "data/indexes" \
      --exclude "data/uploads" \
      "${BRAINCLAW_SOURCE_DIR}/" "${BRAINCLAW_DIR}/"
  fi

  if [[ ! -d "${BRAINCLAW_DIR}" ]]; then
    fail "BrainClaw directory was not created: ${BRAINCLAW_DIR}"
  fi
}

uvicorn_ssl_args() {
  if [[ -n "${BRAINCLAW_SSL_CERTFILE}" && -n "${BRAINCLAW_SSL_KEYFILE}" ]]; then
    printf ' --ssl-certfile %q --ssl-keyfile %q' "${BRAINCLAW_SSL_CERTFILE}" "${BRAINCLAW_SSL_KEYFILE}"
  fi
}

reset_installed_brainclaw_data() {
  step "Resetting BrainClaw data to defaults"

  local data_dir="${BRAINCLAW_DIR}/data"
  local backup_dir="${data_dir}/backups"
  local preserved_backups
  preserved_backups="$(mktemp -d)"

  if [[ -d "${backup_dir}" ]]; then
    cp -a "${backup_dir}" "${preserved_backups}/backups"
  fi

  rm -rf \
    "${BRAINCLAW_DIR}/data/memory.sqlite3" \
    "${BRAINCLAW_DIR}/data/memory.sqlite3-wal" \
    "${BRAINCLAW_DIR}/data/memory.sqlite3-shm" \
    "${BRAINCLAW_DIR}/data/faiss.index" \
    "${BRAINCLAW_DIR}/data/id_map.json" \
    "${BRAINCLAW_DIR}/data/indexes" \
    "${BRAINCLAW_DIR}/data/uploads"

  find "${data_dir}" -mindepth 1 -maxdepth 1 ! -name backups ! -name logs -exec rm -rf {} + 2>/dev/null || true

  install -d -o "${BRAINCLAW_SERVICE_NAME}" -g "${BRAINCLAW_SERVICE_NAME}" -m 0750 "${data_dir}"
  install -d -o "${BRAINCLAW_SERVICE_NAME}" -g "${BRAINCLAW_SERVICE_NAME}" -m 0750 "${data_dir}/indexes"
  install -d -o "${BRAINCLAW_SERVICE_NAME}" -g "${BRAINCLAW_SERVICE_NAME}" -m 0750 "${data_dir}/uploads"
  install -d -o "${BRAINCLAW_SERVICE_NAME}" -g "${BRAINCLAW_SERVICE_NAME}" -m 0750 "${data_dir}/logs"

  if [[ -d "${preserved_backups}/backups" ]]; then
    install -d -o "${BRAINCLAW_SERVICE_NAME}" -g "${BRAINCLAW_SERVICE_NAME}" -m 0750 "${backup_dir}"
    cp -a "${preserved_backups}/backups/." "${backup_dir}/"
  fi
  rm -rf "${preserved_backups}"

  ok "BrainClaw database, indexes, and uploads reset"
}

repair_brainclaw_permissions() {
  step "Repairing BrainClaw install permissions"

  if [[ ! -d "${BRAINCLAW_DIR}" ]]; then
    fail "BrainClaw install directory not found: ${BRAINCLAW_DIR}"
  fi

  chown -R "${BRAINCLAW_SERVICE_NAME}:${BRAINCLAW_SERVICE_NAME}" "${BRAINCLAW_DIR}"
  chmod 0750 "${BRAINCLAW_DIR}"
  find "${BRAINCLAW_DIR}" -type d -exec chmod u+rwx,g+rx,o-rwx {} + 2>/dev/null || true
  find "${BRAINCLAW_DIR}" -type f -exec chmod u+rw,g+r,o-rwx {} + 2>/dev/null || true

  if [[ -d "${BRAINCLAW_DIR}/.venv/bin" ]]; then
    find "${BRAINCLAW_DIR}/.venv/bin" -type f -exec chmod u+rx,g+rx {} + 2>/dev/null || true
  fi
  if [[ -f "${BRAINCLAW_DIR}/.env" ]]; then
    chmod 0640 "${BRAINCLAW_DIR}/.env"
  fi

  ok "BrainClaw install is readable/executable by ${BRAINCLAW_SERVICE_NAME}"
}

patch_brainclaw_requirements() {
  step "Patching BrainClaw requirements"

  local req="${BRAINCLAW_DIR}/requirements.txt"

  if [[ ! -f "${req}" ]]; then
    warn "requirements.txt not found. Creating minimal fallback requirements.txt."
    cat > "${req}" <<'EOF'
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
anyio>=4.7.0,<5
pydantic>=2.9.0
python-dotenv>=1.0.1
requests>=2.32.0
numpy==1.26.4
faiss-cpu==1.8.0.post1
sentence-transformers>=3.3.0
transformers>=4.46.0
torch>=2.2.0
pypdf>=5.0.0
python-docx>=1.1.2
pandas>=2.2.3
EOF
    return 0
  fi

  cp -a "${req}" "${req}.bak.$(date +%Y%m%d-%H%M%S)"

  sed -i \
    -e "s/^faiss-cpu[<=>!~].*/${BRAINCLAW_FAISS_PACKAGE}/" \
    -e "s/^numpy[<=>!~].*/${BRAINCLAW_NUMPY_PACKAGE}/" \
    -e 's/^scipy==.*/scipy>=1.14.0/' \
    -e 's/^scikit-learn==.*/scikit-learn>=1.5.0/' \
    -e 's/^pandas==.*/pandas>=2.2.3/' \
    -e 's/^pydantic==.*/pydantic>=2.9.0/' \
    -e 's/^fastapi==.*/fastapi>=0.115.0/' \
    -e 's/^uvicorn==.*/uvicorn>=0.30.0/' \
    -e 's/^anyio==.*/anyio>=4.7.0,<5/' \
    -e 's/^sentence-transformers==.*/sentence-transformers>=3.3.0/' \
    -e 's/^transformers==.*/transformers>=4.46.0/' \
    -e 's/^python-dotenv==.*/python-dotenv>=1.0.1/' \
    -e 's/^requests==.*/requests>=2.32.0/' \
    -e 's/^pypdf==.*/pypdf>=5.0.0/' \
    -e 's/^python-docx==.*/python-docx>=1.1.2/' \
    "${req}"

  if ! grep -q '^anyio[<=>!~]' "${req}"; then
    printf '\nanyio>=4.7.0,<5\n' >> "${req}"
  fi

  ok "requirements.txt patched for conservative CPU wheels. Backup created."
}

create_brainclaw_env_if_missing() {
  step "Ensuring BrainClaw .env exists"

  local env_file="${BRAINCLAW_DIR}/.env"

  if [[ -f "${env_file}" ]]; then
    ok "BrainClaw .env already exists"
    if grep -q '^HOST=' "${env_file}"; then
      sed -i "s#^HOST=.*#HOST=${BRAINCLAW_HOST}#" "${env_file}"
    else
      printf 'HOST=%s\n' "${BRAINCLAW_HOST}" >> "${env_file}"
    fi
    if grep -q '^PORT=' "${env_file}"; then
      sed -i "s#^PORT=.*#PORT=${BRAINCLAW_PORT}#" "${env_file}"
    else
      printf 'PORT=%s\n' "${BRAINCLAW_PORT}" >> "${env_file}"
    fi
    if grep -q '^BRAINCLAW_SCHEME=' "${env_file}"; then
      sed -i "s#^BRAINCLAW_SCHEME=.*#BRAINCLAW_SCHEME=${BRAINCLAW_SCHEME}#" "${env_file}"
    else
      printf 'BRAINCLAW_SCHEME=%s\n' "${BRAINCLAW_SCHEME}" >> "${env_file}"
    fi
    if grep -q '^BRAINCLAW_SSL_CERTFILE=' "${env_file}"; then
      sed -i "s#^BRAINCLAW_SSL_CERTFILE=.*#BRAINCLAW_SSL_CERTFILE=${BRAINCLAW_SSL_CERTFILE}#" "${env_file}"
    else
      printf 'BRAINCLAW_SSL_CERTFILE=%s\n' "${BRAINCLAW_SSL_CERTFILE}" >> "${env_file}"
    fi
    if grep -q '^BRAINCLAW_SSL_KEYFILE=' "${env_file}"; then
      sed -i "s#^BRAINCLAW_SSL_KEYFILE=.*#BRAINCLAW_SSL_KEYFILE=${BRAINCLAW_SSL_KEYFILE}#" "${env_file}"
    else
      printf 'BRAINCLAW_SSL_KEYFILE=%s\n' "${BRAINCLAW_SSL_KEYFILE}" >> "${env_file}"
    fi
    if grep -q '^LOG_FILE=' "${env_file}"; then
      sed -i "s#^LOG_FILE=.*#LOG_FILE=${BRAINCLAW_DIR}/data/logs/brainclaw.jsonl#" "${env_file}"
    else
      printf 'LOG_FILE=%s/data/logs/brainclaw.jsonl\n' "${BRAINCLAW_DIR}" >> "${env_file}"
    fi
    if ! grep -q '^LOG_MAX_BYTES=' "${env_file}"; then
      printf 'LOG_MAX_BYTES=10485760\n' >> "${env_file}"
    fi
    if ! grep -q '^LOG_BACKUP_COUNT=' "${env_file}"; then
      printf 'LOG_BACKUP_COUNT=5\n' >> "${env_file}"
    fi
    ok "BrainClaw .env bind settings updated"
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
ADMIN_SESSION_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)
HOST=${BRAINCLAW_HOST}
PORT=${BRAINCLAW_PORT}
BRAINCLAW_SCHEME=${BRAINCLAW_SCHEME}
BRAINCLAW_SSL_CERTFILE=${BRAINCLAW_SSL_CERTFILE}
BRAINCLAW_SSL_KEYFILE=${BRAINCLAW_SSL_KEYFILE}
LOG_FILE=${BRAINCLAW_DIR}/data/logs/brainclaw.jsonl
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
DATA_DIR=${BRAINCLAW_DIR}/data
SQLITE_PATH=${BRAINCLAW_DIR}/data/memory.sqlite3
FAISS_INDEX_PATH=${BRAINCLAW_DIR}/data/faiss.index
ID_MAP_PATH=${BRAINCLAW_DIR}/data/id_map.json
INDEX_DIR=${BRAINCLAW_DIR}/data/indexes
UPLOAD_DIR=${BRAINCLAW_DIR}/data/uploads
EOF

  chmod 0640 "${env_file}"
  chown "${BRAINCLAW_SERVICE_NAME}:${BRAINCLAW_SERVICE_NAME}" "${env_file}" 2>/dev/null || true

  ok "BrainClaw .env created"
}

find_brainclaw_app() {
  if [[ -f "${BRAINCLAW_DIR}/app/main.py" ]]; then
    printf 'app.main:app'
  elif [[ -f "${BRAINCLAW_DIR}/main.py" ]]; then
    printf 'main:app'
  elif [[ -f "${BRAINCLAW_DIR}/brainclaw/main.py" ]]; then
    printf 'brainclaw.main:app'
  elif [[ -f "${BRAINCLAW_DIR}/brainclaw/app.py" ]]; then
    printf 'brainclaw.app:app'
  elif [[ -f "${BRAINCLAW_DIR}/server/main.py" ]]; then
    printf 'server.main:app'
  else
    fail "Could not find BrainClaw ASGI app under ${BRAINCLAW_DIR}"
  fi
}

manual_brainclaw_install() {
  step "Manual BrainClaw installation fallback"

  if ! id -u "${BRAINCLAW_SERVICE_NAME}" >/dev/null 2>&1; then
    useradd --system --home-dir "${BRAINCLAW_DIR}" --shell /usr/sbin/nologin "${BRAINCLAW_SERVICE_NAME}" || true
  fi

  install -d -o "${BRAINCLAW_SERVICE_NAME}" -g "${BRAINCLAW_SERVICE_NAME}" -m 0750 "${BRAINCLAW_DIR}"
  install -d -o "${BRAINCLAW_SERVICE_NAME}" -g "${BRAINCLAW_SERVICE_NAME}" -m 0750 "${BRAINCLAW_DIR}/data"

  repair_brainclaw_permissions

  sudo -u "${BRAINCLAW_SERVICE_NAME}" -H "${BRAINCLAW_PYTHON_BIN}" -m venv "${BRAINCLAW_DIR}/.venv"

  sudo -u "${BRAINCLAW_SERVICE_NAME}" -H "${BRAINCLAW_DIR}/.venv/bin/python" -m pip install --upgrade pip setuptools wheel

  sudo -u "${BRAINCLAW_SERVICE_NAME}" -H env \
    PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT}" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1 \
    "${BRAINCLAW_DIR}/.venv/bin/pip" install --prefer-binary -r "${BRAINCLAW_DIR}/requirements.txt"

  create_brainclaw_env_if_missing

  local app_target
  local ssl_args
  app_target="$(find_brainclaw_app)"
  ssl_args="$(uvicorn_ssl_args)"

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
ExecStart=${BRAINCLAW_DIR}/.venv/bin/uvicorn ${app_target} --host ${BRAINCLAW_HOST} --port ${BRAINCLAW_PORT}${ssl_args}
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

  step "Stopping old BrainClaw service if present"
  systemctl stop "${BRAINCLAW_SERVICE_NAME}" 2>/dev/null || true

  step "Removing old BrainClaw virtual environment"
  rm -rf "${BRAINCLAW_DIR}/.venv"

  patch_brainclaw_requirements
  manual_brainclaw_install
}

install_prompt_integration() {
  step "Installing OpenClaw BrainClaw prompt integration"

  local env_file="${BRAINCLAW_DIR}/.env"
  local prompt_installer="${BRAINCLAW_DIR}/scripts/install-openclaw-prompt.sh"
  local memory_key=""

  create_brainclaw_env_if_missing

  memory_key="$(sed -n 's/^MEMORY_API_KEY=//p' "${env_file}" | head -n 1 | strip_cr)"

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

inject_brainclaw_into_openclaw_user() {
  step "Injecting BrainClaw environment into OpenClaw user"

  local user_env="${OPENCLAW_INSTALL_DIR}/brainclaw.env"
  local launcher="${OPENCLAW_NPM_PREFIX}/bin/openclaw-with-brainclaw"
  local shell_block_start="# >>> brainclaw openclaw integration >>>"
  local shell_block_end="# <<< brainclaw openclaw integration <<<"

  if [[ ! -f /etc/openclaw/environment.conf ]]; then
    fail "/etc/openclaw/environment.conf was not created."
  fi

  install -d -o "${OPENCLAW_USER}" -g "${OPENCLAW_GROUP}" -m 0750 "${OPENCLAW_INSTALL_DIR}"
  install -d -o "${OPENCLAW_USER}" -g "${OPENCLAW_GROUP}" -m 0750 "${OPENCLAW_NPM_PREFIX}/bin"
  install -m 0640 -o "${OPENCLAW_USER}" -g "${OPENCLAW_GROUP}" /etc/openclaw/environment.conf "${user_env}"

  cat > "${launcher}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec /usr/local/bin/openclaw-brainclaw "${OPENCLAW_NPM_PREFIX}/bin/openclaw" "\$@"
EOF
  chown "${OPENCLAW_USER}:${OPENCLAW_GROUP}" "${launcher}"
  chmod 0750 "${launcher}"

  for profile in "${OPENCLAW_HOME}/.bashrc" "${OPENCLAW_HOME}/.profile"; do
    touch "${profile}"
    chown "${OPENCLAW_USER}:${OPENCLAW_GROUP}" "${profile}"
    python3 - "${profile}" "${shell_block_start}" "${shell_block_end}" "${OPENCLAW_NPM_PREFIX}" "${user_env}" "${launcher}" <<'PY'
from pathlib import Path
import sys

profile, start, end, npm_prefix, user_env, launcher = sys.argv[1:7]
path = Path(profile)
text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
block = f"""{start}
export OPENCLAW_NPM_PREFIX="{npm_prefix}"
export PATH="{npm_prefix}/bin:$PATH"
if [ -r "{user_env}" ]; then
  set -a
  . "{user_env}"
  set +a
fi
alias openclaw-brainclaw="{launcher}"
alias openclaw-memory="{launcher}"
{end}
"""
if start in text and end in text:
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    text = before.rstrip() + "\n\n" + block + after.lstrip()
else:
    text = text.rstrip() + "\n\n" + block
path.write_text(text, encoding="utf-8")
PY
    chown "${OPENCLAW_USER}:${OPENCLAW_GROUP}" "${profile}"
    chmod 0640 "${profile}"
  done

  ok "OpenClaw user shell now loads BrainClaw environment"
  ok "Run as ${OPENCLAW_USER}: openclaw-with-brainclaw"
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
  pids="$(pgrep -f "${BRAINCLAW_DIR}/.venv/bin/pip install" || true)"

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
    curl -fsS "${BRAINCLAW_URL}/admin/" >/dev/null 2>&1 && ok "BrainClaw admin endpoint responded" || warn "BrainClaw admin endpoint did not respond at ${BRAINCLAW_URL}/admin/"
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
  bind: ${BRAINCLAW_HOST}
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

confirm_uninstall() {
  if [[ "${ASSUME_YES}" == "1" ]]; then
    return 0
  fi

  if [[ ! -r /dev/tty || ! -w /dev/tty ]]; then
    fail "No interactive TTY detected. Re-run with ASSUME_YES=1 for non-interactive uninstall."
  fi

  warn "This will stop and uninstall BrainClaw service files."
  if [[ "${REMOVE_DATA}" == "1" || "${REMOVE_DATA}" == "true" ]]; then
    warn "REMOVE_DATA is enabled, so ${BRAINCLAW_DIR} will also be removed."
  fi
  if [[ "${REMOVE_OPENCLAW}" == "1" || "${REMOVE_OPENCLAW}" == "true" ]]; then
    warn "REMOVE_OPENCLAW is enabled, so OpenClaw integration files will also be removed."
  fi

  read -r -p "Continue uninstall? [y/N] " confirm < /dev/tty

  if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
    fail "Cancelled."
  fi
}

uninstall_stack() {
  banner
  confirm_uninstall

  step "Stopping BrainClaw service"
  if need_cmd systemctl; then
    systemctl stop "${BRAINCLAW_SERVICE_NAME}" 2>/dev/null || true
    systemctl disable "${BRAINCLAW_SERVICE_NAME}" 2>/dev/null || true
    rm -f "/etc/systemd/system/${BRAINCLAW_SERVICE_NAME}.service"
    systemctl daemon-reload
    systemctl reset-failed "${BRAINCLAW_SERVICE_NAME}" 2>/dev/null || true
    ok "BrainClaw service removed"
  else
    warn "systemctl not found. Removing service unit file only."
    rm -f "/etc/systemd/system/${BRAINCLAW_SERVICE_NAME}.service"
  fi

  if [[ "${REMOVE_DATA}" == "1" || "${REMOVE_DATA}" == "true" ]]; then
    step "Removing BrainClaw install directory"
    rm -rf "${BRAINCLAW_DIR}"
    ok "Removed ${BRAINCLAW_DIR}"
  else
    warn "Kept ${BRAINCLAW_DIR}. Set REMOVE_DATA=1 to remove it."
  fi

  if [[ "${REMOVE_OPENCLAW}" == "1" || "${REMOVE_OPENCLAW}" == "true" ]]; then
    step "Removing OpenClaw integration"
    if id -u "${OPENCLAW_USER}" >/dev/null 2>&1; then
      sudo -u "${OPENCLAW_USER}" -H env OPENCLAW_NPM_PREFIX="${OPENCLAW_NPM_PREFIX}" bash -lc '
        export PATH="$OPENCLAW_NPM_PREFIX/bin:$PATH"
        if command -v openclaw >/dev/null 2>&1; then
          openclaw gateway uninstall >/dev/null 2>&1 || true
        fi
      ' || true
    fi
    rm -f /usr/local/bin/openclaw-brainclaw
    rm -rf /etc/openclaw
    rm -rf "${OPENCLAW_INSTALL_DIR}"
    ok "OpenClaw integration files removed"
  else
    warn "Kept OpenClaw files. Set REMOVE_OPENCLAW=1 to remove integration files."
  fi

  if [[ "${REMOVE_OPENCLAW_USER}" == "1" || "${REMOVE_OPENCLAW_USER}" == "true" ]]; then
    step "Removing OpenClaw Linux user"
    userdel -r "${OPENCLAW_USER}" 2>/dev/null || userdel "${OPENCLAW_USER}" 2>/dev/null || true
    ok "Removed ${OPENCLAW_USER} if it existed"
  else
    warn "Kept Linux user ${OPENCLAW_USER}. Set REMOVE_OPENCLAW_USER=1 to remove it."
  fi
}

repair_service() {
  banner
  load_brainclaw_env_settings
  configure_brainclaw_bind

  if [[ ! -d "${BRAINCLAW_DIR}" ]]; then
    fail "BrainClaw install directory not found: ${BRAINCLAW_DIR}"
  fi

  local app_target
  local ssl_args
  app_target="$(find_brainclaw_app)"
  ssl_args="$(uvicorn_ssl_args)"

  repair_brainclaw_permissions

  step "Repairing BrainClaw systemd service using ${app_target}"
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
ExecStart=${BRAINCLAW_DIR}/.venv/bin/uvicorn ${app_target} --host ${BRAINCLAW_HOST} --port ${BRAINCLAW_PORT}${ssl_args}
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
  systemctl restart "${BRAINCLAW_SERVICE_NAME}"
  ok "BrainClaw service repaired and restarted"
}

repair_venv() {
  banner

  if [[ ! -d "${BRAINCLAW_DIR}" ]]; then
    fail "BrainClaw install directory not found: ${BRAINCLAW_DIR}"
  fi

  step "Stopping BrainClaw service"
  systemctl stop "${BRAINCLAW_SERVICE_NAME}" 2>/dev/null || true

  detect_python
  patch_brainclaw_requirements

  step "Rebuilding BrainClaw virtual environment"
  rm -rf "${BRAINCLAW_DIR}/.venv"
  repair_brainclaw_permissions
  sudo -u "${BRAINCLAW_SERVICE_NAME}" -H "${BRAINCLAW_PYTHON_BIN}" -m venv "${BRAINCLAW_DIR}/.venv"
  sudo -u "${BRAINCLAW_SERVICE_NAME}" -H "${BRAINCLAW_DIR}/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
  sudo -u "${BRAINCLAW_SERVICE_NAME}" -H env \
    PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT}" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1 \
    "${BRAINCLAW_DIR}/.venv/bin/pip" install --prefer-binary -r "${BRAINCLAW_DIR}/requirements.txt"

  step "Testing native imports"
  sudo -u "${BRAINCLAW_SERVICE_NAME}" -H bash -lc "cd '${BRAINCLAW_DIR}' && '${BRAINCLAW_DIR}/.venv/bin/python' - <<'PY'
import anyio
import anyio._backends._asyncio
import faiss
import numpy
import torch
print('runtime imports ok')
PY"

  load_brainclaw_env_settings
  configure_brainclaw_bind
  repair_service
}

inject_openclaw_only() {
  banner
  load_brainclaw_env_settings
  configure_brainclaw_bind
  install_dependencies
  create_openclaw_user
  install_openclaw
  install_prompt_integration
  inject_brainclaw_into_openclaw_user
  ok "BrainClaw injection into OpenClaw completed"
}

usage() {
  cat <<EOF
Usage:
  sudo ./setup.sh install
  sudo ./setup.sh uninstall
  sudo ./setup.sh repair-service
  sudo ./setup.sh repair-venv
  sudo ./setup.sh repair-permissions
  sudo ./setup.sh inject-openclaw

Install is the default command.

Useful environment options:
  ASSUME_YES=1               run without prompts
  OPENCLAW_PASSWORD=...      set the openclaw Linux user password non-interactively
  BRAINCLAW_DIR=/opt/path    install BrainClaw somewhere else
  BRAINCLAW_HOST=0.0.0.0     bind address: 127.0.0.1, 0.0.0.0, or a specific IP
  BRAINCLAW_PORT=8757        bind port
  BRAINCLAW_SCHEME=https     URL scheme for OpenClaw/admin links: http or https
  BRAINCLAW_SSL_CERTFILE=... TLS certificate path for Uvicorn
  BRAINCLAW_SSL_KEYFILE=...  TLS private key path for Uvicorn
  LOG_MAX_BYTES=10485760     JSONL log rotation size
  LOG_BACKUP_COUNT=5         JSONL rotated file count
  BRAINCLAW_FAISS_PACKAGE=... override FAISS package, default: ${BRAINCLAW_FAISS_PACKAGE}
  BRAINCLAW_NUMPY_PACKAGE=... override NumPy package, default: ${BRAINCLAW_NUMPY_PACKAGE}
  BRAINCLAW_REPO=https://... clone instead of installing from this checkout
  REMOVE_DATA=1              uninstall and remove BrainClaw installed files/data
  REMOVE_OPENCLAW=1          uninstall and remove OpenClaw integration files
  REMOVE_OPENCLAW_USER=1     uninstall and remove the openclaw Linux user
EOF
}

install_stack() {
  banner
  confirm_run
  configure_brainclaw_bind

  cleanup_previous_hanging_install
  install_dependencies
  create_openclaw_user
  install_openclaw
  checkout_brainclaw
  if ! id -u "${BRAINCLAW_SERVICE_NAME}" >/dev/null 2>&1; then
    useradd --system --home-dir "${BRAINCLAW_DIR}" --shell /usr/sbin/nologin "${BRAINCLAW_SERVICE_NAME}" || true
  fi
  reset_installed_brainclaw_data
  install_brainclaw_service
  install_prompt_integration
  inject_brainclaw_into_openclaw_user
  setup_openclaw_gateway
  test_brainclaw_service
  print_summary
}

main() {
  if [[ -t 1 ]]; then
    clear
  fi

  local command="${1:-install}"
  case "${command}" in
    install)
      shift || true
      install_stack "$@"
      ;;
    uninstall)
      shift || true
      uninstall_stack "$@"
      ;;
    repair-service)
      shift || true
      repair_service "$@"
      ;;
    repair-venv)
      shift || true
      repair_venv "$@"
      ;;
    repair-permissions)
      shift || true
      repair_brainclaw_permissions "$@"
      ;;
    inject-openclaw)
      shift || true
      inject_openclaw_only "$@"
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      usage >&2
      fail "Unknown command: ${command}"
      ;;
  esac
}

main "$@"
