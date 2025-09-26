# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

Command cheat sheet

Python backend (FastAPI + UI)
- Setup (uv recommended)
  - uv venv .venv && source .venv/bin/activate
  - uv pip install -r requirements.txt
- Run locally (serves UI and APIs)
  - python -m commander.commander web
    - UI: http://127.0.0.1:8000/ui  • Basic check: http://127.0.0.1:8000/basic  • Health: http://127.0.0.1:8000/health
    - To change bind address/port: export QC_HOST=127.0.0.1 QC_PORT=8000
  - Alternative (with reload): uvicorn "commander.commander:app" --host 127.0.0.1 --port 8000 --reload
- Quick API demos
  - SSE stream (GET; print first lines):
    - curl -Ns "http://127.0.0.1:8000/sse?message=Hello%20from%20SSE" | sed -n '1,12p'
  - SSE stream (POST JSON; preferred for long prompts):
    - curl -Ns -X POST http://127.0.0.1:8000/sse -H 'Content-Type: application/json' -d '{"message":"Hello from SSE"}' | sed -n '1,12p'
  - Upload a file:
    - curl -F "file=@/etc/hosts" http://127.0.0.1:8000/files/upload

Tests (pytest)
- Install: uv pip install pytest
- Run all: pytest -q
- Run one file: pytest tests/test_ws.py -q
- Run one test: pytest tests/test_ws.py::test_ws_stream_and_cancel -q

Node.js CLI (separate from backend)
- Install deps: npm install
- Help: node bin/qc --help
- Optional global link: npm link  (then use qc ...)
- Examples:
  - qc learn "start server" "npm run dev" -t dev,local
  - qc recall "run server"
  - qc suggest "build project"
  - qc list
  - Upgrade modules: qc upgrade --url https://example.com/QuantumCognition.js  (or --git <repo>)

Service helpers (optional)
- Make targets (systemd user service via qcctl):
  - make qstart | qstop | qrestart | qstatus | qlogs | qlog | qhealth | qopen | qenable | qdisable
- Note: qcctl manages the user-level systemd unit quantum-commander.service. For local development, prefer python -m commander.commander web.

React GUI (experimental, separate)
- cd quantum-gui && npm install && npm run dev (Vite dev server)
- Optional: cp .env.template .env and set VITE_ASSISTANT_PORT=8000 (or place a .port file with the backend port)

Key configuration (env)
- Providers and models (read from .env in repo root)
  - MODEL_PROVIDER: openai | anthropic | groq | deepseek
  - OPENAI_MODEL, ANTHROPIC_MODEL, GROQ_MODEL, DEEPSEEK_MODEL
  - OPENAI_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY, DEEPSEEK_API_KEY
  - TEMPERATURE, MAX_TOKENS, REQUEST_TIMEOUT_S
- Server runtime
  - QC_HOST, QC_PORT (defaults: 127.0.0.1, 8000) for python -m commander.commander web
  - QC_STREAM_FIRST_TIMEOUT (s): max wait for first streaming chunk before one‑shot fallback
  - QC_PREWARM: if set to 1/true, prewarm provider endpoints at startup
- Data/DB
  - SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (enable Supabase-backed storage)
  - QC_BOTS_DB, QC_CHATS_DB, QC_KB_DB, QC_SKILLS_DB (override JSON file paths)
  - QC_UPLOAD_DIR (uploads/), QC_MAX_UPLOAD (bytes)
