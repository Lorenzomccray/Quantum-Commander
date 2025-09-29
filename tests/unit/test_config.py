# Unit tests for core config merging and validation
from backend.app.config import DEFAULTS, merged_config, get_server_port


def test_defaults_present_when_no_persisted(monkeypatch, tmp_path):
    # Ensure data dir is empty
    monkeypatch.chdir(tmp_path)
    cfg = merged_config()
    for k, v in DEFAULTS.items():
        assert cfg[k] == v


def test_server_port_env(monkeypatch):
    monkeypatch.setenv("QC_PORT", "19001")
    assert get_server_port() == 19001
    monkeypatch.delenv("QC_PORT", raising=False)
    assert get_server_port() == 18000
