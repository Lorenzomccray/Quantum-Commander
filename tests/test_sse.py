import re


def test_sse_stream_with_stub(app_client, monkeypatch):
    # Stub stream_agent to avoid network/provider
    async def fake_stream_agent(message: str, meta=None):
        yield "hello "
        yield "world"

    from commander import routes_sse as r
    monkeypatch.setattr(r, "stream_agent", fake_stream_agent, raising=True)

    with app_client.stream("GET", "/sse", params={"message": "x"}) as resp:
        assert resp.status_code == 200
        body = ""
        for line in resp.iter_lines():
            if not line:
                continue
            body += line.decode() if isinstance(line, (bytes, bytearray)) else line
            body += "\n"
        # Expect meta, delta (hello ), delta (world), done
        assert re.search(r"^event: meta$", body, re.M)
        assert re.search(r"data: \{.*\}$", body, re.M)
        assert "hello " in body and "world" in body
        assert re.search(r"^event: done$", body, re.M)
