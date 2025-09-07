import os
import sys
import importlib
from pathlib import Path
import pytest
from starlette.testclient import TestClient


def _clear_modules():
    for name in [
        "commander.commander",
        "commander.routes_files",
        "commander.routes_kb",
        "commander.routes_chats",
        "commander.routes_sse",
        "commander.bots_dal",
        "app.main",
        "app.settings",
    ]:
        if name in sys.modules:
            del sys.modules[name]


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    # Isolate data dirs under a temp root
    root = tmp_path
    (root / "uploads").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("QC_UPLOAD_DIR", str(root / "uploads"))
    monkeypatch.setenv("QC_BOTS_DB", str(root / "data" / "bots.json"))
    monkeypatch.setenv("QC_KB_DB", str(root / "data" / "kb.json"))
    monkeypatch.setenv("QC_CHATS_DB", str(root / "data" / "chats.json"))
    # Keep provider local-safe
    monkeypatch.setenv("MODEL_PROVIDER", "openai")

    _clear_modules()
    from commander import commander as commander_mod  # type: ignore

    app = commander_mod.app
    client = TestClient(app)
    return client
