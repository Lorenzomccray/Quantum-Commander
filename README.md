# 🧠 Quantum Ops AI

**Quantum Ops AI** is a cognitive command-line assistant built to evolve with you. It learns what you teach it, recalls what matters, and continuously enhances its own capabilities — without ever breaking your flow.

Whether you’re automating tasks, securing workflows, or simply trying to remember that perfect command you ran three weeks ago, Quantum Ops AI is your second brain on the terminal.

---

## ✨ What It Does

- 📚 **Learn** any custom command and tag it by purpose or environment
- 🧠 **Recall** intelligently — with fuzzy logic and AI fallback
- 🤖 **Suggest** alternatives when your memory draws a blank
- ⬆️ **Upgrade** itself from a URL or GitHub repo
- 🔒 Designed for **private use** and controlled self-enhancement
- 🗂️ **List** saved commands with tags and metadata

---

## 🚀 Quick Start

```bash
# Install dependencies
npm install

# Link it to your terminal
npm link

# Start using the assistant
qc learn "start server" "npm run dev" -t dev,local
qc recall "run server"
qc suggest "build project"
qc list
qc upgrade --url https://yourdomain.com/modules/update.js
```

---

## 🧩 Backend API (FastAPI) — SSE, Files, KB, and Chats

This repository also includes a FastAPI backend (Quantum Commander) powering a web UI with WebSocket and Server‑Sent Events (SSE) transports, file uploads, a minimal knowledge base, persistent chats, and customizable bot profiles.

### Endpoints

Health
- GET /health — basic service/config status

SSE Streaming
- GET /sse?message=... — streams events: `meta` → repeated `delta` frames → `done`

Files
- GET /files — list uploaded files
- POST /files/upload — multipart/form‑data upload; field name: `file`
- GET /files/{file_id} — download by ID

Knowledge Base (JSON‑backed)
- POST /kb/index — add/update entries
- GET /kb/search?q=... — simple search over indexed content

Chats (JSON‑backed)
- GET /chats — list chats
- POST /chats — create chat
- GET /chats/{chat_id} — get a chat
- PATCH /chats/{chat_id} — update a chat

Bots
- GET /bots — list bot profiles
- POST /bots — create/update a bot profile
- DELETE /bots/{bot_id} — delete a bot profile

### Streaming caveat (SSE)
Some model providers require special permissions for streaming. If you see an error like:

> Your organization must be verified to stream this model.

then either:
- choose a model you’re permitted to stream,
- verify your organization for streaming with that provider, or
- switch Transport to WebSocket in the UI (top controls) to avoid SSE.

### UI notes
- Transport selector: choose WebSocket or SSE for chat streaming.
- Uploads modal: upload files; metadata is stored under `uploads/` and persisted.
- Bot profiles: click the 🧩 Bots button to create and select specialized bots; chat requests include the selected `bot_id` and apply bot overrides (system prompt and parameters).

### CLI examples
SSE stream (first lines):

```bash
curl -Ns "http://127.0.0.1:8000/sse?message=Hello%20from%20SSE" | sed -n '1,12p'
```

Upload a file:

```bash
curl -F "file=@/etc/hosts" http://127.0.0.1:8000/files/upload
```

