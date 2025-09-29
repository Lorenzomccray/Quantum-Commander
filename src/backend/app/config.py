from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .utils import read_json, write_json_atomic

DATA_DIR = Path("data")
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULTS = {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "preferredTransport": "sse",
}


def get_server_port() -> int:
    try:
        return int(os.getenv("QC_PORT", "18000"))
    except ValueError:
        return 18000


def load_persisted_config() -> dict[str, Any]:
    return read_json(CONFIG_PATH)


def save_persisted_config(new_values: dict[str, Any]) -> None:
    # Persist only user-defined values (no derived fields like server_port)
    current = read_json(CONFIG_PATH)
    current.update(new_values)
    write_json_atomic(CONFIG_PATH, current)


def merged_config() -> dict[str, Any]:
    # Merge DEFAULTS with persisted values; DEFAULTS provide missing keys only
    persisted = load_persisted_config()
    merged: dict[str, Any] = {**DEFAULTS, **persisted}
    return merged


def provider_readiness(provider: str | None) -> tuple[bool, str | None]:
    if not provider:
        return False, "provider not set"
    provider = provider.lower()
    if provider == "openai":
        ok = bool(os.getenv("OPENAI_API_KEY"))
        return ok, None if ok else "OPENAI_API_KEY not set"
    if provider == "anthropic":
        ok = bool(os.getenv("ANTHROPIC_API_KEY"))
        return ok, None if ok else "ANTHROPIC_API_KEY not set"
    if provider == "openrouter":
        ok = bool(os.getenv("OPENROUTER_API_KEY"))
        return ok, None if ok else "OPENROUTER_API_KEY not set"
    return False, f"Unknown provider: {provider}"
