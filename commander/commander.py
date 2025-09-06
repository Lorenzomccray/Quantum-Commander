# ----- FastAPI Web (Vanilla WebSocket with raw text) -----
import asyncio
import os
import pathlib
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
import json
from commander.routes_bots import router as bots_router
from commander.routes_sse import router as sse_router
from commander.routes_files import router as files_router
from commander.routes_kb import router as kb_router
from commander.routes_chats import router as chats_router

app = FastAPI(title="Quantum Commander")
app.include_router(bots_router)
app.include_router(sse_router)
app.include_router(files_router)
app.include_router(kb_router)
app.include_router(chats_router)

# repo-root-based paths
repo_root = pathlib.Path(__file__).resolve().parent.parent
# Load .env from repo root if present
try:
    load_dotenv(dotenv_path=str(repo_root / ".env"), override=False)
except Exception:
    pass
static_dir = repo_root / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

templates_dir = repo_root / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Include app.* routers (e.g., /health)
try:
    from app.main import router as health_router  # type: ignore
    app.include_router(health_router)
except Exception:
    pass

# Try to import the async make_agent(message) -> str; otherwise provide an async echo fallback.
try:
    from .agent import make_agent as call_agent, stream_agent, apply_bot_overrides  # type: ignore
except Exception:
    async def call_agent(message: str, meta=None) -> str:
        return f"Echo: {message}"
    async def stream_agent(message: str, meta=None):
        yield f"Echo: {message}"
    def apply_bot_overrides(payload: dict):
        return payload

@app.get("/", response_class=HTMLResponse)
async def web_ui(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Receive message (JSON or plain text)
            is_json = False
            try:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    # Apply bot overrides if available (provider/model/params/system prompt)
                    try:
                        data = apply_bot_overrides(data)  # type: ignore
                    except Exception:
                        pass
                    message = data.get("message", "")
                    is_json = True
                except Exception:
                    message = raw
            except Exception as e:
                # Malformed frame or receive error; report and continue
                try:
                    await websocket.send_json({"error": str(e)})
                except Exception:
                    pass
                continue

            # Process the message
            try:
                # Build meta overrides if JSON provided
                meta = None
                if is_json:
                    meta = {
                        "provider": data.get("provider"),
                        "model": data.get("model"),
                        "temperature": data.get("temperature"),
                        "max_tokens": data.get("max_tokens"),
                        "timeout_s": data.get("timeout_s"),
                    }
                # One-shot or streaming response
                if is_json and data.get("stream"):
                    # Inform client streaming has started
                    await websocket.send_json({"stream": True, "done": False})
                    # True provider streaming
                    async for delta in stream_agent(message, meta):
                        await websocket.send_json({"delta": delta})
                    await websocket.send_json({"done": True})
                else:
                    resp = await call_agent(message, meta)
                    # Send response back to client
                    if is_json:
                        await websocket.send_json({"response": resp})
                    else:
                        await websocket.send_text(resp if isinstance(resp, str) else str(resp))
            except Exception as e:
                # If processing failed, report error
                try:
                    await websocket.send_json({"error": str(e)}) if is_json else await websocket.send_text(f"Error: {e}")
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass

# Minimal CLI entrypoint for `python -m commander.commander web`
if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "web":
        import uvicorn
        uvicorn.run("commander.commander:app", host="127.0.0.1", port=8000, reload=False)
    else:
        print("Usage: python -m commander.commander web")

