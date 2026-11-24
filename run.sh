#!/usr/bin/env bash
# Start Temporal (local dev server), the worker, and the Streamlit app.
# No cloud account. No real Slack.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
DATA="$ROOT/data"
BIN="$ROOT/bin"
mkdir -p "$DATA" "$BIN"

CLI_VERSION="1.10.1"
CLI_URL="https://github.com/temporalio/cli/releases/download/v${CLI_VERSION}/temporal_cli_${CLI_VERSION}_linux_amd64.tar.gz"

if [[ ! -x "$BIN/temporal" ]]; then
  echo "Downloading Temporal CLI v${CLI_VERSION} (local dev server, no signup)…"
  tmp="$(mktemp -d)"
  curl -sL "$CLI_URL" -o "$tmp/temporal.tar.gz"
  tar -xzf "$tmp/temporal.tar.gz" -C "$tmp"
  mv "$tmp/temporal" "$BIN/temporal"
  chmod +x "$BIN/temporal"
  rm -rf "$tmp"
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

if [[ ! -f .venv/bin/python ]]; then
  echo "Could not find .venv/bin/python" >&2
  exit 1
fi

export TEMPORAL_ADDRESS="${TEMPORAL_ADDRESS:-127.0.0.1:7233}"
export TEMPORAL_PORT="${TEMPORAL_PORT:-7233}"
export TEMPORAL_UI_PORT="${TEMPORAL_UI_PORT:-8233}"
export TEMPORAL_HTTP_PORT="${TEMPORAL_HTTP_PORT:-7243}"
export TEMPORAL_METRICS_PORT="${TEMPORAL_METRICS_PORT:-7253}"
export APPROVAL_GATE_TASK_QUEUE="${APPROVAL_GATE_TASK_QUEUE:-approval-gate}"
export APPROVAL_GATE_DATA="$DATA"
export APPROVAL_GATE_DB="$DATA/approval_gate.db"
export TEMPORAL_DB="$DATA/temporal.db"
export STREAMLIT_PORT="${STREAMLIT_PORT:-8501}"

wait_port() {
  local port="$1"
  local tries=0
  while ! python3 -c "import socket; s=socket.create_connection(('127.0.0.1', $port), 0.4); s.close()" 2>/dev/null; do
    tries=$((tries + 1))
    if [[ "$tries" -gt 80 ]]; then
      echo "Timed out waiting for port $port" >&2
      exit 1
    fi
    sleep 0.25
  done
}

cleanup() {
  if [[ -n "${WORKER_PID:-}" ]] && kill -0 "$WORKER_PID" 2>/dev/null; then
    kill "$WORKER_PID" 2>/dev/null || true
  fi
  if [[ -n "${TEMPORAL_PID:-}" ]] && kill -0 "$TEMPORAL_PID" 2>/dev/null; then
    kill "$TEMPORAL_PID" 2>/dev/null || true
  fi
  rm -f "$DATA/worker.pid" "$DATA/temporal.pid"
}
trap cleanup EXIT INT TERM

if ! python3 -c "import socket; s=socket.create_connection(('127.0.0.1', ${TEMPORAL_PORT}), 0.4); s.close()" 2>/dev/null; then
  echo "Starting Temporal dev server on port ${TEMPORAL_PORT}…"
  "$BIN/temporal" server start-dev \
    --ip 127.0.0.1 \
    --port "$TEMPORAL_PORT" \
    --ui-port "$TEMPORAL_UI_PORT" \
    --http-port "$TEMPORAL_HTTP_PORT" \
    --metrics-port "$TEMPORAL_METRICS_PORT" \
    --db-filename "$TEMPORAL_DB" \
    >"$DATA/temporal.log" 2>&1 &
  TEMPORAL_PID=$!
  echo "$TEMPORAL_PID" >"$DATA/temporal.pid"
  wait_port "$TEMPORAL_PORT"
else
  echo "Temporal already looks up on port ${TEMPORAL_PORT}; reusing it."
  TEMPORAL_PID=""
fi

echo "Starting approval-gate worker…"
.venv/bin/python -m approvalgate worker >"$DATA/worker.log" 2>&1 &
WORKER_PID=$!
echo "$WORKER_PID" >"$DATA/worker.pid"
sleep 0.8
if ! kill -0 "$WORKER_PID" 2>/dev/null; then
  echo "Worker failed to start. Tail of data/worker.log:" >&2
  tail -n 40 "$DATA/worker.log" >&2
  exit 1
fi

echo
echo "Approval gate is ready."
echo "  App:         http://127.0.0.1:${STREAMLIT_PORT}"
echo "  Temporal UI: http://127.0.0.1:${TEMPORAL_UI_PORT}"
echo "  Crash test:  .venv/bin/python -m approvalgate crash-test"
echo

exec .venv/bin/streamlit run app.py --server.headless true --server.port "$STREAMLIT_PORT" --server.address 127.0.0.1
