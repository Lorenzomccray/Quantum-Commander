from fastapi import APIRouter
from app.settings import settings
import os
import time
import platform
from pathlib import Path

router = APIRouter()

STARTED_AT = time.time()


@router.get("/health")
def health():
    provider = (settings.MODEL_PROVIDER or "").lower()
    model = None
    has_key = False

    # Known providers and some common model options
    available_providers = ["openai", "anthropic", "groq", "deepseek"]
    model_catalog = {
        "openai": [
            "gpt-5", "gpt-5-mini", "gpt-5-nano",
            "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
            "o3", "o4-mini",
            "gpt-4o", "gpt-4o-mini",
        ],
        "anthropic": [
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
            "claude-3-opus-latest",
        ],
        "groq": [
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
        ],
        "deepseek": [
            "deepseek-reasoner",
            "deepseek-chat",
        ],
    }

    keys_map = {
        "openai": bool(getattr(settings, "OPENAI_API_KEY", None)),
        "anthropic": bool(getattr(settings, "ANTHROPIC_API_KEY", None)),
        "groq": bool(getattr(settings, "GROQ_API_KEY", None)),
        "deepseek": bool(getattr(settings, "DEEPSEEK_API_KEY", None)),
    }

    if provider == "openai":
        model = settings.OPENAI_MODEL
        has_key = keys_map["openai"]
    elif provider == "anthropic":
        model = settings.ANTHROPIC_MODEL
        has_key = keys_map["anthropic"]
    elif provider == "groq":
        model = settings.GROQ_MODEL
        has_key = keys_map["groq"]
    elif provider == "deepseek":
        model = settings.DEEPSEEK_MODEL
        has_key = keys_map["deepseek"]

    # Determine stores
    import importlib
    supa_ok = bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)
    try:
        importlib.import_module('supabase')
    except Exception:
        supa_ok = False
    stores = {
        "bots": "supabase" if supa_ok else "json",
        "chats": "supabase" if supa_ok else "json",
        "kb": "supabase" if supa_ok else "json",
        "skills": "supabase" if supa_ok else "json",
        "files": "fs",
    }

    # Prefer a fast default model when not set
    if not model and provider == "openai":
        model = "gpt-4o-mini"

    return {
        "ok": True,
        "provider": provider,
        "model": model,
        "api_key_set": has_key,
        "temperature": settings.TEMPERATURE,
        "max_tokens": settings.MAX_TOKENS,
        "available_providers": available_providers,
        "available_models": model_catalog.get(provider, model_catalog["openai"]),
        "models_by_provider": model_catalog,
        "providers_with_keys": keys_map,
        "ws": True,
        "sse": True,
        "stores": stores,
        "uptime_s": int(time.time() - STARTED_AT),
        "python": platform.python_version(),
    }


def _check_upload_dir():
    root = Path(os.environ.get("QC_UPLOAD_DIR", "uploads"))
    ok = True
    msg = ""
    try:
        root.mkdir(parents=True, exist_ok=True)
        testf = root / (".ready_" + str(int(time.time()*1000)))
        testf.write_text("ok", encoding="utf-8")
        testf.unlink(missing_ok=True)
    except Exception as e:
        ok = False
        msg = f"upload dir not writable: {e}"
    return ok, msg, str(root)


def _check_ops_helper():
    path = Path("/usr/local/bin/qc-rootsh")
    try:
        return path.exists() and os.access(path, os.X_OK), str(path)
    except Exception:
        return False, str(path)


@router.get("/live")
def live():
    return {"ok": True, "uptime_s": int(time.time() - STARTED_AT)}


@router.get("/ready")
def ready():
    warnings = []
    errors = []

    # Templates present
    tpl_ok = Path(__file__).resolve().parent.parent / "templates" / "index.html"
    if not tpl_ok.exists():
        errors.append("UI template missing: templates/index.html")

    # Upload dir
    up_ok, up_msg, up_dir = _check_upload_dir()
    if not up_ok:
        errors.append(up_msg)

    # Providers keys summary
    keys_map = {
        "openai": bool(getattr(settings, "OPENAI_API_KEY", None)),
        "anthropic": bool(getattr(settings, "ANTHROPIC_API_KEY", None)),
        "groq": bool(getattr(settings, "GROQ_API_KEY", None)),
        "deepseek": bool(getattr(settings, "DEEPSEEK_API_KEY", None)),
    }
    if not any(keys_map.values()):
        warnings.append("No API keys configured; responses will fail until a provider key is set")

    # Supabase config presence (optional)
    supa_cfg = bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)
    if not supa_cfg:
        warnings.append("Supabase not configured; falling back to local JSON storage")

    # Ops helper presence (optional)
    ops_ok, ops_path = _check_ops_helper()
    if not ops_ok:
        warnings.append(f"Root ops helper not found at {ops_path}; Root Ops disabled")

    ok = (len(errors) == 0)
    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "uptime_s": int(time.time() - STARTED_AT),
        "details": {
            "upload_dir": up_dir,
            "providers_with_keys": keys_map,
            "ops_helper": ops_path,
        },
    }

