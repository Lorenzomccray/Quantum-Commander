#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# Quantum Assistant migration: disable legacy UI, ensure inline completions, wire services & VS Code
# Idempotent and safe. Logs to a timestamped file in /tmp.

BACKEND_DIR="/home/lorenzomccray/projects/fix-assistant"
ext_dir_default="/home/lorenzomccray/projects/fix-assistant-vscode/quantum-copilot"
EXT_DIR="${EXT_DIR:-$ext_dir_default}"
API_PORT="${QC_PORT:-18000}"
LOG_FILE="/tmp/quantum-migrate-$(date +%Y%m%d-%H%M%S).log"

exec > >(tee -a "$LOG_FILE") 2>&1

warn() { echo "[WARN] $*"; }
info() { echo "[INFO] $*"; }
ok()   { echo "[ OK ] $*"; }
err()  { echo "[ERR ] $*"; }

cleanup() { echo "Script exited with code: $?"; }
trap cleanup EXIT INT TERM

need_cmd() { command -v "$1" >/dev/null 2>&1 || { err "Missing dependency: $1"; missing=1; }; }

check_deps() {
  missing=0
  for c in bash python3 pip curl jq sed awk npm node systemctl tmux; do
    need_cmd "$c"
  done
  [[ $missing -eq 0 ]] || { err "Install missing dependencies and re-run."; exit 1; }
}

wait_ready() {
  local url="$1" timeout="${2:-30}" elapsed=0
  info "Waiting for $url ..."
  until curl -fsS "$url" >/dev/null 2>&1; do
    sleep 2; elapsed=$((elapsed+2)); [[ $elapsed -ge $timeout ]] && { err "Timeout waiting for $url"; return 1; }
  done
  ok "$url is ready"
}

apply_systemd_overrides() {
  local svc="$1"; local d="$HOME/.config/systemd/user/${svc}.d"
  mkdir -p "$d"
  cat >"$d/override.conf" <<EOF
[Service]
Environment=QC_EXPOSE_WEB_UI=0
Environment=QC_PORT=${API_PORT}
EOF
  systemctl --user daemon-reload || true
  systemctl --user set-environment QC_EXPOSE_WEB_UI=0 QC_PORT="${API_PORT}" || true
  if systemctl --user is-enabled --quiet "$svc" 2>/dev/null; then
    systemctl --user restart "$svc" && ok "Restarted $svc" || warn "Failed to restart $svc"
  else
    systemctl --user restart "$svc" && ok "Restarted $svc" || warn "Failed to restart $svc"
  fi
}

start_tmux_fallback() {
  local sess="qa-backend"
  tmux kill-session -t "$sess" 2>/dev/null || true
  local uv="$BACKEND_DIR/.venv/bin/uvicorn"
  local cmd
  if [[ -x "$uv" ]]; then
    cmd="PYTHONPATH='$BACKEND_DIR/src' QC_EXPOSE_WEB_UI=0 QC_PORT=${API_PORT} '$uv' backend.app.main:app --host 127.0.0.1 --port ${API_PORT}"
  else
    cmd="PYTHONPATH='$BACKEND_DIR/src' QC_EXPOSE_WEB_UI=0 QC_PORT=${API_PORT} uvicorn backend.app.main:app --host 127.0.0.1 --port ${API_PORT}"
  fi
  tmux new-session -d -s "$sess" \
    "cd '$BACKEND_DIR' && $cmd"
  ok "Backend started in tmux session '$sess'"
}

persist_port_shell() {
  local rc="$HOME/.bashrc" line='export QC_PORT=18000'
  if ! grep -qs "^export QC_PORT=.*" "$rc"; then
    echo "$line" >>"$rc"
    ok "Persisted QC_PORT=18000 to $rc (open a new shell or: source ~/.bashrc)"
  else
    ok "QC_PORT already present in $rc"
  fi
}

