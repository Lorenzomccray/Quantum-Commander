from typing import Dict, Any, Optional
from app.settings import settings
import threading
import asyncio

SYSTEM_PROMPT = """
You are Quantum Commander - an interactive AI pair-programmer and ops assistant. Be concise, actionable, and safe.
Always structure your replies to collaborate effectively:
1) Acknowledge the request and restate key intent;
2) Ask up to 3 targeted clarifying questions if requirements are ambiguous;
3) Propose a short, numbered plan;
4) Provide the minimal code or commands to achieve the goal;
5) Offer an execution directive and wait for user confirmation.

Procedures and style:
- Use numbered steps for procedures. Prefer least-privilege actions and safe defaults.
- On Fedora Linux, prefer 'dnf' for package management.
- Never include secrets. Avoid destructive commands unless explicitly requested, and call out risks.

Execution directives understood by the UI (emit exactly one directive per action line):
- RUN_USER: <cmd>   # non-root shell command (preferred when possible)
- RUN_ROOT: <cmd>   # root command; only emit when the user explicitly needs privileged actions
- EXT_INSTALL: <name>.py   # when proposing custom code, include this line then a single code block with the full module to write
- EXT_CALL: <module>:<func> args=[...]   # after installing, call a function with JSON args

Usage guidance:
- For shell tasks: propose the command and include one RUN_USER/ROOT line.
- For custom logic: include EXT_INSTALL:<module>.py, then one fenced code block of the module, then EXT_CALL:<module>:<func> with args.
- After listing directives, end with: Say "proceed" to run.
- If the user asks to "run" without details, ask clarifying questions first; once confirmed, output directives.
"""


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
    if provider == "deepseek":
        # DeepSeek supports an OpenAI-compatible API; use the OpenAI client with a custom base_url
        from openai import OpenAI
        base_url = getattr(settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        return "openai", OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=base_url, timeout=timeout)
    raise ValueError(f"Unsupported MODEL_PROVIDER: {provider}")


def run_once(*, provider: str, model: str, message: str, temperature: float, max_tokens: int) -> str:
    """Synchronous helper to invoke make_agent from non-async contexts.
    It safely creates a new event loop when needed, or runs in a background thread
    if already inside an active loop.
    """
    meta: Dict[str, Any] = {
        "provider": provider,
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async def _call():
        return await make_agent(message, meta)

    try:
        # Prefer running directly when no loop is active in this thread
        return asyncio.run(_call())
    except RuntimeError:
        # If there's already a running loop, execute in a background thread
        result_holder: Dict[str, Any] = {}

        def _runner():
            result_holder["result"] = asyncio.run(_call())

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()
        return result_holder.get("result", "")


def _model_name(provider: str, model_override: str | None = None) -> str:
    if model_override:
        return model_override
    return {
        "openai": settings.OPENAI_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
        "groq":   settings.GROQ_MODEL,
        "deepseek": settings.DEEPSEEK_MODEL,
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


def _openai_has_responses(client) -> bool:
    try:
        return hasattr(client, "responses") and hasattr(client.responses, "create")
    except Exception:
        return False


def _openai_resp_text(resp) -> str:
    """Best-effort extraction of text from OpenAI Responses API objects across versions."""
    try:
        txt = getattr(resp, "output_text", None)
        if txt:
            return str(txt)
    except Exception:
        pass
    # Fallback: iterate over output[].content[].text if present
    try:
        out = []
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                t = getattr(c, "text", None)
                if t:
                    out.append(str(t))
        if out:
            return "".join(out)
    except Exception:
        pass
    return ""


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
    sys_prompt = (meta.get("system_prompt") or SYSTEM_PROMPT)

    try:
        if provider == "openai":
            if _openai_has_responses(client):
                # Prefer the newer Responses API when available (works across modern models)
                resp = client.responses.create(
                    model=model,
                    instructions=sys_prompt,
                    input=user_prompt,
                )
                return _openai_resp_text(resp).strip()
            # Otherwise fall back to Chat Completions for broad compatibility
            kwargs = {
                "model": model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            # Supply temperature/tokens only for legacy/chat-compatible models
            if not _openai_use_responses(model):
                kwargs.update(_openai_tokens_kw(model, max_tokens))
                kwargs["temperature"] = temperature
            resp = client.chat.completions.create(**kwargs)
            return (resp.choices[0].message.content or "").strip()

        if provider == "anthropic":
            resp = client.messages.create(
                model=model,
                system=sys_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return "".join([b.text for b in resp.content if getattr(b, "type", "") == "text"]).strip()

        if provider == "groq":
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": sys_prompt},
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
    sys_prompt = (meta.get("system_prompt") or SYSTEM_PROMPT)

    queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def run_stream():
        try:
            if provider == "openai":
                if _openai_has_responses(client):
                    # Streaming with the Responses API (preferred)
                    with client.responses.stream(
                        model=model,
                        instructions=sys_prompt,
                        input=user_prompt,
                    ) as stream:
                        for event in stream:
                            try:
                                if getattr(event, "type", "") == "response.output_text.delta":
                                    delta = getattr(event, "delta", "") or ""
                                    if delta:
                                        loop.call_soon_threadsafe(queue.put_nowait, delta)
                                elif getattr(event, "type", "") == "response.error":
                                    err = getattr(getattr(event, "error", None), "message", "")
                                    if err:
                                        loop.call_soon_threadsafe(queue.put_nowait, f"[agent-error] {err}")
                            except Exception:
                                pass
                elif _openai_use_responses(model) and not _openai_has_responses(client):
                    # Compatibility fallback: Responses API unavailable in client version.
                    # Perform a non-streaming request and yield the whole text once.
                    try:
                        text = make_agent.__wrapped__(message=user_prompt, meta={
                            "provider": "openai",
                            "model": model,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                            "system_prompt": sys_prompt,
                        }) if hasattr(make_agent, "__wrapped__") else None
                    except Exception:
                        text = None
                    if not text:
                        try:
                            # Final fallback: minimal Chat Completions without extra params
                            resp = client.chat.completions.create(
                                model=model,
                                messages=[
                                    {"role": "system", "content": sys_prompt},
                                    {"role": "user", "content": user_prompt},
                                ],
                                stream=False,
                            )
                            text = (resp.choices[0].message.content or "")
                        except Exception as e:
                            loop.call_soon_threadsafe(queue.put_nowait, f"[agent-error] {type(e).__name__}: {e}")
                            text = None
                    if text:
                        loop.call_soon_threadsafe(queue.put_nowait, text)
                else:
                    # Streaming via Chat Completions. For models that dislike max_tokens,
                    # omit it and rely on provider defaults.
                    kwargs = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": True,
                    }
                    # For chat-compatible models we can send tokens/temperature; for newer models, omit
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
                        {"role": "system", "content": sys_prompt},
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
                    system=sys_prompt,
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
            # Provide system prompt natively instead of mutating message
            sp = (b.get("system_prompt") or "").strip()
            if sp and not payload.get("system_prompt"):
                payload["system_prompt"] = sp
            break
    return payload

