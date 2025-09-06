from __future__ import annotations
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from commander.agent import stream_agent
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
    """Server-Sent Events streaming for a single prompt using the existing provider streams."""
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
        yield f"event: meta\ndata: {json.dumps({'req_id': req_id, 'ts': time.time()})}\n\n"
        try:
            async for delta in stream_agent(message, meta):
                if await request.is_disconnected():
                    break
                if delta:
                    payload = {"delta": delta}
                    yield f"event: delta\ndata: {json.dumps(payload)}\n\n"
        finally:
            if not await request.is_disconnected():
                yield f"event: done\ndata: {json.dumps({'ok': True})}\n\n"

    return StreamingResponse(eventgen(), media_type="text/event-stream")

