#!/usr/bin/env bash
# Shared helpers for install.sh and textedit. Plain-English messages only.

LOG_FILE=${LOG_FILE:-data/install.log}
MIN_DRIVER=570

say()  { printf '\n==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }

# fail "what went wrong" "what to do"
fail() {
  printf '\n!!! %s\n' "$1" >&2
  [ -n "${2:-}" ] && printf '    What to do: %s\n' "$2" >&2
  printf '    Full details are in: %s\n\n' "$LOG_FILE" >&2
  exit 1
}

valid_email() { [[ "$1" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]]; }

ask_email() {
  while true; do
    printf 'Administrator email (used to log in): '
    IFS= read -r ADMIN_EMAIL || fail "No email was entered." "Run the installer again and type an email."
    ADMIN_EMAIL=${ADMIN_EMAIL//[[:space:]]/}
    if valid_email "$ADMIN_EMAIL"; then
      return 0
    fi
    echo "That does not look like an email address. Please try again."
  done
}

ask_password() {
  local again
  while true; do
    printf 'Choose an administrator password (at least 8 characters, hidden while typing): '
    IFS= read -rs ADMIN_PASSWORD || fail "No password was entered." "Run the installer again."
    echo
    if [ "${#ADMIN_PASSWORD}" -lt 8 ]; then
      echo "The password must be at least 8 characters. Please try again."
      continue
    fi
    if [[ "$ADMIN_PASSWORD" =~ [[:space:]\$\#\'\"\\\`] ]]; then
      echo "The password cannot contain spaces or any of these characters: \$ # ' \" \\ \`  Please choose another."
      continue
    fi
    printf 'Type the same password again: '
    IFS= read -rs again || fail "No password was entered." "Run the installer again."
    echo
    if [ "$again" != "$ADMIN_PASSWORD" ]; then
      echo "The two passwords did not match. Please try again."
      continue
    fi
    return 0
  done
}

random_string() { # length
  LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "$1"
}

# Writes .env and data/secrets/llama_key the first time only.
write_env_once() {
  if [ -f .env ] && grep -q '^WEBUI_SECRET_KEY=' .env; then
    return 0
  fi
  umask 077
  mkdir -p data/secrets
  local key
  key=$(random_string 40)
  printf '%s\n' "$key" > data/secrets/llama_key
  {
    echo "# Created by the installer. Keep this file private; never share or commit it."
    echo "WEBUI_SECRET_KEY=$(random_string 48)"
    echo "LLAMA_API_KEY=$key"
    echo "WEBUI_ADMIN_EMAIL=$ADMIN_EMAIL"
    echo "WEBUI_ADMIN_PASSWORD=$ADMIN_PASSWORD"
    echo "SITE_ADDRESSES=$SITE_ADDRESSES"
  } > .env
  chmod 600 .env data/secrets/llama_key
}

# Removes the one-time admin password from .env once setup is finished.
forget_admin_password() {
  [ -f .env ] && sed -i 's/^WEBUI_ADMIN_PASSWORD=.*/WEBUI_ADMIN_PASSWORD=/' .env
}

site_addresses_from() { # hostname "ip list"
  local out="https://$1.local" ip
  for ip in $2; do
    case "$ip" in
      172.1[6-9].*|172.2[0-9].*|172.3[01].*|127.*|*:*) continue ;; # Docker/loopback/IPv6
    esac
    out="$out, https://$ip"
  done
  echo "$out, https://localhost"
}

# True when huggingface.co can be reached (works with curl or wget; fresh Ubuntu desktops lack curl).
internet_ok() {
  if command -v curl >/dev/null 2>&1; then
    curl -sfI --max-time 20 https://huggingface.co >/dev/null
  else
    wget -q --spider --timeout=20 https://huggingface.co
  fi
}

driver_ok() { # driver version string
  local major=${1%%.*}
  [[ "$major" =~ ^[0-9]+$ ]] && [ "$major" -ge "$MIN_DRIVER" ]
}

step_done() { [ -f data/install-state ] && grep -qx "$1" data/install-state; }
mark_done() { mkdir -p data && echo "$1" >> data/install-state; }

# docker compose with this project's settings files
dc() {
  local files=(-f compose.yaml)
  [ -f data/ci-mode ] && files+=(-f compose.ci.yaml)
  docker compose --env-file config/versions.env --env-file config/defaults.env --env-file .env "${files[@]}" "$@"
}

# Address users open in their browser
show_addresses() {
  local port addr
  port=$(grep '^HTTPS_PORT=' config/defaults.env | cut -d= -f2)
  [ -f data/ci-mode ] && port=8443
  addr=$(grep '^SITE_ADDRESSES=' .env | cut -d= -f2-)
  IFS=',' read -ra list <<< "$addr"
  for a in "${list[@]}"; do
    a=${a// /}
    if [ "$port" = "443" ]; then echo "      $a"; else echo "      $a:$port"; fi
  done
}

wait_healthy() { # service, minutes
  local i=0 status
  while [ "$i" -lt $(( $2 * 6 )) ]; do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$(dc ps -q "$1" 2>/dev/null)" 2>/dev/null || true)
    [ "$status" = "healthy" ] && return 0
    sleep 10
    i=$((i + 1))
    if [ $((i % 6)) -eq 0 ]; then info "Still starting ($((i / 6)) min)..."; fi
  done
  return 1
}
