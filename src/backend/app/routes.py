from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .config import merged_config, provider_readiness, get_server_port, save_persisted_config
from .auth import require_auth_token

router = APIRouter()


class ConfigPatch(BaseModel):
    provider: str | None = Field(default=None)
    model: str | None = Field(default=None)
    preferredTransport: str | None = Field(default=None)

    def normalized(self) -> dict:
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
                raise HTTPException(status_code=400, detail="preferredTransport must be 'sse' or 'ws'")
            out["preferredTransport"] = v
        return out


@router.get("/assistant/config")
async def get_assistant_config():
    cfg = merged_config()
    ready, reason = provider_readiness(cfg.get("provider"))
    # server_port is derived from environment and is read-only
    cfg_with_meta = {
        **cfg,
        "server_port": get_server_port(),
        "provider_ready": ready,
        "provider_reason": reason,
    }
    return cfg_with_meta


@router.patch("/assistant/config", dependencies=[require_auth_token])
async def patch_assistant_config(patch: ConfigPatch):
    # Validate and normalize inputs
    patch_values = patch.normalized()
    if not patch_values:
        return await get_assistant_config()

    # Persist patch values (atomic write inside save)
    save_persisted_config(patch_values)

    # Return updated, merged view with metadata
    return await get_assistant_config()
