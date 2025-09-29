# Unit tests for inline completion endpoint
from __future__ import annotations

import os

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app import routes


client = TestClient(app)


def _set_provider(monkeypatch, provider: str, model: str = "gpt-4o-mini"):
    monkeypatch.setattr(routes, "merged_config", lambda: {"provider": provider, "model": model})


def test_inline_missing_api_key_returns_empty(monkeypatch):
    _set_provider(monkeypatch, "openai")
    # Ensure key not set
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = client.post("/assistant/inline", json={"prompt": "hello"})
    assert r.status_code == 200
    assert r.json()["completion"] == ""


@respx.mock
def test_inline_openai_success(monkeypatch):
    _set_provider(monkeypatch, "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "hi there"}}]
        })
    )
    r = client.post("/assistant/inline", json={"prompt": "hello"})
    assert r.status_code == 200
    assert r.json()["completion"] == "hi there"
    assert route.called


@respx.mock
def test_inline_anthropic_success(monkeypatch):
    _set_provider(monkeypatch, "anthropic", model="claude-3-haiku")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json={
            "content": [{"type": "text", "text": "anthropic ok"}]
        })
    )
    r = client.post("/assistant/inline", json={"prompt": "hello"})
    assert r.status_code == 200
    assert r.json()["completion"] == "anthropic ok"
    assert route.called


@respx.mock
def test_inline_deepseek_success(monkeypatch):
    _set_provider(monkeypatch, "deepseek", model="deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "deep"}}]
        })
    )
    r = client.post("/assistant/inline", json={"prompt": "hello"})
    assert r.status_code == 200
    assert r.json()["completion"] == "deep"
    assert route.called


@respx.mock
def test_inline_openrouter_success(monkeypatch):
    _set_provider(monkeypatch, "openrouter", model="meta-llama/llama-3-8b-instruct")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "router"}}]
        })
    )
    r = client.post("/assistant/inline", json={"prompt": "hello"})
    assert r.status_code == 200
    assert r.json()["completion"] == "router"
    assert route.called