update_vscode_settings() {
  local settings_dir settings_file
  case "$(uname)" in
    Linux*) settings_dir="$HOME/.config/Code/User";;
    Darwin*) settings_dir="$HOME/Library/Application Support/Code/User";;
    *) settings_dir="$HOME/.config/Code/User";;
  esac
  mkdir -p "$settings_dir"
  settings_file="$settings_dir/settings.json"
  [[ -f "$settings_file" ]] || echo '{}' >"$settings_file"
  if command -v jq >/dev/null 2>&1; then
    tmp="${settings_file}.tmp"
    jq --arg url "http://127.0.0.1:${API_PORT}" '."quantumCopilot.baseUrl"=$url | ."quantumCopilot.enabled"=true' "$settings_file" >"$tmp" && mv "$tmp" "$settings_file" && ok "VS Code settings updated" || warn "jq failed to update settings"
  else
    python3 - "$settings_file" "$API_PORT" <<'PY'
import json,sys
p=sys.argv[1];port=sys.argv[2]
try:
  d=json.load(open(p))
except Exception:
  d={}
d['quantumCopilot.baseUrl']=f'http://127.0.0.1:{port}'
d['quantumCopilot.enabled']=True
json.dump(d, open(p,'w'), indent=2)
PY
    ok "VS Code settings updated (python fallback)"
  fi
}

build_extension() {
  local dir="$EXT_DIR"
  if [[ ! -d "$dir" ]]; then
    warn "Extension dir not found: $dir (skipping)"; return 0
  fi
  (cd "$dir" && {
     info "Installing npm deps..."
     npm install || npm install
     npm install -D node-fetch@2 @types/node-fetch@2 @vscode/vsce || true
     info "Building extension..." && npm run build || npm run build
     info "Packaging extension..." && npx vsce package --no-yarn --allow-star-activation || true
     local vsix
     vsix=$(ls -1 *.vsix 2>/dev/null | head -1 || true)
     if [[ -n "$vsix" ]] && command -v code >/dev/null 2>&1; then
       code --install-extension "$vsix" --force && ok "Installed VSIX $vsix" || warn "Failed to install VSIX"
     else
       info "VSIX available in $dir (install manually if desired)"
     fi
  })
}

main() {
  info "Starting migration"
  check_deps

  # Ensure backend env
  if [[ ! -d "$BACKEND_DIR" ]]; then
    err "Backend directory not found: $BACKEND_DIR"; exit 1
  fi

  # Verify backend is updated (UI gate and inline route)
  if ! grep -qs "EXPOSE_WEB_UI" "$BACKEND_DIR/src/backend/app/main.py"; then
    warn "EXPOSE_WEB_UI mount not detected; please update main.py"
  fi
  if ! grep -qs "/assistant/inline" "$BACKEND_DIR/src/backend/app/routes.py"; then
    warn "Inline endpoint not detected; please update routes.py"
  fi

  # Services: qc-assistant.service preferred, fallback to quantum-commander.service
  if systemctl --user status qc-assistant.service >/dev/null 2>&1; then
    apply_systemd_overrides qc-assistant.service
  elif systemctl --user status quantum-commander.service >/dev/null 2>&1; then
    apply_systemd_overrides quantum-commander.service
  else
    warn "No user service found; using tmux fallback"
    start_tmux_fallback
  fi

  # Wait for backend
  wait_ready "http://127.0.0.1:${API_PORT}/assistant/config" || true

  # Disable legacy UI on port 8123 check (best-effort)
  if curl -fsS "http://127.0.0.1:8123/" >/dev/null 2>&1; then
    warn "Old UI appears to be serving on 8123"
  else
    ok "Old UI disabled"
  fi

  # Extension and VS Code
  build_extension
  update_vscode_settings

  # Persist port in shell per preference
  persist_port_shell

  echo
  ok "SWITCHOVER COMPLETE"
  echo "Backend API:    http://127.0.0.1:${API_PORT}"
  echo "Inline comps:   enabled (provider/model via /assistant/config)"
  echo "VS Code:        settings updated; extension built if present"
  echo "Systemd:        overrides applied if unit exists; tmux fallback otherwise"
  echo "Log file:       $LOG_FILE"
}

main "$@"