- Ops (privileged)
  - OPS_TOKEN enables /ops/* and /ops/pty; requires external helpers /usr/local/bin/qc-rootsh and /usr/local/bin/qc-ptysh
- Ensemble
  - ENSEMBLE_MODE: committee | router | cascade
  - ENSEMBLE_MODELS: JSON or CSV (e.g., openai:gpt-4o,anthropic:claude-3-5-sonnet-latest)
  - ENSEMBLE_JUDGE_PROVIDER, ENSEMBLE_JUDGE_MODEL
- CLI crypto
  - QC_SECRET for encrypting ~/.qc_secure_memory.enc

High-level architecture

Overview
- Polyglot workspace with two primary components:
  1) Python FastAPI service (primary runtime) that serves a local UI and provides chat transports (WebSocket + SSE), file uploads, a JSON-backed knowledge base, chats, bots, skills, and optional Supabase integration.
  2) A separate Node.js CLI (qc) for personal command memory (learn/recall/suggest/list) using an encrypted local store.
- An experimental React/Vite app (quantum-gui) exists but is not wired to the FastAPI routes by default; the FastAPI app serves its own UI from templates/.

Service composition (FastAPI)
- Entry/app wiring: commander/commander.py
  - Loads .env (repo root), sets restrictive CORS for localhost, mounts /static, serves templates/.
  - Includes routers:
    - Chat transports:
      - /ws WebSocket: JSON or text frames. Supports streaming and non-streaming; includes cancel via JSON {type:"cancel", id}.
      - /sse Server-Sent Events: emits meta, repeated delta frames, then done; on first-chunk streaming errors, falls back to one-shot. Supports GET and JSON POST.
    - Data APIs (JSON-backed with optional Supabase): /files, /kb, /chats, /bots, /skills
    - Ops (privileged): /ops/shell (root exec with one-warning destructive guard); /ops/pty (root PTY via qc-ptysh + sudo); /pty (user shell PTY)
    - Supabase status: /supabase/status returns table readiness plus a consolidated SQL schema to provision required tables.
    - Health/UI: from app/main.py — /health (summarizes provider/model, key presence, stores), /live, /ready (template/upload-dir/keys/ops checks), plus /basic (diagnostics HTML), / and /ui (full chat UI)
- LLM provider bridge: commander/agent.py
  - Adapts to multiple providers based on env (OpenAI, Anthropic, Groq, DeepSeek).
  - One-shot make_agent() and streaming stream_agent() with automatic compatibility fallbacks (Responses API vs Chat Completions; non-stream fallback when streaming isn’t permitted).
  - Bot profile overrides: apply_bot_overrides injects provider/model/params/system prompt based on selected bot_id (stored in JSON or Supabase).
- Persistence
  - Default JSON stores under data/ (bots.json, chats.json, kb.json, skills.json). DALs prefer Supabase when SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are configured.
  - Uploads under uploads/ with metadata index uploads/_meta.json.
- Ensemble
  - Committee/router/cascade strategies via commander/ensemble.py. Maintains per-run logs under data/logs and a small local ensemble_memory.json for biasing future runs.
- UI (templates/index.html)
  - Single-page chat with transport selector (WS/SSE), per-message ensemble overrides, file uploads, bots/skills managers, and Supabase status/SQL modal.
  - Sensible defaults (e.g., non-stream for certain OpenAI models and for ensemble); badge indicators show active modes/overrides.

Node CLI (independent of FastAPI)
- bin/qc -> lib/QuantumCommander.js provides:
  - learn <input> <output> [--tags]
  - recall <input> [--exec] [--threshold] [--suggest]
  - suggest <query>
  - list [--tags] [--sort]
  - upgrade (--url | --git) to refresh core assistant modules under lib/
- lib/QuantumCognition.js
  - Encrypted JSON store at ~/.qc_secure_memory.enc; QC_SECRET governs key derivation (PBKDF2 via lib/QuantumCrypto.js).
  - Fuzzy recall (fastest-levenshtein) and optional AI-style suggestion heuristic.
- Completely separate from the Python backend—useful alongside, not required by it.

Notes and caveats
- Streaming caveat (SSE/WS): some providers/models disallow streaming without special permissions. Code auto-falls back to non-stream one-shot responses when necessary; tune first-chunk timeout via QC_STREAM_FIRST_TIMEOUT.
- Privileged ops require OPS_TOKEN and external helpers installed in the system; without them, /ops/* will be unavailable.
- No repository-wide linter configuration is present; linting commands are intentionally omitted.
- CI runs pytest on Python 3.13 and sets MODEL_PROVIDER=openai; tests stub streaming and avoid real provider calls.

