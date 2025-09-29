# Unit tests for optional metrics and provider dispatch
from __future__ import annotations

import os

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_metrics_disabled_by_default(monkeypatch):
    """By default, /metrics should not exist."""
    monkeypatch.delenv("QC_METRICS", raising=False)
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/metrics")
        assert r.status_code == 404


def test_metrics_enabled_when_flag_set(monkeypatch):
    """If QC_METRICS=1 and prometheus lib available, /metrics should exist."""
    monkeypatch.setenv("QC_METRICS", "1")
    
    try:
        # Try to import to see if the lib is available
        from prometheus_fastapi_instrumentator import Instrumentator  # noqa: F401
        prometheus_available = True
    except ImportError:
        prometheus_available = False
    
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/metrics")
        if prometheus_available:
            # Should succeed (200) and contain prometheus metrics
            assert r.status_code == 200
            assert "http_request" in r.text or "# HELP" in r.text
        else:
            # Lib not available; endpoint should not exist
            assert r.status_code == 404