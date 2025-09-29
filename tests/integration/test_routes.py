from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_get_config_includes_server_port_and_defaults():
    r = client.get("/assistant/config")
    assert r.status_code == 200
    data = r.json()
    assert "server_port" in data
    assert data["preferredTransport"] in {"sse", "ws"}


def test_patch_requires_token():
    r = client.patch("/assistant/config", json={"provider": "openai"})
    assert r.status_code == 401
