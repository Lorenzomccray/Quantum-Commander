from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

from .utils import read_json, write_json_atomic, ensure_dir

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


def load_persisted_config() -> dict:
    return read_json(CONFIG_PATH)


def save_persisted_config(new_values: dict) -> None:
    # Persist only user-defined values (no derived fields like server_port)
    current = read_json(CONFIG_PATH)
    current.update(new_values)
    write_json_atomic(CONFIG_PATH, current)


def merged_config() -> dict:
    # Merge DEFAULTS with persisted values; DEFAULTS provide missing keys only
    persisted = load_persisted_config()
    merged = {**DEFAULTS, **persisted}
    return merged


def provider_readiness(provider: str | None) -> Tuple[bool, str | None]:
    if not provider:
        return False, "provider not set"
    provider = provider.lower()
    if provider == "openai":
        return (bool(os.getenv("OPENAI_API_KEY")), None if os.getenv("OPENAI_API_KEY") else "OPENAI_API_KEY not set")
    if provider == "anthropic":
        return (bool(os.getenv("ANTHROPIC_API_KEY")), None if os.getenv("ANTHROPIC_API_KEY") else "ANTHROPIC_API_KEY not set")
    if provider == "openrouter":
        return (bool(os.getenv("OPENROUTER_API_KEY")), None if os.getenv("OPENROUTER_API_KEY") else "OPENROUTER_API_KEY not set")
    return False, f"Unknown provider: {provider}"
