#!/usr/bin/env bash
# Installs and starts text-editing-llm on Ubuntu Linux.
# Usage:  sudo ./install.sh        (run it again any time; it continues where it stopped)
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data
# shellcheck source=scripts/lib.sh
source scripts/lib.sh
exec > >(tee -a "$LOG_FILE") 2>&1

CI_MODE=0
[ "${1:-}" = "--ci" ] && CI_MODE=1 && touch data/ci-mode

echo "================================================================"
echo " text-editing-llm installer"
echo " This takes 20-60 minutes the first time (mostly downloading)."
echo " You can stop it at any time and run the same command again."
echo "================================================================"

if [ "$CI_MODE" = 0 ]; then
  # --- 1. Checks -----------------------------------------------------------
  say "Checking this computer"
  [ "$(id -u)" = 0 ] || fail "The installer needs administrator rights." "Run it as: sudo ./install.sh"
  if ! grep -qi ubuntu /etc/os-release; then
    info "This is not Ubuntu. The installer is tested on Ubuntu 22.04 and 24.04 and may not work here."
  fi
  lspci 2>/dev/null | grep -qi nvidia || fail "No NVIDIA graphics card was found." "This software needs an NVIDIA GPU."
  free_gb=$(df -BG --output=avail . | tail -1 | tr -dc 0-9)
  [ "$free_gb" -ge 100 ] || fail "Only ${free_gb} GB of disk space is free; 100 GB is needed." "Free up disk space, then run: sudo ./install.sh"
  internet_ok || fail "This computer cannot reach the internet." "Check the network connection, then run: sudo ./install.sh"
  if ! command -v curl >/dev/null; then
    { apt-get update -y && apt-get install -y curl ca-certificates; } || fail "A small tool (curl) could not be installed." "Check the network connection, then run: sudo ./install.sh"
  fi

  # --- 2. NVIDIA driver ------------------------------------------------------
  say "Checking the NVIDIA driver"
  drv=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1 || true)
  if [ -z "$drv" ] || ! driver_ok "$drv"; then
    info "The NVIDIA driver is missing or too old (found: ${drv:-none}; need ${MIN_DRIVER} or newer). Installing it now..."
    apt-get update -y && apt-get install -y ubuntu-drivers-common
    ubuntu-drivers install || fail "The NVIDIA driver could not be installed automatically." \
      "Install the latest NVIDIA driver from https://www.nvidia.com/drivers, restart, and run: sudo ./install.sh"
    echo
    echo "The NVIDIA driver was installed. The computer must restart now."
    echo "If a blue 'MOK management' screen appears while restarting, choose 'Enroll MOK',"
    echo "then 'Continue', and type the password you were asked to choose."
    echo "After the restart, open a terminal in this folder and run again:  sudo ./install.sh"
    exit 0
  fi
  info "Driver $drv is fine."

  # --- 3. Docker and the NVIDIA container support --------------------------------
  if ! step_done docker; then
    say "Installing Docker (the software that runs the assistant)"
    if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
      apt-get update -y && apt-get install -y ca-certificates curl gnupg
      install -m 0755 -d /etc/apt/keyrings
      curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
      chmod a+r /etc/apt/keyrings/docker.asc
      # shellcheck disable=SC1091
      echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
      apt-get update -y
      apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    fi
    if ! command -v nvidia-ctk >/dev/null; then
      curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
      curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
        > /etc/apt/sources.list.d/nvidia-container-toolkit.list
      apt-get update -y && apt-get install -y nvidia-container-toolkit
    fi
    nvidia-ctk runtime configure --runtime=docker >/dev/null
    systemctl enable --now docker >/dev/null 2>&1 || true
    systemctl restart docker
    if [ -n "${SUDO_USER:-}" ]; then usermod -aG docker "$SUDO_USER" || true; fi
    mark_done docker
  fi
  # shellcheck disable=SC1091
  LLAMA_IMAGE=$(grep '^LLAMA_IMAGE=' config/versions.env | cut -d= -f2)
  say "Checking that Docker can use the graphics card"
  docker run --rm --gpus all --entrypoint nvidia-smi "$LLAMA_IMAGE" -L >/dev/null \
    || fail "Docker cannot use the graphics card." "Restart the computer, then run: sudo ./install.sh. If it still fails, see docs/admin-guide.md, 'Troubleshooting'."
fi

# --- 4. Settings and passwords (first time only) -----------------------------
if [ ! -f .env ]; then
  say "Setting up the administrator account"
  if [ "$CI_MODE" = 1 ]; then
    ADMIN_EMAIL=${CI_ADMIN_EMAIL:-admin@example.com}
    ADMIN_PASSWORD=${CI_ADMIN_PASSWORD:-ci-password-1}
  else
    echo "You will log in to the assistant with this email and password."
    ask_email
    ask_password
  fi
  SITE_ADDRESSES=$(site_addresses_from "$(hostname)" "$(hostname -I 2>/dev/null || true)")
  write_env_once
fi

# --- 5. Download and start -----------------------------------------------------
say "Downloading the software (a few GB)"
dc pull --ignore-buildable --quiet || fail "The software could not be downloaded." "Check the internet connection and run the same command again."
dc build --quiet setup

say "Preparing the AI model (about 17 GB; this is the longest step)"
dc run --rm setup || fail "The AI model could not be prepared." "Run the same command again; the download continues where it stopped."

say "Starting the assistant (the first start measures the graphics card and can take 10-20 minutes)"
dc up -d || fail "The assistant could not be started." "Run: ./textedit doctor   and follow what it says."
wait_healthy llama 60 || fail "The AI model did not start." "Run: ./textedit doctor   and follow what it says."
wait_healthy webui 20 || fail "The web page did not start." "Run: ./textedit doctor   and follow what it says."

say "Installing the editing presets"
dc run --rm seed || fail "The editing presets could not be installed." "Run: sudo ./install.sh   again."
forget_admin_password
mark_done installed

echo
echo "================================================================"
echo " Done! The assistant is running."
echo
echo " Open one of these addresses in a web browser (on this network):"
show_addresses
echo
echo " The browser will warn that the connection is not private the first"
echo " time. This is expected: click 'Advanced', then 'Continue'."
echo
echo " Log in with the administrator email and password you just chose,"
echo " then add your colleagues: see docs/admin-guide.md"
echo
echo " Useful commands:  ./textedit status   ./textedit doctor"
echo "================================================================"
