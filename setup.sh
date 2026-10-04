#!/usr/bin/env bash
# Set up everything this project needs on a Mac. Safe to run again: each step checks first.
#
# What it does, and nothing else:
#   1. Makes sure uv is available. If it is missing, installs it for the current user:
#      with Homebrew if you have it, otherwise with uv's own installer into ~/.local/bin.
#   2. Installs Python and the project's packages into .venv inside this folder.
#   3. Downloads the browser for the end-to-end tests into Playwright's own cache folder.
#
# It never uses sudo, never edits your shell profile, never installs Homebrew, and never
# touches anything outside this folder, ~/.local/bin and the uv and Playwright caches.
set -euo pipefail

cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

step() { printf '\n==> %s\n' "$1"; }

if [ "$(uname -s)" != "Darwin" ]; then
  echo "Note: this script is written for macOS. Continuing anyway."
fi

step "uv"
if command -v uv >/dev/null 2>&1; then
  echo "Already installed: $(uv --version)"
elif command -v brew >/dev/null 2>&1; then
  echo "Installing uv with Homebrew."
  HOMEBREW_NO_AUTO_UPDATE=1 brew install uv
else
  echo "Installing uv into ~/.local/bin with its official installer."
  curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
  echo "The scripts in this folder find it there. To use uv yourself, add ~/.local/bin to your PATH."
fi

step "Python and packages, into .venv in this folder"
uv sync --locked

step "Browser for the end-to-end tests"
uv run playwright install chromium

step "Ready"
echo "$(uv run python --version), $(uv --version)"
echo "Next: ./run_server.sh, ./run_all_tests.sh or ./cicd.sh"
