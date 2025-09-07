def test_health_ok(app_client):
    r = app_client.get("/health")
    assert r.status_code == 200
    j = r.json()
    assert j.get("ok") is True
    assert "provider" in j and "available_models" in j
    assert j.get("ws") is True and j.get("sse") is True
