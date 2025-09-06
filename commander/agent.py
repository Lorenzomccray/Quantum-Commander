from typing import Dict, Any, Optional
from app.settings import settings
import threading
import asyncio

SYSTEM_PROMPT = (
    "You are Quantum Commander. Be concise, actionable, and safe. "
    "Use numbered steps when giving procedures."
)


def _lazy_client(provider_override: str | None = None, timeout_s: float | None = None):
    provider = (provider_override or settings.MODEL_PROVIDER).lower()
    timeout = timeout_s if timeout_s is not None else settings.REQUEST_TIMEOUT_S
    if provider == "openai":
        from openai import OpenAI
        return "openai", OpenAI(api_key=settings.OPENAI_API_KEY, timeout=timeout)
    if provider == "anthropic":
        import anthropic
        return "anthropic", anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=timeout)
    if provider == "groq":
        from groq import Groq
        return "groq", Groq(api_key=settings.GROQ_API_KEY, timeout=timeout)
    raise ValueError(f"Unsupported MODEL_PROVIDER: {provider}")


def _model_name(provider: str, model_override: str | None = None) -> str:
    if model_override:
        return model_override
    return {
        "openai": settings.OPENAI_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
        "groq":   settings.GROQ_MODEL,
    }[provider]


def _openai_tokens_kw(model: str, max_tokens: int) -> dict:
    m = (model or "").lower()
    # Newer models (gpt-5 family, o* family, gpt-4o/4.1) expect max_completion_tokens (when using Chat Completions)
    if m.startswith("gpt-5") or m.startswith("o") or m.startswith("gpt-4o") or m.startswith("gpt-4.1"):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}


def _openai_use_responses(model: str) -> bool:
    m = (model or "").lower()
    return m.startswith("gpt-5") or m.startswith("o") or m.startswith("gpt-4o") or m.startswith("gpt-4.1")


async def make_agent(message: str, meta: Dict[str, Any] | None = None) -> str:
    meta = meta or {}
    provider_override = meta.get("provider")
    model_override = meta.get("model")
    temperature = float(meta.get("temperature", settings.TEMPERATURE))
    max_tokens = int(meta.get("max_tokens", settings.MAX_TOKENS))
    timeout_s = meta.get("timeout_s")

    provider, client = _lazy_client(provider_override=provider_override, timeout_s=timeout_s)
    model = _model_name(provider, model_override=model_override)
    user_prompt = message

    try:
        if provider == "openai":
            # Chat Completions path for broad compatibility. Some newer models
            # reject max_tokens; omit it in that case.
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            }
            if not _openai_use_responses(model):
                kwargs.update(_openai_tokens_kw(model, max_tokens))
                kwargs["temperature"] = temperature
            resp = client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()

        if provider == "anthropic":
            resp = client.messages.create(
                model=model,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return "".join([b.text for b in resp.content if getattr(b, "type", "") == "text"]).strip()

        if provider == "groq":
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()

    except Exception as e:
        # Graceful fallback: no stack traces to clients
        return f"[agent-error] {type(e).__name__}: {e}"


async def stream_agent(message: str, meta: Dict[str, Any] | None = None):
    """Async generator that yields text deltas as they arrive from the provider."""
    meta = meta or {}
    provider_override = meta.get("provider")
    model_override = meta.get("model")
    temperature = float(meta.get("temperature", settings.TEMPERATURE))
    max_tokens = int(meta.get("max_tokens", settings.MAX_TOKENS))
    timeout_s = meta.get("timeout_s")

    provider, client = _lazy_client(provider_override=provider_override, timeout_s=timeout_s)
    model = _model_name(provider, model_override=model_override)
    user_prompt = message

    queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def run_stream():
        try:
            if provider == "openai":
                # Streaming via Chat Completions. For models that dislike max_tokens,
                # omit it and rely on provider defaults.
                kwargs = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": True,
                }
                if not _openai_use_responses(model):
                    kwargs.update(_openai_tokens_kw(model, max_tokens))
                    kwargs["temperature"] = temperature
                resp = client.chat.completions.create(**kwargs)
                for chunk in resp:
                    try:
                        delta = chunk.choices[0].delta.content or ""
                    except Exception:
                        delta = ""
                    if delta:
                        loop.call_soon_threadsafe(queue.put_nowait, delta)
            elif provider == "groq":
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )
                for chunk in resp:
                    try:
                        delta = chunk.choices[0].delta.content or ""
                    except Exception:
                        delta = ""
                    if delta:
                        loop.call_soon_threadsafe(queue.put_nowait, delta)
            elif provider == "anthropic":
                with client.messages.stream(
                    model=model,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                ) as stream:
                    for event in stream:
                        try:
                            if getattr(event, "type", "") == "content_block_delta":
                                delta = getattr(getattr(event, "delta", None), "text", "")
                                if delta:
                                    loop.call_soon_threadsafe(queue.put_nowait, delta)
                        except Exception:
                            pass
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, f"[agent-error] {type(e).__name__}: {e}")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=run_stream, daemon=True).start()

    while True:
        chunk = await queue.get()
        if chunk is None:
            break
        yield chunk

# --- Bot overrides (JSON DB) ---
from pathlib import Path as _P
import json as _json

def _bots_db():
    path = _P("data/bots.json")
    if not path.exists(): return []
    try: return _json.loads(path.read_text("utf-8"))
    except Exception: return []

def apply_bot_overrides(payload: dict) -> dict:
    bot_id = (payload or {}).get("bot_id") or ""
    if not bot_id: return payload
    for b in _bots_db():
        if b.get("id") == bot_id:
            # Inject model/provider/params if not explicitly set by client
            payload.setdefault("provider", b.get("provider","openai"))
            payload.setdefault("model", b.get("model","gpt-5"))
            payload.setdefault("temperature", b.get("temperature",0.2))
            payload.setdefault("max_tokens", b.get("max_tokens",800))
            # Prepend system prompt
            sp = b.get("system_prompt") or ""
            if sp:
                msg = payload.get("message","")
                payload["message"] = f"[SYSTEM]\n{sp}\n[/SYSTEM]\n\n{msg}"
            break
    return payload

