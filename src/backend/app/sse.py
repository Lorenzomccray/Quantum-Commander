from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

router = APIRouter()


@router.get("/assistant/sse")
async def assistant_sse(
    request: Request,
    provider: str | None = None,
    model: str | None = None,
    count: int | None = None,
    interval_ms: int | None = None,
) -> StreamingResponse:
    if not provider or not model:
        raise HTTPException(status_code=400, detail="provider and model query params are required")

    # Defaults from env with bounds
    default_count = int(os.getenv("QC_SSE_PINGS", "3") or 3)
    default_interval = int(os.getenv("QC_SSE_INTERVAL_MS", "500") or 500)
    n = max(1, min(count or default_count, 50))
    delay = max(50, min(interval_ms or default_interval, 10_000)) / 1000.0

    async def event_stream() -> AsyncIterator[str]:
        # Minimal stub: stream heartbeats and then end
        for i in range(n):
            if await request.is_disconnected():
                break
            yield (
                f"event: message\n"
                f'data: {{"tick": {i}, "provider": "{provider}", "model": "{model}"}}\n\n'
            )
            await asyncio.sleep(delay)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
