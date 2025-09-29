from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ValidationError

ws_router = APIRouter()


class WsMessage(BaseModel):
    type: str
    content: str


@ws_router.websocket("/assistant/ws")
async def assistant_ws(websocket: WebSocket) -> None:
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
        # Enhanced echo loop with schema validation
        while True:
            msg_text = await websocket.receive_text()
            try:
                parsed = json.loads(msg_text)
                validated = WsMessage(**parsed)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "echo",
                            "content": f"Received {validated.type}: {validated.content}",
                            "provider": provider,
                            "model": model,
                        }
                    )
                )
            except (json.JSONDecodeError, ValidationError) as e:
                await websocket.send_text(
                    json.dumps(
                        {"type": "error", "content": f"Invalid message format: {type(e).__name__}"}
                    )
                )
    except WebSocketDisconnect:
        return
