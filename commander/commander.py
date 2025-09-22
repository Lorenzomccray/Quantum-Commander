# ----- FastAPI Web (Vanilla WebSocket with raw text) -----
import asyncio
import os
import pathlib
import logging
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from app.settings import settings
from commander.agent import run_once as _run_once
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import json
from commander.routes_bots import router as bots_router
from commander.routes_sse import router as sse_router
from commander.routes_files import router as files_router
from commander.routes_kb import router as kb_router
from commander.routes_chats import router as chats_router
from commander.routes_ensemble import router as ensemble_router
from commander.routes_ops import router as ops_router
from commander.routes_pty_ws import router as pty_router
from commander.routes_skills import router as skills_router
from commander.routes_supabase import router as supabase_router
from commander.routes_extensions import router as extensions_router
from commander.routes_patch import router as patch_router

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    try:
        log.info("app_startup")
        # Background prewarm of common provider endpoints to reduce first-request DNS/TLS latency
        async def _prewarm():
            try:
                import httpx
                urls = [
                    "https://api.openai.com/",
                    "https://api.anthropic.com/",
                    "https://api.groq.com/",
                    "https://api.deepseek.com/",
                ]
                timeout = httpx.Timeout(2.0, read=2.0, write=2.0, connect=2.0)
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    tasks = [client.head(u) for u in urls]
                    try:
                        await asyncio.gather(*tasks, return_exceptions=True)
                    except Exception:
                        pass
                # Optional: exact-model warmup using paid API call if QC_PREWARM is enabled
                try:
                    if str(os.getenv("QC_PREWARM", "")).strip().lower() in ("1", "true", "yes", "on"):
                        async def _prewarm_model():
                            try:
                                provider = (settings.MODEL_PROVIDER or "openai").lower()
                                if provider == "openai":
                                    model = settings.OPENAI_MODEL
                                elif provider == "anthropic":
                                    model = settings.ANTHROPIC_MODEL
                                elif provider == "groq":
                                    model = settings.GROQ_MODEL
                                elif provider == "deepseek":
                                    model = settings.DEEPSEEK_MODEL
                                else:
                                    model = settings.OPENAI_MODEL
                                # Run in thread to avoid blocking the loop
                                await asyncio.to_thread(
                                    _run_once,
                                    provider=provider,
                                    model=model,
                                    message="ping",
                                    temperature=0.0,
                                    max_tokens=1,
                                )
                                log.info("prewarm_model_done", extra={"provider": provider, "model": model})
                            except Exception:
                                pass
                        await _prewarm_model()
                except Exception:
                    pass
                log.info("prewarm_done")
            except Exception:
                pass
        try:
            asyncio.create_task(_prewarm())
        except Exception:
            pass
        yield
    finally:
        try:
            log.info("app_shutdown")
        except Exception:
            pass

app = FastAPI(title="Quantum Commander", lifespan=lifespan)
# Restrictive CORS: allow only same-origin localhost access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(bots_router)
app.include_router(sse_router)
app.include_router(files_router)
app.include_router(kb_router)
app.include_router(chats_router)
app.include_router(ensemble_router)
app.include_router(ops_router, prefix="/ops")
app.include_router(pty_router)
app.include_router(skills_router)
app.include_router(supabase_router)
app.include_router(extensions_router)
app.include_router(patch_router)
# New utility routers
try:
    from commander.routes_search import router as search_router  # type: ignore
    app.include_router(search_router)
except Exception:
    pass
try:
    from commander.routes_vision import router as vision_router  # type: ignore
    app.include_router(vision_router)
except Exception:
    pass
# Diagnostics router
try:
    from commander.routes_diagnostics import router as diag_router  # type: ignore
    app.include_router(diag_router)
except Exception:
    pass
# Self status router
try:
    from commander.routes_self import router as self_router  # type: ignore
    app.include_router(self_router)
except Exception:
    pass

# Logger
log = logging.getLogger("qc")
if not log.handlers:
    logging.basicConfig(level=os.environ.get("QC_LOG_LEVEL", "INFO"))

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
async def web_root(request: Request):
    # Serve the full UI at the root
    return FileResponse(str(templates_dir / "index.html"), media_type="text/html")

@app.get("/ui", response_class=HTMLResponse)
async def web_ui(request: Request):
    # Also serve the full UI under /ui for compatibility
    return FileResponse(str(templates_dir / "index.html"), media_type="text/html")

