#!/usr/bin/env bash
set -euo pipefail
APP="/home/lorenzomccray/quantum-commander"
OUT="$APP/_diagnostics"
TS="$(date +%Y%m%d-%H%M%S)"
B="$OUT/$TS"
mkdir -p "$B"
cd "$APP"

# --- System info ---
{ echo "=== SYSTEM ==="; uname -a; echo; hostnamectl || true; echo; cat /etc/os-release; } > "$B/system.txt"

# --- Git state (if repo) ---
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  { echo "=== GIT STATUS ==="; git status --porcelain=v1 -uall; echo;
    echo "=== RECENT COMMITS ==="; git --no-pager log --oneline -n 20; echo;
    echo "=== REMOTES ==="; git remote -v; } > "$B/git.txt"
fi

# --- Python / venv / requirements ---
if [ -d ".venv" ]; then
  . .venv/bin/activate
  { echo "=== PYTHON ==="; python -V; which python; echo;
    echo "=== PIP FREEZE ==="; pip freeze | sort; } > "$B/python.txt"
fi
cp -f requirements.txt "$B/requirements.txt" 2>/dev/null || true

# --- Services & logs (user units) ---
systemctl --user --no-pager --full status quantum-commander > "$B/quantum-commander.status.txt" 2>&1 || true
systemctl --user cat quantum-commander > "$B/quantum-commander.unit.txt" 2>&1 || true
journalctl --user -u quantum-commander -n 400 --no-pager > "$B/quantum-commander.journal.txt" 2>&1 || true

systemctl --user --no-pager --full status qc-blueprint-watcher.service > "$B/qc-blueprint-watcher.status.txt" 2>&1 || true
systemctl --user --no-pager --full status qc-blueprint-watcher.timer > "$B/qc-blueprint-watcher.timer.txt" 2>&1 || true
systemctl --user cat qc-blueprint-watcher.service > "$B/qc-blueprint-watcher.unit.txt" 2>&1 || true
systemctl --user cat qc-blueprint-watcher.timer > "$B/qc-blueprint-watcher.timer.unit.txt" 2>&1 || true
journalctl --user -u qc-blueprint-watcher -n 300 --no-pager > "$B/qc-blueprint-watcher.journal.txt" 2>&1 || true

# --- Processes & ports ---
ss -tulpn > "$B/ss.txt" 2>&1 || true
ps -u "$(id -u)" -o pid,ppid,stime,cmd > "$B/ps.txt"

# --- App endpoints ---
curl -sS http://127.0.0.1:8000/health > "$B/health.json" || echo "{}" > "$B/health.json"
curl -sS http://127.0.0.1:8000/bots > "$B/bots.json" || true
curl -sS http://127.0.0.1:8000/files > "$B/files.json" || true
curl -sS -o /dev/null -w "%{http_code}\n" -X OPTIONS http://127.0.0.1:8000/sse > "$B/sse.http" 2>/dev/null || true

# --- Routes & key files ---
find commander -maxdepth 1 -type f -name "routes_*.py" -print > "$B/routes.list.txt" || true
grep -R "APIRouter" -n commander > "$B/routes.scan.txt" 2>/dev/null || true
sha256sum templates/index.html 2>/dev/null >> "$B/filehashes.txt" || true
sha256sum templates/terminal.html 2>/dev/null >> "$B/filehashes.txt" || true
sha256sum commander/commander.py commander/agent.py 2>/dev/null >> "$B/filehashes.txt" || true

# --- Blueprint / patches ---
cp -f scripts/blueprint_watcher.py "$B/" 2>/dev/null || true
cp -f blueprint.json "$B/" 2>/dev/null || true
cp -f data/auto_applied.json "$B/" 2>/dev/null || true
(ls -l patches/auto || true) > "$B/patches.auto.ls.txt"

# --- .env (redacted safely) ---
if [ -f ".env" ]; then
python3 - "$B/dotenv.redacted.txt" <<'PY'
import re, sys
out = sys.argv[1]
def mask(v): return (v[:3]+"***"+v[-2:]) if len(v)>=7 else "***"
red=[]
with open(".env","r",encoding="utf-8",errors="ignore") as f:
  for line in f:
    m=re.match(r"\s*([A-Za-z0-9_]+)\s*=\s*(.*)\s*$", line)
    if not m: continue
    k,v=m.group(1),m.group(2).strip().strip("\"'"); red.append(f"{k}="+(mask(v) if v else "(empty)"))
with open(out,"w",encoding="utf-8") as o: o.write("\n".join(red))
PY
fi

# --- Tiny summary ---
python3 - "$B/report.txt" <<'PY'
import json, os, sys
b=sys.argv[1]
def J(name):
  p=os.path.join(b,name)
  try: return json.load(open(p))
  except: return {}
h=J("health.json"); bots=J("bots.json")
if isinstance(bots,dict): bots=bots.get("bots",[]) or bots.get("items",[]) or []
lines=[
  "=== Quantum Commander Snapshot ===",
  f"Provider: {h.get('provider')}",
  f"Model: {h.get('model')}",
  f"OK: {h.get('ok')}   SSE/WS present: sse_http="+str(open(os.path.join(b,'sse.http')).read().strip() if os.path.exists(os.path.join(b,'sse.http')) else 'NA'),
  f"Bots: {len(bots)}"
]
open(os.path.join(b,"report.txt"),"w").write("\n".join(lines)+"\n")
print("\n".join(lines))
PY

# --- Bundle it ---
tar -C "$OUT/$TS" -czf "$OUT/qc-diagnostics-$TS.tar.gz" .
echo
echo "=== Diagnostics bundle ready ==="
echo "Folder: $OUT/$TS"
echo "Archive: $OUT/qc-diagnostics-$TS.tar.gz"
echo "Open: xdg-open $OUT/$TS || true"
