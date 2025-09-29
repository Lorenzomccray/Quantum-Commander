# Fix Assistant Backend

Centralized configuration and transport gateway for the Assistant. This backend exposes a minimal FastAPI server that:

- Centralizes configuration behind an API (single source of truth)
- Enforces token-protected writes to config (PATCH)
- Surfaces provider readiness status based on env keys
- Normalizes transport to preferredTransport ∈ {sse, ws}
- Requires provider and model on every SSE/WS request
- Uses environment-driven port (QC_PORT, default 18000) and returns server_port read-only

Quick start (development)
- Requirements: Python 3.10+
- Recommended: create a virtual environment and install deps

```
python -m venv .venv
source .venv/bin/activate
pip install -e .
QC_PORT=18000 uvicorn backend.app.main:app --host 127.0.0.1 --port 18000
```

Endpoints
- GET /health → {"status":"ok"}
- GET /assistant/config → merged config + server_port + provider_ready/provider_reason
- PATCH /assistant/config (X-Auth-Token required) → updates provider/model/preferredTransport
- GET /assistant/sse?provider=...&model=... → demo stream (stub)
- WS /assistant/ws?provider=...&model=... → demo echo (stub)

Security
- The backend generates a token at startup if QC_TOKEN is not set, writing it to .qc_token with 0600 perms. Clients must use X-Auth-Token for PATCH.
- Never print secrets or tokens in logs.

Port policy
- The server listens on QC_PORT (default 18000). The API returns server_port read-only. Changing port requires restart and is not part of PATCH.

Transport policy
- preferredTransport is one of "sse" or "ws". Clients should pass provider/model on all SSE/WS calls and honor this preference.

Testing
```
pytest -q
```
