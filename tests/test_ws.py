import asyncio

def test_ws_stream_and_cancel(app_client, monkeypatch):
    from commander import commander as cm

    async def fake_stream_agent(message: str, meta=None):
        for i in range(50):
            await asyncio.sleep(0.01)
            yield f"chunk{i}"

    monkeypatch.setattr(cm, "stream_agent", fake_stream_agent, raising=True)

    with app_client.websocket_connect("/ws") as ws:
        ws.send_json({
            "id": "t1",
            "message": "hello",
            "stream": True,
            "provider": "openai",
            "model": "gpt-5",
        })
        pre = ws.receive_json()
        assert pre.get("stream") is True and pre.get("done") is False
        first = ws.receive_json()
        assert "delta" in first
        # request cancel
        ws.send_json({"type": "cancel", "id": "t1"})
        done_seen = False
        for _ in range(50):
            msg = ws.receive_json()
            if msg.get("done") is True:
                done_seen = True
                break
        assert done_seen


def test_ws_nonstream_ok(app_client, monkeypatch):
    from commander import commander as cm

    async def fake_call_agent(message: str, meta=None):
        return "ok:" + message

    monkeypatch.setattr(cm, "call_agent", fake_call_agent, raising=True)

    with app_client.websocket_connect("/ws") as ws:
        ws.send_json({"message": "ping", "stream": False})
        msg = ws.receive_json()
        assert msg.get("response") == "ok:ping"
