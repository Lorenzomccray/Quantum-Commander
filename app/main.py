from fastapi import APIRouter
from app.settings import settings

router = APIRouter()


@router.get("/health")
def health():
    provider = (settings.MODEL_PROVIDER or "").lower()
    model = None
    has_key = False

    # Known providers and some common model options
    available_providers = ["openai", "anthropic", "groq"]
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
    }

    if provider == "openai":
        model = settings.OPENAI_MODEL
        has_key = bool(settings.OPENAI_API_KEY)
    elif provider == "anthropic":
        model = settings.ANTHROPIC_MODEL
        has_key = bool(settings.ANTHROPIC_API_KEY)
    elif provider == "groq":
        model = settings.GROQ_MODEL
        has_key = bool(settings.GROQ_API_KEY)

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
        "ws": True,
        "sse": True,
        "stores": {"bots": "json-or-supabase", "chats": "json", "kb": "json", "files": "fs"},
    }

