#!/usr/bin/env bash
set -euo pipefail
# Generate a systemd user service that runs gunicorn with Uvicorn workers.
# Usage: ./scripts/setup_gunicorn_service.sh [PORT]
# Default PORT=8000

PORT="${1:-8000}"
APP_DIR="$HOME/quantum-commander"
VENV="$APP_DIR/.venv"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_NAME="quantum-commander-gunicorn.service"

mkdir -p "$UNIT_DIR"
cat >"$UNIT_DIR/$UNIT_NAME" <<EOF
[Unit]
Description=Quantum Commander (gunicorn)
After=network-online.target

[Service]
WorkingDirectory=%h/quantum-commander
EnvironmentFile=%h/quantum-commander/.env
ExecStart=%h/quantum-commander/.venv/bin/gunicorn -k uvicorn.workers.UvicornWorker -w %CPU_CORES% -b 127.0.0.1:${PORT} --timeout 120 --graceful-timeout 30 --access-logfile - --error-logfile - 'commander.commander:app'
Restart=on-failure
RestartSec=2
KillSignal=SIGINT
TimeoutStopSec=20

[Install]
WantedBy=default.target
EOF

# Replace %CPU_CORES% with detected core count (min 2)
CORES=$(python - <<'PY'
import os
n=os.cpu_count() or 2
print(max(2, n))
PY
)
sed -i "s/%CPU_CORES%/${CORES}/" "$UNIT_DIR/$UNIT_NAME"

systemctl --user daemon-reload
systemctl --user enable --now "$UNIT_NAME"

printf "Created and started %s on 127.0.0.1:%s (workers=%s)\n" "$UNIT_NAME" "$PORT" "$CORES"
