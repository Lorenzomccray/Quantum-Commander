def test_bots_crud(app_client):
    payload = {
        "name": "Test Bot",
        "emoji": "🤖",
        "system_prompt": "You are test.",
        "provider": "openai",
        "model": "gpt-5",
        "temperature": 0.1,
        "max_tokens": 256,
    }
    r = app_client.post("/bots", json=payload)
    assert r.status_code == 200
    bot = r.json()["bot"]

    r_list = app_client.get("/bots")
    assert r_list.status_code == 200
    assert any(b["id"] == bot["id"] for b in r_list.json().get("bots", []))

    r_get = app_client.get(f"/bots/{bot['id']}")
    assert r_get.status_code == 200

    r_patch = app_client.patch(f"/bots/{bot['id']}", json={"name": "Renamed Bot"})
    assert r_patch.status_code == 200
    assert r_patch.json()["bot"]["name"] == "Renamed Bot"

    r_del = app_client.delete(f"/bots/{bot['id']}")
    assert r_del.status_code == 200
