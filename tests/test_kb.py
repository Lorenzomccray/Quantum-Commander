def test_kb_index_and_search(app_client):
    r = app_client.post("/kb/index", params={"text": "hello quantum world", "source": "test"})
    assert r.status_code == 200
    r2 = app_client.get("/kb/search", params={"q": "quantum", "k": 3})
    assert r2.status_code == 200
    hits = r2.json().get("hits", [])
    assert any("quantum" in h.get("text", "").lower() for h in hits)
