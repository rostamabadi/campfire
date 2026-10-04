#!/usr/bin/env bash
# Run the app on http://127.0.0.1:5001/. Stop it with Ctrl+C.
# Another port: PORT=5002 ./run_server.sh
set -euo pipefail

cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"
PORT="${PORT:-5001}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Run ./setup.sh first."
  exit 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use. The server may already be running:"
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN
  echo "Open http://127.0.0.1:$PORT/ or stop that process, then run this again."
  exit 1
fi

echo "Income statement: http://127.0.0.1:$PORT/"
exec uv run flask --app app run --port "$PORT"
