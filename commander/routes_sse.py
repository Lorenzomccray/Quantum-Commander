from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from commander.agent import stream_agent, make_agent as call_agent, apply_bot_overrides
import asyncio, json, time, uuid, logging, os

router = APIRouter()
log = logging.getLogger("qc")

# Accept both GET (querystring) and POST (JSON body) to support very long prompts safely
@router.api_route("/sse", methods=["GET", "POST"])
async def sse(
    request: Request,
    message: str | None = None,
    provider: str = "openai",
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 800,
    bot_id: str = "",
):
    """Server-Sent Events for a single prompt with graceful fallback when streaming is disallowed.

    Supports:
      - GET /sse?message=... (legacy)
      - POST /sse {"message":..., "provider":..., ...} (preferred for long prompts)
    """
    # Prefer JSON body on POST to avoid URL length limits
    try:
        if request.method == "POST":
            body = await request.json()
            if isinstance(body, dict):
                message = body.get("message", message)
                provider = body.get("provider", provider)
                model = body.get("model", model)
                temperature = float(body.get("temperature", temperature))
                max_tokens = int(body.get("max_tokens", max_tokens))
                bot_id = body.get("bot_id", bot_id)
    except Exception:
        # Fall back to query params if body parse fails
        pass

    # Apply bot overrides to payload (provider/model/params/system prompt)
    payload = {
        "message": message or "",
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "bot_id": bot_id,
    }
    try:
        payload = apply_bot_overrides(payload)
    except Exception:
        pass

    # Extract possibly overridden values
    message = payload.get("message", message)
    provider = payload.get("provider", provider)
    model = payload.get("model", model)
    temperature = float(payload.get("temperature", temperature))
    max_tokens = int(payload.get("max_tokens", max_tokens))
    sys_prompt = payload.get("system_prompt")

    meta = {
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if sys_prompt:
        meta["system_prompt"] = sys_prompt

    async def eventgen():
        req_id = uuid.uuid4().hex
        log.info("sse_start", extra={"req_id": req_id, "provider": provider, "model": model})
        # metadata prelude
        yield f"event: meta\ndata: {json.dumps({'req_id': req_id, 'ts': time.time()})}\n\n"

        first = True
        done = asyncio.Event()
        q: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()

        async def stream_task():
            try:
                async for delta in stream_agent(message, meta):
                    await q.put(("delta", delta or ""))
            except Exception as e:
                await q.put(("error", f"[agent-error] {type(e).__name__}: {e}"))
            finally:
                await q.put(("done", None))
                done.set()

        async def ping_task():
            try:
                while not done.is_set():
                    await asyncio.sleep(5)
                    await q.put(("ping", "{}"))
            except asyncio.CancelledError:
                pass

        t1 = asyncio.create_task(stream_task())
        t2 = asyncio.create_task(ping_task())
        FIRST_TIMEOUT = float(os.getenv("QC_STREAM_FIRST_TIMEOUT", "10"))
        started = time.monotonic()
        try:
            while True:
                try:
                    kind, payload_s = await asyncio.wait_for(q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    # Watchdog: if no first chunk within timeout, fallback to one-shot
                    if first and (time.monotonic() - started) > FIRST_TIMEOUT:
                        try:
                            text = await call_agent(message, meta)
                        except Exception as e:
                            text = f"[agent-error] {type(e).__name__}: {e}"
                        yield f"event: delta\ndata: {json.dumps({'delta': text})}\n\n"
                        yield f"event: done\ndata: {json.dumps({'ok': True, 'fallback': 'timeout'})}\n\n"
                        try:
                            log.info("sse_no_delta_timeout", extra={"req_id": req_id})
                        except Exception:
                            pass
                        break
                    continue

                if await request.is_disconnected():
                    break
                if kind == "delta":
                    delta = payload_s or ""
                    if first and delta.startswith("[agent-error]"):
                        try:
                            text = await call_agent(message, meta)
                        except Exception as e:
                            text = f"[agent-error] {type(e).__name__}: {e}"
                        yield f"event: delta\ndata: {json.dumps({'delta': text})}\n\n"
                        yield f"event: done\ndata: {json.dumps({'ok': True, 'fallback': 'agent-error'})}\n\n"
                        break
                    yield f"event: delta\ndata: {json.dumps({'delta': delta})}\n\n"
                    first = False
                elif kind == "ping":
                    yield f"event: ping\ndata: {payload_s}\n\n"
                elif kind == "error":
                    # Fallback already encoded in error payload; surface as delta
                    yield f"event: delta\ndata: {json.dumps({'delta': payload_s or ''})}\n\n"
                elif kind == "done":
                    yield f"event: done\ndata: {json.dumps({'ok': True})}\n\n"
                    try:
                        log.info("sse_done", extra={"req_id": req_id})
                    except Exception:
                        pass
                    break
        finally:
            for t in (t1, t2):
                if not t.done():
                    t.cancel()

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(eventgen(), media_type="text/event-stream", headers=headers)

