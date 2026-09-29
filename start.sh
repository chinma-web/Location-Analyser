#!/usr/bin/env bash
#
# Start the Location Analyser web app.
#
#   ./start.sh                  start in the background (default)
#   ./start.sh --foreground     run in this terminal, Ctrl-C to stop
#   ./start.sh --port 8600      use a different port
#   ./start.sh --skip-install   don't touch the virtualenv (fast restart)
#
# Creates .venv and installs requirements on first run. Writes the PID to
# .run/app.pid and logs to .run/app.log so stop.sh can find it.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# ── Defaults (override with flags or environment) ─────────────────────────────
PORT="${PORT:-8501}"
HOST="${HOST:-0.0.0.0}"
VENV_DIR="${VENV_DIR:-.venv}"
RUN_DIR=".run"
PID_FILE="$RUN_DIR/app.pid"
LOG_FILE="$RUN_DIR/app.log"
FOREGROUND=0
SKIP_INSTALL=0

# ── Colours (disabled when not a terminal) ────────────────────────────────────
if [ -t 1 ]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; YELLOW=""; RED=""; DIM=""; RESET=""
fi

info()  { printf '%s\n' "${DIM}·${RESET} $*"; }
ok()    { printf '%s\n' "${GREEN}✓${RESET} $*"; }
warn()  { printf '%s\n' "${YELLOW}⚠${RESET} $*"; }
fail()  { printf '%s\n' "${RED}✗${RESET} $*" >&2; exit 1; }

usage() {
  sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
}

# ── Arguments ─────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    -f|--foreground)   FOREGROUND=1; shift ;;
    -p|--port)         PORT="${2:?--port needs a value}"; shift 2 ;;
    --port=*)          PORT="${1#*=}"; shift ;;
    --host)            HOST="${2:?--host needs a value}"; shift 2 ;;
    --host=*)          HOST="${1#*=}"; shift ;;
    -s|--skip-install) SKIP_INSTALL=1; shift ;;
    -h|--help)         usage ;;
    *)                 fail "Unknown option: $1  (try --help)" ;;
  esac
done

mkdir -p "$RUN_DIR"

# ── Already running? ──────────────────────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
  EXISTING_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    warn "Already running (PID $EXISTING_PID). Use ./stop.sh first, or ./stop.sh && ./start.sh"
    exit 1
  fi
  info "Removing stale PID file"
  rm -f "$PID_FILE"
fi

# ── Python ────────────────────────────────────────────────────────────────────
PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then PYTHON_BIN="$candidate"; break; fi
  done
fi
[ -n "$PYTHON_BIN" ] || fail "No python3 found. Install Python 3.10 or newer."

"$PYTHON_BIN" - <<'PY' || fail "Python 3.10+ is required (found an older interpreter)."
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY

# ── Virtualenv + dependencies ─────────────────────────────────────────────────
if [ "$SKIP_INSTALL" -eq 0 ]; then
  if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtualenv in $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR" || fail "Could not create the virtualenv."
  fi
fi
[ -x "$VENV_DIR/bin/python" ] || fail "No interpreter at $VENV_DIR/bin/python. Re-run without --skip-install."
VENV_PY="$VENV_DIR/bin/python"

if [ "$SKIP_INSTALL" -eq 0 ]; then
  # Only reinstall when requirements.txt is newer than the last successful run.
  STAMP="$RUN_DIR/.deps-installed"
  if [ ! -f "$STAMP" ] || [ requirements.txt -nt "$STAMP" ]; then
    info "Installing dependencies (this can take a minute on first run)"
    "$VENV_PY" -m pip install --quiet --upgrade pip
    "$VENV_PY" -m pip install --quiet -r requirements.txt || fail "Dependency installation failed."
    touch "$STAMP"
    ok "Dependencies installed"
  else
    info "Dependencies already up to date ${DIM}(requirements.txt unchanged)${RESET}"
  fi
fi

# ── Credentials ───────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  warn "No .env file found."
  if [ -f .env.example ]; then
    info "Copy the template and fill in your keys:  cp .env.example .env"
  fi
fi

MISSING="$("$VENV_PY" - <<'PY' 2>/dev/null || true
try:
    from locan.config import missing_credentials
    print(",".join(missing_credentials()))
except Exception:
    pass
PY
)"
if [ -n "$MISSING" ]; then
  warn "Missing API keys: ${BOLD}${MISSING}${RESET}"
  warn "The app will start and explain what is missing, but analyses will not run."
fi

# ── Port already taken? ───────────────────────────────────────────────────────
if "$VENV_PY" - "$PORT" <<'PY'
import socket, sys
with socket.socket() as probe:
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sys.exit(0 if probe.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
then
  fail "Port $PORT is already in use. Stop that process, or start with --port 8600."
fi

# ── Launch ────────────────────────────────────────────────────────────────────
STREAMLIT_ARGS=(
  -m streamlit run app.py
  --server.port "$PORT"
  --server.address "$HOST"
  --server.headless true
  --browser.gatherUsageStats false
)

if [ "$FOREGROUND" -eq 1 ]; then
  ok "Starting in the foreground on http://localhost:$PORT  ${DIM}(Ctrl-C to stop)${RESET}"
  exec "$VENV_PY" "${STREAMLIT_ARGS[@]}"
fi

info "Starting Location Analyser…"
nohup "$VENV_PY" "${STREAMLIT_ARGS[@]}" >"$LOG_FILE" 2>&1 &
APP_PID=$!
echo "$APP_PID" >"$PID_FILE"

# Wait for the port to accept connections rather than sleeping a fixed amount.
for _ in $(seq 1 60); do
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    rm -f "$PID_FILE"
    printf '%s\n' "${DIM}--- last 20 log lines ---${RESET}"
    tail -n 20 "$LOG_FILE" || true
    fail "The app exited during startup. Full log: $LOG_FILE"
  fi
  if "$VENV_PY" - "$PORT" <<'PY'
import socket, sys
with socket.socket() as probe:
    probe.settimeout(1)
    sys.exit(0 if probe.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
  then
    ok "Running on ${BOLD}http://localhost:$PORT${RESET}  ${DIM}(PID $APP_PID)${RESET}"
    info "Logs:  tail -f $LOG_FILE"
    info "Stop:  ./stop.sh"
    exit 0
  fi
  sleep 0.5
done

fail "Timed out waiting for port $PORT. Check $LOG_FILE (the process is still running as PID $APP_PID)."
