#!/usr/bin/env bash
# Quantum Commander robust UI launcher
# Starts the service, waits for readiness, self-heals once, then opens the UI with fallbacks.
set -euo pipefail
URL_DEFAULT="http://127.0.0.1:8000/ui"
BASE="http://127.0.0.1:8000"
URL="${1:-$URL_DEFAULT}"
notify() { if command -v notify-send >/dev/null 2>&1; then notify-send "Assistant" "$1" || true; fi }
# 1) Ensure API is running
# Prefer socket activation (pre-binds port 8000)
systemctl --user start quantum-commander.socket || true

is_ready() {
  local ucode rcode
  ucode=$(curl -sS -m 1 -o /dev/null -w "%{http_code}" "$URL" || true)
  rcode=$(curl -sS -m 1 -o /dev/null -w "%{http_code}" "$BASE/ready" || true)
  if [ "$ucode" = "200" ] || [ "$rcode" = "200" ]; then return 0; fi
  return 1
}

wait_ready() {
  local limit="${1:-4}" elapsed=0.0; local step=0.2
  while awk "BEGIN{exit !($elapsed < $limit)}" 2>/dev/null; do
    if is_ready; then return 0; fi
    sleep "$step"; elapsed=$(awk -v e="$elapsed" -v s="$step" 'BEGIN{print e+s}')
    step=$(awk -v s="$step" 'BEGIN{v=s+0.05; if(v>0.5) v=0.5; print v;}')
  done
  return 1
}

# 2) Initial wait (4s). If not ready, self-heal once and wait up to 12s total
if ! wait_ready 4; then
  notify "Restarting backend…"
  systemctl --user restart quantum-commander.service || true
  wait_ready 12 || true
fi

# 3) Open browser (prefer Chrome app window); if not ready, open /basic as fallback
open_url() {
  local u="$1"
  if command -v google-chrome >/dev/null 2>&1; then
    nohup google-chrome --new-window --class=QuantumCommander --app="$u" >/dev/null 2>&1 & disown || true
    return 0
  fi
  if [ -x /opt/google/chrome/google-chrome ]; then
    nohup /opt/google/chrome/google-chrome --new-window --class=QuantumCommander --app="$u" >/dev/null 2>&1 & disown || true
    return 0
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    nohup xdg-open "$u" >/dev/null 2>&1 & disown || true
    return 0
  fi
  if command -v gio >/dev/null 2>&1; then
    nohup gio open "$u" >/dev/null 2>&1 & disown || true
    return 0
  fi
  if command -v firefox >/dev/null 2>&1; then
    nohup firefox -new-window "$u" >/dev/null 2>&1 & disown || true
    return 0
  fi
  printf "Could not find a browser to open %s\n" "$u" >&2
  exit 1
}

if is_ready; then
  open_url "$URL"
else
  notify "Opening fallback UI while backend warms…"
  open_url "$BASE/basic"
fi
exit 0
