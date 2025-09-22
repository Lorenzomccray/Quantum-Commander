#!/usr/bin/env bash
set -euo pipefail

# Start Quantum Commander backend using the repo-local virtualenv and .env
# Logs go to journald when run under systemd; when run manually, they go to stdout.

REPO="/home/lorenzomccray/quantum-commander"
cd "$REPO"

# Load environment if present (non-fatal)
if [ -f "$REPO/.env" ]; then
  # shellcheck disable=SC2046
  export $(grep -v '^#' "$REPO/.env" | xargs) || true
fi

# Ensure venv exists
if [ ! -x "$REPO/.venv/bin/python" ]; then
  echo "Backend venv missing; creating..." >&2
  python3 -m venv "$REPO/.venv"
  "$REPO/.venv/bin/pip" install -U pip wheel
  "$REPO/.venv/bin/pip" install -r "$REPO/requirements.txt"
fi

exec "$REPO/.venv/bin/python" -m commander.commander web
