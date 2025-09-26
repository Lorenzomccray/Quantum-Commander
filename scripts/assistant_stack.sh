#!/usr/bin/env bash
set -euo pipefail

# ===== paths =====
STACK="$HOME/assistant-stack"; VENV="$STACK/.venv"
POCKET="$HOME/.quantum/secrets.env"; BIN="$HOME/.quantum/bin"
mkdir -p "$STACK" "$BIN" "$(dirname "$POCKET")"

# ===== OS deps (Fedora) =====
if ! command -v dnf >/dev/null 2>&1; then echo "This installer targets Fedora (dnf)."; exit 1; fi
sudo dnf -y install git python3 python3-pip ffmpeg jq unzip \
  nodejs npm redis bind-utils curl || true
sudo systemctl enable --now redis || true

# Docker (for local services)
if ! command -v docker >/dev/null 2>&1; then
  sudo dnf -y install moby-engine docker-compose-plugin || true
  sudo systemctl enable --now docker || true
  sudo usermod -aG docker "$USER" || true
  echo "Docker group membership updated. You may need to re-login or run: newgrp docker"
fi

# ===== Ollama (local LLMs) =====
if ! command -v ollama >/dev/null 2>&1; then curl -fsSL https://ollama.com/install.sh | sh; fi

# ===== Python venv + core libs =====
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip wheel setuptools
"$VENV/bin/pip" install -U \
  openai anthropic groq deepseek \
  langchain llama-index tiktoken pydantic \
  elasticsearch==8.* requests httpx \
  pymongo redis \
  openai-whisper \
  fastapi uvicorn \
  playwright duckduckgo-search \
  chromadb weaviate-client pinecone-client wolframalpha \
  pillow

# Playwright browsers & deps (best effort)
"$VENV/bin/python" -m playwright install chromium || true
if ! "$VENV/bin/python" -m playwright install-deps; then
  echo "Hint: Playwright OS deps may require sudo: sudo $VENV/bin/python -m playwright install-deps" >&2
fi

# ===== Diffusers (Stable Diffusion CPU) + Torch gating =====
PY_MAJMIN=$("$VENV/bin/python" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)
case "$PY_MAJMIN" in
  3.13|3.13.*)
    echo "Python $PY_MAJMIN detected: skipping pinned torch CPU install (wheels may be unavailable)." ;;
  *)
    "$VENV/bin/pip" install --index-url https://download.pytorch.org/whl/cpu \
      torch==2.4.1 torchvision==0.19.1 || true
    ;;
esac
"$VENV/bin/pip" install -U diffusers transformers accelerate safetensors || true

# ===== secrets pocket (create/update placeholders) =====
touch "$POCKET"; chmod 600 "$POCKET"
set_kv(){ grep -q "^$1=" "$POCKET" 2>/dev/null && sed -i "s|^$1=.*|$1=$2|" "$POCKET" || echo "$1=$2" >> "$POCKET"; }
set_kv OPENAI_API_KEY ""
set_kv ANTHROPIC_API_KEY ""
set_kv GROQ_API_KEY ""
set_kv DEEPSEEK_API_KEY ""
set_kv MONGODB_URI ""
set_kv MONGODB_DB "assistant"
set_kv ELASTICSEARCH_URL ""
set_kv ELASTICSEARCH_API_KEY ""
set_kv ELASTICSEARCH_INDEX "assistant-index"
# If elastic-start-local exists, wire it automatically
if [ -f "$HOME/elastic-start-local/.env" ]; then
  ES_PW=$(grep -E "^ELASTIC_PASSWORD=" "$HOME/elastic-start-local/.env" | cut -d= -f2- || true)
  CA_CERT=$(grep -E "^CA_CERT=" "$HOME/elastic-start-local/.env" | cut -d= -f2- || true)
  [ -n "$CA_CERT" ] && set_kv ELASTICSEARCH_CA_CERT "$CA_CERT"
  set_kv ELASTICSEARCH_URL "https://localhost:9200"
  set_kv ELASTICSEARCH_USERNAME "elastic"
  set_kv ELASTICSEARCH_PASSWORD "$ES_PW"
fi

