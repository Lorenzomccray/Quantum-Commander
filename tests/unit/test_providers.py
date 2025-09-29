# Unit tests for centralized provider dispatch
from __future__ import annotations

import httpx
import pytest
import respx

from backend.app.providers import inline_suggestion


@pytest.mark.asyncio
@respx.mock
async def test_inline_suggestion_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "hello world"}}]
        })
    )
    
    async with httpx.AsyncClient() as client:
        result = await inline_suggestion("openai", "gpt-4", "test prompt", client)
        assert result == "hello world"


@pytest.mark.asyncio
async def test_inline_suggestion_missing_key():
    """Should return empty string when API key is missing."""
    async with httpx.AsyncClient() as client:
        result = await inline_suggestion("openai", "gpt-4", "test prompt", client)
        assert result == ""


@pytest.mark.asyncio
async def test_inline_suggestion_unsupported_provider():
    """Should return empty string for unsupported providers."""
    async with httpx.AsyncClient() as client:
        result = await inline_suggestion("unsupported", "model", "test prompt", client)
        assert result == ""


@pytest.mark.asyncio
@respx.mock
async def test_inline_suggestion_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(200, json={
            "content": [{"type": "text", "text": "anthropic response"}]
        })
    )
    
    async with httpx.AsyncClient() as client:
        result = await inline_suggestion("anthropic", "claude-3-haiku", "test prompt", client)
        assert result == "anthropic response"


@pytest.mark.asyncio
@respx.mock
async def test_inline_suggestion_http_error():
    """Should return empty string on HTTP errors."""
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="Server Error")
    )
    
    async with httpx.AsyncClient() as client:
        result = await inline_suggestion("openai", "gpt-4", "test prompt", client)
        assert result == ""