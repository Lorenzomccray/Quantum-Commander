from __future__ import annotations

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import require_auth_token
from .config import get_server_port, merged_config, provider_readiness, save_persisted_config
from .providers import inline_suggestion

router = APIRouter()


class ConfigPatch(BaseModel):
    provider: str | None = Field(default=None)
    model: str | None = Field(default=None)
    preferredTransport: str | None = Field(default=None)

    def normalized(self) -> dict[str, str]:
        out: dict = {}
        if self.provider is not None:
            if not isinstance(self.provider, str) or not self.provider.strip():
                raise HTTPException(status_code=400, detail="provider must be a non-empty string")
            out["provider"] = self.provider
        if self.model is not None:
            if not isinstance(self.model, str) or not self.model.strip():
                raise HTTPException(status_code=400, detail="model must be a non-empty string")
            out["model"] = self.model
        if self.preferredTransport is not None:
            v = self.preferredTransport.lower()
            if v not in {"sse", "ws"}:
                raise HTTPException(
                    status_code=400, detail="preferredTransport must be 'sse' or 'ws'"
                )
            out["preferredTransport"] = v
        return out


class ConfigResponse(BaseModel):
    provider: str
    model: str
    preferredTransport: str
    server_port: int
    provider_ready: bool
    provider_reason: str | None


@router.get("/assistant/config")
async def get_assistant_config() -> ConfigResponse:
    cfg = merged_config()
    ready, reason = provider_readiness(cfg.get("provider"))
    # server_port is derived from environment and is read-only
    cfg_with_meta = ConfigResponse(
        provider=cfg["provider"],
        model=cfg["model"],
        preferredTransport=cfg["preferredTransport"],
        server_port=get_server_port(),
        provider_ready=ready,
        provider_reason=reason,
    )
    return cfg_with_meta


@router.patch("/assistant/config", dependencies=[Depends(require_auth_token)])
async def patch_assistant_config(patch: ConfigPatch) -> ConfigResponse:
    # Validate and normalize inputs
    patch_values = patch.normalized()
    if not patch_values:
        return await get_assistant_config()

    # Persist patch values (atomic write inside save)
    save_persisted_config(patch_values)

    # Return updated, merged view with metadata
    return await get_assistant_config()


@router.post("/assistant/inline")
async def inline_completion(
    request: Request, prompt: str = Body(..., embed=True)
) -> dict[str, str]:
    """
    Produce a short inline suggestion using the configured provider and model.
    Supported providers: openai, anthropic, deepseek, openrouter.
    Returns {"completion": ""} when misconfigured or on error.
    """
    cfg = merged_config()
    provider = (cfg.get("provider") or "").lower()
    model = cfg.get("model") or ""
    if not provider or not model or not prompt:
        return {"completion": ""}

    client = getattr(request.app.state, "http", None)
    if client is None:
        async with httpx.AsyncClient(timeout=15.0) as tmp:
            text = await inline_suggestion(provider, model, prompt, tmp)
            return {"completion": text}

    text = await inline_suggestion(provider, model, prompt, client)
    return {"completion": text}