@app.get("/basic", response_class=HTMLResponse)
async def web_basic(request: Request):
    # Keep a small diagnostics page
    return FileResponse(str(templates_dir / "basic.html"), media_type="text/html")

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
                        "system_prompt": data.get("system_prompt"),
                    }
                # Built-in chat command: /self -> return self-status JSON
                try:
                    msg_norm = (message or "").strip().lower()
                    if msg_norm in ("/self", "/status"):
                        try:
                            from commander.routes_self import self_status  # type: ignore
                            payload = self_status()
                            # Return structured JSON plus compact summary
                            await websocket.send_json({"response": payload, "summary": payload.get("summary"), "command": "self"})
                        except Exception as e:
                            await websocket.send_json({"error": f"self-status failed: {e}"})
                        continue
                except Exception:
                    pass
                # One-shot or streaming response
                # Ensemble one-shot path
                if is_json and data.get("model") == "ensemble":
                    from commander.ensemble import run_ensemble as _run_ensemble
                    emode = data.get("ensemble_mode") or os.getenv("ENSEMBLE_MODE", "committee")
                    emodels = data.get("ensemble_models")
                    try:
                        if isinstance(emodels, str):
                            emodels = json.loads(emodels)
                    except Exception:
                        emodels = None
                    res = _run_ensemble(
                        message=message,
                        temperature=float(data.get("temperature") or 0.2),
                        max_tokens=int(data.get("max_tokens") or 800),
                        mode=emode,
                        models=emodels,
                        timeout=int(data.get("ensemble_timeout") or 30),
                    )
                    await websocket.send_json({"response": res.get("response"), "meta": res.get("meta", {}), "stream": False, "done": True})
                    continue

                if is_json and data.get("stream"):
                    log.info("ws_stream_start", extra={"message": message[:80]})
                    # Inform client streaming has started
                    await websocket.send_json({"stream": True, "done": False})

                    # Minimal cancel support: listen for a {type:"cancel"} control frame while streaming
                    cancel_event = asyncio.Event()

                    async def listen_cancel():
                        while True:
                            try:
                                raw_ctrl = await websocket.receive_text()
                                try:
                                    ctrl = json.loads(raw_ctrl)
                                except Exception:
                                    continue
                                if isinstance(ctrl, dict) and ctrl.get("type") == "cancel" and ctrl.get("id") == data.get("id"):
                                    cancel_event.set()
                                    break
                            except WebSocketDisconnect:
                                break
                            except Exception:
                                # Ignore malformed or unexpected frames while streaming
                                continue

                    listener_task = asyncio.create_task(listen_cancel())
                    try:
                        first_chunk = True
                        started = time.monotonic()
                        FIRST_TIMEOUT = float(os.getenv("QC_STREAM_FIRST_TIMEOUT", "10"))
                        agen = stream_agent(message, meta)
                        aiter = agen.__aiter__()
                        while True:
                            if cancel_event.is_set():
                                log.info("ws_stream_cancel")
                                break
                            try:
                                delta = await asyncio.wait_for(aiter.__anext__(), timeout=1.0)
                            except StopAsyncIteration:
                                await websocket.send_json({"done": True})
                                log.info("ws_stream_done")
                                break
                            except asyncio.TimeoutError:
                                now = time.monotonic()
                                if first_chunk and (now - started) > FIRST_TIMEOUT:
                                    log.info("ws_no_delta_timeout")
                                    try:
                                        resp = await call_agent(message, meta)
                                        await websocket.send_json({"response": resp})
                                    except Exception as e:
                                        await websocket.send_json({"error": str(e)})
                                    finally:
                                        await websocket.send_json({"done": True})
                                    break
                                continue
                            # got a chunk
                            if first_chunk and isinstance(delta, str) and delta.startswith("[agent-error]"):
                                # Fallback to one-shot if streaming is not permitted
                                try:
                                    resp = await call_agent(message, meta)
                                    await websocket.send_json({"response": resp})
                                except Exception as e:
                                    await websocket.send_json({"error": str(e)})
                                finally:
                                    await websocket.send_json({"done": True})
                                    log.info("ws_stream_fallback_done")
                                break
                            await websocket.send_json({"delta": delta})
                            first_chunk = False
                    finally:
                        if not listener_task.done():
                            listener_task.cancel()
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

