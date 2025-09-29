from __future__ import annotations

import os
from typing import Any, cast

import httpx

# Provider handling centralized here


async def inline_suggestion(
    provider: str,
    model: str,
    prompt: str,
    client: httpx.AsyncClient,
) -> str:
    provider_l = provider.lower().strip()
    if not provider_l or not model or not prompt:
        return ""

    try:
        if provider_l == "openai":
            key = os.getenv("OPENAI_API_KEY")
            if not key:
                return ""
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 80,
                    "temperature": 0.2,
                },
            )
            r.raise_for_status()
            data = cast(dict[str, Any], r.json())
            content = (
                (data.get("choices") or [{}])[0]
                .get("message", {})  # type: ignore[index]
                .get("content", "")
            )
            return str(content).strip()

        if provider_l == "anthropic":
            key = os.getenv("ANTHROPIC_API_KEY")
            if not key:
                return ""
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 80,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            r.raise_for_status()
            data = cast(dict[str, Any], r.json())
            blocks = cast(list[dict[str, Any]], data.get("content") or [])
            for b in blocks:
                if b.get("type") == "text" and isinstance(b.get("text"), str):
                    return str(b["text"]).strip()
            return ""

        if provider_l == "deepseek":
            key = os.getenv("DEEPSEEK_API_KEY")
            if not key:
                return ""
            r = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 80,
                    "temperature": 0.2,
                },
            )
            r.raise_for_status()
            data = cast(dict[str, Any], r.json())
            content = (
                (data.get("choices") or [{}])[0]
                .get("message", {})  # type: ignore[index]
                .get("content", "")
            )
            return str(content).strip()

        if provider_l == "openrouter":
            key = os.getenv("OPENROUTER_API_KEY")
            if not key:
                return ""
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 80,
                    "temperature": 0.2,
                },
            )
            r.raise_for_status()
            data = cast(dict[str, Any], r.json())
            content = (
                (data.get("choices") or [{}])[0]
                .get("message", {})  # type: ignore[index]
                .get("content", "")
            )
            return str(content).strip()

    except Exception:
        return ""

    return ""
