from __future__ import annotations

import asyncio
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

router = APIRouter()


@router.get("/assistant/sse")
async def assistant_sse(request: Request, provider: str | None = None, model: str | None = None):
    if not provider or not model:
        raise HTTPException(status_code=400, detail="provider and model query params are required")

    async def event_stream():
        # Minimal stub: stream a few heartbeats and then end
        for i in range(3):
            if await request.is_disconnected():
                break
            yield f"event: message\ndata: {{\"tick\": {i}, \"provider\": \"{provider}\", \"model\": \"{model}\"}}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
