#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${SUDO_USER:-${USER}}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This installer supports Linux only." >&2
  exit 1
fi

if [[ "$APP_USER" == "root" && -z "${SUDO_USER:-}" ]]; then
  echo "Run this installer as the bench user, not as root." >&2
  echo "It will ask sudo only for system packages and serial permissions." >&2
  exit 1
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

run_as_user() {
  if [[ "$(id -un)" == "$APP_USER" ]]; then
    "$@"
  else
    sudo -H -u "$APP_USER" "$@"
  fi
}

install_system_packages() {
  if need_cmd apt-get; then
    sudo apt-get update
    sudo apt-get install -y git python3 python3-pip pipx iperf3
  elif need_cmd dnf; then
    sudo dnf install -y git python3 python3-pip pipx iperf3
  elif need_cmd pacman; then
    sudo pacman -Sy --needed git python python-pipx iperf3
  else
    echo "Unsupported package manager. Install git, python3, pipx and iperf3 manually." >&2
    exit 1
  fi
}

check_python_version() {
  python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required")
PY
}

add_serial_groups() {
  local groups=()
  for group in dialout uucp; do
    if getent group "$group" >/dev/null; then
      groups+=("$group")
      sudo usermod -aG "$group" "$APP_USER"
    fi
  done

  if ((${#groups[@]} == 0)); then
    echo "Warning: no dialout/uucp group found. Check serial permissions manually." >&2
  else
    echo "Added $APP_USER to serial group(s): ${groups[*]}"
    echo "Log out and back in, or run: newgrp ${groups[0]}"
  fi
}

install_switchlive() {
  run_as_user python3 -m pipx ensurepath
  run_as_user python3 -m pipx install --force --include-deps "$PROJECT_DIR"

  if [[ ! -f "$PROJECT_DIR/switchlive.json" ]]; then
    run_as_user cp "$PROJECT_DIR/configs/switchlive.example.json" "$PROJECT_DIR/switchlive.json"
  fi
  if [[ ! -f "$PROJECT_DIR/standart_login.txt" ]]; then
    run_as_user cp "$PROJECT_DIR/configs/standart_login.example.txt" "$PROJECT_DIR/standart_login.txt"
  fi
}

echo "Installing switchLIVE for user: $APP_USER"
install_system_packages
check_python_version
add_serial_groups
install_switchlive

echo
echo "Done."
echo "Start a new shell after re-login, then run:"
echo "  switchlive"
