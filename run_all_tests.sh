#!/usr/bin/env bash
# Run every test, in order. Stops at the first failure.
#   1. Unit tests
#   2. Integration tests
#   3. End-to-end tests in a real browser (they start their own copy of the app)
#   4. Mutation check: plant mistakes one at a time, the tests must fail for each
set -euo pipefail

cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

step() { printf '\n==> %s\n' "$1"; }

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Run ./setup.sh first."
  exit 1
fi

step "1/4 Unit tests"
uv run pytest tests/unit -q

step "2/4 Integration tests"
uv run pytest tests/integration -q

step "3/4 End-to-end tests in a real browser"
if ! uv run pytest tests/e2e -q; then
  echo "If the browser is missing, run ./setup.sh and try again."
  exit 1
fi

step "4/4 Mutation check"
uv run python tests/mutation_check.py

printf '\nAll tests passed.\n'