# ===== helpers =====
cat > "$BIN/ai-health" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
VENV="$HOME/assistant-stack/.venv"; POCKET="$HOME/.quantum/secrets.env"
echo "== Versions =="; echo -n "Python: "; "$VENV/bin/python" -V
echo -n "Node: "; node -v 2>/dev/null || echo "missing"
echo -n "Ollama: "; ollama --version 2>/dev/null || echo "missing"
echo -n "Redis: "; redis-cli ping 2>/dev/null || echo "missing/blocked"
echo
echo "== Python libs =="; "$VENV/bin/python" - <<PY
import pkgutil
need=["openai","anthropic","groq","deepseek","langchain","llama_index","elasticsearch","pymongo","redis","whisper","playwright","diffusers"]
have={m.name for m in pkgutil.iter_modules()}
print("installed:", ", ".join(sorted(set(need)&have)))
print("missing:", ", ".join([n for n in need if n not in have]) or "none")
PY
echo
echo "== Elastic check =="; if [ -f "$POCKET" ]; then . "$POCKET"; fi
if [ -n "${ELASTICSEARCH_URL:-}" ]; then
  if [ -n "${ELASTICSEARCH_API_KEY:-}" ]; then
    curl -sS -k -H "Authorization: ApiKey $ELASTICSEARCH_API_KEY" "$ELASTICSEARCH_URL/_cluster/health?pretty" | sed -n "1,40p" || true
  elif [ -n "${ELASTICSEARCH_USERNAME:-}" ] && [ -n "${ELASTICSEARCH_PASSWORD:-}" ]; then
    curl -sS -k -u "$ELASTICSEARCH_USERNAME:$ELASTICSEARCH_PASSWORD" "$ELASTICSEARCH_URL/_cluster/health?pretty" | sed -n "1,40p" || true
  else echo "Elastic not configured (set API key or user/pass in secrets.env)"; fi
else echo "Elastic URL not set."; fi
echo
echo "== Mongo check =="; "$VENV/bin/python" - <<PY
import os, sys
uri=(open(os.path.expanduser("~/.quantum/secrets.env")).read() if os.path.exists(os.path.expanduser("~/.quantum/secrets.env")) else "")
for line in uri.splitlines():
    if line.startswith("MONGODB_URI="): uri=line.split("=",1)[1]; break
else: uri=""
if not uri: print("Mongo not configured."); sys.exit(0)
from pymongo import MongoClient
try: print(MongoClient(uri, serverSelectionTimeoutMS=3000).admin.command("ping"))
except Exception as e: print("Mongo error:", e)
PY
SH
chmod +x "$BIN/ai-health"

cat > "$BIN/ai-pull-models" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
MEM_GB=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo 2>/dev/null || echo 8)
echo "Detected RAM: ${MEM_GB} GB"
if [ "$MEM_GB" -ge 24 ]; then
  echo "Pulling: llama3.1:8b, deepseek-coder:6.7b";
  ollama pull llama3.1:8b || true
  ollama pull deepseek-coder:6.7b || true
elif [ "$MEM_GB" -ge 12 ]; then
  echo "Pulling: llama3.2:3b, deepseek-coder:1.3b";
  ollama pull llama3.2:3b || true
  ollama pull deepseek-coder:1.3b || true
else
  echo "Low RAM: pulling tiny models (phi3:mini)";
  ollama pull phi3:mini || true
fi
echo "Done."
SH
chmod +x "$BIN/ai-pull-models"

# PATH reminder
if ! echo ":$PATH:" | grep -q ":$HOME/.quantum/bin:"; then
  echo
  echo "PATH hint: add the following to your shell profile to use helpers without full paths:"
  echo "  export PATH=\"\$HOME/.quantum/bin:\$PATH\""
  echo
fi

echo
echo "✅ Giant intelligence stack installed."
echo "   • Venv: $VENV"
echo "   • Secrets: $POCKET   (put your API keys & URIs here)"
echo "   • Helpers: $BIN/ai-health, $BIN/ai-pull-models"
echo
echo "Next steps:"
echo "  1) Open secrets:  code $POCKET   # add OPENAI_API_KEY, MONGODB_URI, ELASTICSEARCH_*"
echo "  2) Pull local models:  $BIN/ai-pull-models"
echo "  3) Verify:  $BIN/ai-health"
echo "  4) Optional Weaviate:  qc stack weaviate start   (or: make stack-weaviate-start)"