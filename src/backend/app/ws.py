from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

ws_router = APIRouter()


@ws_router.websocket("/assistant/ws")
async def assistant_ws(websocket: WebSocket):
    # Validate required query params
    provider = websocket.query_params.get("provider")
    model = websocket.query_params.get("model")
    if not provider or not model:
        # Accept then close with a policy violation
        await websocket.accept()
        await websocket.close(code=1008, reason="provider and model query params are required")
        return

    await websocket.accept()
    try:
        # Minimal echo loop
        while True:
            msg = await websocket.receive_text()
            await websocket.send_text(f"echo: {msg}")
    except WebSocketDisconnect:
        return
