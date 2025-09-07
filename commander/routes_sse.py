from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from commander.agent import stream_agent, make_agent as call_agent, apply_bot_overrides
import asyncio, json, time, uuid, logging

router = APIRouter()
log = logging.getLogger("qc")

@router.get("/sse")
async def sse(
    request: Request,
    message: str,
    provider: str = "openai",
    model: str = "gpt-5",
    temperature: float = 0.2,
    max_tokens: int = 800,
    bot_id: str = "",
):
    """Server-Sent Events for a single prompt with graceful fallback when streaming is disallowed."""
    # Apply bot overrides to payload (provider/model/params/system prompt)
    payload = {
        "message": message,
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
                    await asyncio.sleep(20)
                    await q.put(("ping", "{}"))
            except asyncio.CancelledError:
                pass

        t1 = asyncio.create_task(stream_task())
        t2 = asyncio.create_task(ping_task())
        try:
            while True:
                kind, payload_s = await q.get()
                if await request.is_disconnected():
                    break
                if kind == "delta":
                    delta = payload_s or ""
                    if first and delta.startswith("[agent-error]"):
                        low = delta.lower()
                        if "stream" in low or "streaming" in low or "unsupported_value" in low or "verify" in low:
                            try:
                                text = await call_agent(message, meta)
                            except Exception as e:
                                text = f"[agent-error] {type(e).__name__}: {e}"
                            yield f"event: delta\ndata: {json.dumps({'delta': text})}\n\n"
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
                    log.info("sse_done", extra={"req_id": req_id})
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

