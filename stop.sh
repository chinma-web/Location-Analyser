#!/usr/bin/env bash
#
# Stop the Location Analyser web app started by start.sh.
#
#   ./stop.sh              graceful shutdown (SIGTERM, then SIGKILL)
#   ./stop.sh --force      skip straight to SIGKILL
#   ./stop.sh --port 8600  also stop whatever is listening on that port
#
# Exits 0 when nothing is running, so it is safe in scripts and Makefiles.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

PORT="${PORT:-8501}"
RUN_DIR=".run"
PID_FILE="$RUN_DIR/app.pid"
LOG_FILE="$RUN_DIR/app.log"
FORCE=0
GRACE_SECONDS=10

if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; DIM=""; RESET=""
fi

info() { printf '%s\n' "${DIM}·${RESET} $*"; }
ok()   { printf '%s\n' "${GREEN}✓${RESET} $*"; }
warn() { printf '%s\n' "${YELLOW}⚠${RESET} $*"; }

usage() {
  sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    -f|--force) FORCE=1; shift ;;
    -p|--port)  PORT="${2:?--port needs a value}"; shift 2 ;;
    --port=*)   PORT="${1#*=}"; shift ;;
    -h|--help)  usage ;;
    *)          warn "Unknown option: $1  (try --help)"; exit 1 ;;
  esac
done

# Send a signal to a PID and report whether it was still alive.
signal_pid() {
  local pid="$1" signal="$2"
  kill -"$signal" "$pid" 2>/dev/null
}

stop_pid() {
  local pid="$1" label="$2"

  if ! kill -0 "$pid" 2>/dev/null; then
    return 1
  fi

  if [ "$FORCE" -eq 1 ]; then
    signal_pid "$pid" KILL || true
    ok "Killed $label ${DIM}(PID $pid, SIGKILL)${RESET}"
    return 0
  fi

  info "Stopping $label ${DIM}(PID $pid)${RESET}"
  signal_pid "$pid" TERM || true

  for _ in $(seq 1 $((GRACE_SECONDS * 2))); do
    if ! kill -0 "$pid" 2>/dev/null; then
      ok "Stopped $label"
      return 0
    fi
    sleep 0.5
  done

  warn "$label did not exit after ${GRACE_SECONDS}s — sending SIGKILL"
  signal_pid "$pid" KILL || true
  sleep 0.5
  if kill -0 "$pid" 2>/dev/null; then
    warn "PID $pid is still alive. It may belong to another user."
    return 2
  fi
  ok "Killed $label"
}

STOPPED_ANY=0

# ── 1. The PID recorded by start.sh ───────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$PID" ] && stop_pid "$PID" "Location Analyser"; then
    STOPPED_ANY=1
  else
    info "PID file pointed at a process that was no longer running"
  fi
  rm -f "$PID_FILE"
fi

# ── 2. Anything else still holding the port ───────────────────────────────────
# Covers a run started by hand (streamlit run app.py) or a stale child process.
PORT_PIDS=""
if command -v lsof >/dev/null 2>&1; then
  PORT_PIDS="$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
elif command -v fuser >/dev/null 2>&1; then
  PORT_PIDS="$(fuser "$PORT"/tcp 2>/dev/null | tr -s ' ' '\n' | tr -d ' ' || true)"
elif command -v ss >/dev/null 2>&1; then
  PORT_PIDS="$(ss -lptnH "sport = :$PORT" 2>/dev/null \
               | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u || true)"
fi

for PID in $PORT_PIDS; do
  [ "$PID" = "$$" ] && continue
  if stop_pid "$PID" "process on port $PORT"; then
    STOPPED_ANY=1
  fi
done

# ── Result ────────────────────────────────────────────────────────────────────
if [ "$STOPPED_ANY" -eq 1 ]; then
  ok "Location Analyser is ${BOLD}stopped${RESET}"
  [ -f "$LOG_FILE" ] && info "Last log kept at $LOG_FILE"
  exit 0
fi

info "Nothing to stop — no app running on port $PORT"
exit 0
