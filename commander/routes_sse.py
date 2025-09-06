from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from commander.agent import stream_agent, make_agent as call_agent
import asyncio, json, time, uuid

router = APIRouter()

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
    meta = {
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if bot_id:
        meta["bot_id"] = bot_id

    async def eventgen():
        req_id = uuid.uuid4().hex
        # metadata prelude
        yield f"event: meta\ndata: {json.dumps({'req_id': req_id, 'ts': time.time()})}\n\n"

        sent_any = False
        first = True
        try:
            async for delta in stream_agent(message, meta):
                if await request.is_disconnected():
                    break
                if not delta:
                    continue
                # Detect provider streaming restriction and fallback to one-shot
                if first and isinstance(delta, str) and delta.startswith("[agent-error]"):
                    low = delta.lower()
                    if "stream" in low or "streaming" in low or "unsupported_value" in low or "verify" in low:
                        try:
                            text = await call_agent(message, meta)
                        except Exception as e:
                            text = f"[agent-error] {type(e).__name__}: {e}"
                        yield f"event: delta\ndata: {json.dumps({'delta': text})}\n\n"
                        sent_any = True
                        break
                # Normal streaming delta
                yield f"event: delta\ndata: {json.dumps({'delta': delta})}\n\n"
                sent_any = True
                first = False
        except Exception as e:
            # Hard failure: fallback to one-shot
            try:
                text = await call_agent(message, meta)
            except Exception as e2:
                text = f"[agent-error] {type(e2).__name__}: {e2}"
            yield f"event: delta\ndata: {json.dumps({'delta': text})}\n\n"
            sent_any = True
        finally:
            if not await request.is_disconnected():
                yield f"event: done\ndata: {json.dumps({'ok': True})}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(eventgen(), media_type="text/event-stream", headers=headers)

