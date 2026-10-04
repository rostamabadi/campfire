#!/usr/bin/env bash
# Everything a change must pass, in order. Stops at the first failure.
#   1. Lint: ruff, on the code and the tests
#   2. Types: mypy, on the application code
#   3. Every test: unit, integration, end-to-end, then the mutation check
set -euo pipefail

cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

step() { printf '\n==> %s\n' "$1"; }

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Run ./setup.sh first."
  exit 1
fi

step "Lint (ruff)"
uv run ruff check .

step "Types (mypy)"
uv run mypy

./run_all_tests.sh

printf '\nAll checks passed.\n'
