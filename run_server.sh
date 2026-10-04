#!/usr/bin/env bash
# Run the app. Stop it with Ctrl+C.
#
# It asks two questions, and Enter accepts the default for each:
#   1. Which ledger file. It lists the .json files in this folder and in tests/data.
#      The default is the original ledger.json.
#   2. Which port. The default is the first free port from 5001 upwards.
#
# To skip a question, set its answer:
#   LEDGER_FILE=tests/data/ledger_warnings.json PORT=5002 ./run_server.sh
# Nothing is asked when the script is not run from a terminal.
set -euo pipefail

cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

DEFAULT_LEDGER="ledger.json"
FIRST_PORT=5001

port_is_free() {
  ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Run ./setup.sh first."
  exit 1
fi

if [ -n "${PORT:-}" ] && ! port_is_free "$PORT"; then
  echo "Port $PORT is already in use:"
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN
  echo "Run this again without PORT to have a free port picked."
  exit 1
fi

interactive=false
if [ -t 0 ]; then
  interactive=true
fi

# --- 1. The ledger file
if [ -z "${LEDGER_FILE:-}" ] && $interactive; then
  files=()
  if [ -f "$DEFAULT_LEDGER" ]; then
    files+=("$DEFAULT_LEDGER")
  fi
  for file in *.json tests/data/*.json; do
    if [ -f "$file" ] && [ "$file" != "$DEFAULT_LEDGER" ]; then
      files+=("$file")
    fi
  done
  if [ "${#files[@]}" -eq 0 ]; then
    echo "No ledger files found in this folder or in tests/data."
    exit 1
  fi

  echo "Which ledger file?"
  number=1
  for file in "${files[@]}"; do
    echo "  $number) $file"
    number=$((number + 1))
  done

  while true; do
    read -r -p "Number, or Enter for 1: " answer || { echo; exit 1; }
    answer="${answer:-1}"
    if [[ "$answer" =~ ^[0-9]+$ ]] && [ "$answer" -ge 1 ] && [ "$answer" -le "${#files[@]}" ]; then
      LEDGER_FILE="${files[$((answer - 1))]}"
      break
    fi
    echo "Please type a number from 1 to ${#files[@]}."
  done
fi

export LEDGER_FILE="${LEDGER_FILE:-$DEFAULT_LEDGER}"
if [ ! -f "$LEDGER_FILE" ]; then
  echo "Ledger file not found: $LEDGER_FILE"
  exit 1
fi

# --- 2. The port
if [ -z "${PORT:-}" ]; then
  PORT="$FIRST_PORT"
  while ! port_is_free "$PORT"; do
    PORT=$((PORT + 1))
    if [ "$PORT" -gt $((FIRST_PORT + 100)) ]; then
      echo "No free port found from $FIRST_PORT to $((FIRST_PORT + 100))."
      exit 1
    fi
  done
  if [ "$PORT" != "$FIRST_PORT" ]; then
    echo "Port $FIRST_PORT is in use. The first free port is $PORT."
  fi

  if $interactive; then
    while true; do
      read -r -p "Port, or Enter for $PORT: " answer || { echo; exit 1; }
      if [ -z "$answer" ]; then
        break
      fi
      if ! [[ "$answer" =~ ^[0-9]+$ ]] || [ "$answer" -lt 1024 ] || [ "$answer" -gt 65535 ]; then
        echo "Please type a port number from 1024 to 65535."
        continue
      fi
      if ! port_is_free "$answer"; then
        echo "Port $answer is already in use."
        continue
      fi
      PORT="$answer"
      break
    done
  fi
fi

echo "Ledger: $LEDGER_FILE"
echo "Income statement: http://127.0.0.1:$PORT/"
exec uv run flask --app app run --port "$PORT"
