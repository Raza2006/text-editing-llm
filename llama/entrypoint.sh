#!/bin/sh
# Starts llama-server. On the first start it finds the largest shared context
# pool that fits on this GPU and saves it, so later starts are immediate.
# Set REPROBE=1 to measure again (textedit doctor --reprobe does this).
set -u

LLAMA_BIN=${LLAMA_BIN:-/app/llama-server}
MODELS_DIR=${MODELS_DIR:-/models}
STATE_DIR=${STATE_DIR:-/state}
API_KEY_FILE=${API_KEY_FILE:-/run/secrets/llama_key}
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-900}
CTX_CANDIDATES=${CTX_CANDIDATES:-524288 458752 393216 327680 262144}
CTX_MAX_PER_CHAT=${CTX_MAX_PER_CHAT:-262144}
MIN_FREE_MIB=${MIN_FREE_MIB:-2048}
PARALLEL=${PARALLEL:-8}
CPU_ONLY=${CPU_ONLY:-0}

say() { echo "[model] $*"; }

if [ ! -f "$MODELS_DIR/selected.env" ]; then
  say "ERROR: No model has been prepared yet. Run the installer again."
  exit 2
fi
# shellcheck disable=SC1091
. "$MODELS_DIR/selected.env"

start_server() {
  ctx=$1
  gpu_flags="-ngl 99"
  [ "$CPU_ONLY" = "1" ] && gpu_flags=""
  # shellcheck disable=SC2086
  "$LLAMA_BIN" -m "$MODELS_DIR/$MODEL_FILE" --alias "$MODEL_ALIAS" \
    -c "$ctx" --parallel "$PARALLEL" --kv-unified -fa on -ctk q8_0 -ctv q8_0 \
    --reasoning off --jinja --no-webui --api-key-file "$API_KEY_FILE" \
    --host 0.0.0.0 --port 8080 $gpu_flags &
  SERVER_PID=$!
}

wait_healthy() {
  waited=0
  while [ "$waited" -lt "$HEALTH_TIMEOUT" ]; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      return 1
    fi
    if curl -sf http://127.0.0.1:8080/health >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}

stop_server() {
  kill "$SERVER_PID" 2>/dev/null
  wait "$SERVER_PID" 2>/dev/null
}

free_mib() {
  nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -n 1 | tr -d ' '
}

save_choice() {
  ctx=$1
  per_chat=$((ctx / 2))
  [ "$per_chat" -gt "$CTX_MAX_PER_CHAT" ] && per_chat=$CTX_MAX_PER_CHAT
  mkdir -p "$STATE_DIR"
  printf 'CTX=%s\nPER_CHAT=%s\n' "$ctx" "$per_chat" > "$STATE_DIR/ctx.env.tmp"
  mv "$STATE_DIR/ctx.env.tmp" "$STATE_DIR/ctx.env"
}

trap 'stop_server; exit 0' TERM INT

if [ -f "$STATE_DIR/ctx.env" ] && [ -z "${REPROBE:-}" ]; then
  # shellcheck disable=SC1091
  . "$STATE_DIR/ctx.env"
  say "Starting with a shared context of $CTX tokens."
  start_server "$CTX"
  wait "$SERVER_PID"
  exit $?
fi

for ctx in $CTX_CANDIDATES; do
  say "Trying a shared context of $ctx tokens..."
  start_server "$ctx"
  if ! wait_healthy; then
    say "That does not fit. Trying a smaller size."
    stop_server
    continue
  fi
  if [ "$CPU_ONLY" != "1" ]; then
    free=$(free_mib)
    if [ "$free" -lt "$MIN_FREE_MIB" ]; then
      say "That leaves only $free MiB of GPU memory free. Trying a smaller size."
      stop_server
      continue
    fi
    say "Loaded, with $free MiB of GPU memory still free."
  fi
  save_choice "$ctx"
  say "Chosen: shared context of $ctx tokens. Ready."
  wait "$SERVER_PID"
  exit $?
done

say "ERROR: The model does not fit on this GPU even with the smallest setting. Run: textedit doctor"
exit 3
