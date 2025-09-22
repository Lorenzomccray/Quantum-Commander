from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from app.settings import settings

# Optional imports from sibling modules (best-effort)
try:
    from .routes_ops import DANGER as OPS_DANGER_PATTERNS  # type: ignore
except Exception:  # pragma: no cover - keep endpoint resilient
    OPS_DANGER_PATTERNS = []  # type: ignore

router = APIRouter()

REPO_ROOT = Path(__file__).resolve().parent.parent


def _git(cmd: List[str]) -> Optional[str]:
    try:
        cp = subprocess.run(cmd, cwd=str(REPO_ROOT), text=True, capture_output=True, check=True)
        return (cp.stdout or "").strip() or None
    except Exception:
        return None


def _git_info() -> Dict[str, Optional[str]]:
    return {
        "sha": _git(["git", "rev-parse", "--short", "HEAD"]),
        "branch": _git(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "remote_url": _git(["git", "remote", "get-url", "origin"]),
    }


def _provider_info() -> Dict[str, Any]:
    provider = (settings.MODEL_PROVIDER or "").lower()
    model = None
    keys = {
        "openai": bool(getattr(settings, "OPENAI_API_KEY", None)),
        "anthropic": bool(getattr(settings, "ANTHROPIC_API_KEY", None)),
        "groq": bool(getattr(settings, "GROQ_API_KEY", None)),
        "deepseek": bool(getattr(settings, "DEEPSEEK_API_KEY", None)),
    }
    if provider == "openai":
        model = settings.OPENAI_MODEL
    elif provider == "anthropic":
        model = settings.ANTHROPIC_MODEL
    elif provider == "groq":
        model = settings.GROQ_MODEL
    elif provider == "deepseek":
        model = settings.DEEPSEEK_MODEL
    return {
        "provider": provider,
        "model": model,
        "providers_with_keys": keys,
    }


def _tools_info() -> List[Dict[str, Any]]:
    tools: List[Dict[str, Any]] = []
    # Terminal/ops tool (root shell helper)
    ops_helper = Path("/usr/local/bin/qc-rootsh")
    tools.append(
        {
            "name": "ops-shell",
            "enabled": ops_helper.exists() and os.access(ops_helper, os.X_OK),
            "dangerous": True,
            "requiresApproval": True,
            "token_set": bool(os.getenv("OPS_TOKEN")),
        }
    )
    # Storage/backends
    supa_ok = bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)
    tools.append({"name": "supabase", "enabled": supa_ok, "dangerous": False})
    tools.append({"name": "json-fs-store", "enabled": True, "dangerous": False})
    # Containers (presence only)
    def _ok(cmd: List[str]) -> bool:
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except Exception:
            return False
    tools.append({"name": "podman", "enabled": _ok(["podman", "--version"]), "dangerous": False})
    tools.append({"name": "docker", "enabled": _ok(["docker", "--version"]), "dangerous": False})
    return tools


def _policies_info() -> Dict[str, Any]:
    # Rule files discovered in repo root
    rule_files: List[str] = []
    for name in ("AGENTS.MD", "AGENTS.md", "agents.md", "WARP.md"):
        p = REPO_ROOT / name
        if p.exists():
            rule_files.append(str(p.name))
    exec_policy = os.getenv("EXEC_POLICY", "alwaysAsk")  # external assistants may read this
    allowed_commands = []
    try:
        allowed_commands = json.loads(os.getenv("ALLOWED_COMMANDS", "[]"))
    except Exception:
        allowed_commands = []
    return {
        "rule_files": rule_files,
        "exec_policy": exec_policy,
        "allowed_commands": allowed_commands,
        "ops_danger_patterns": OPS_DANGER_PATTERNS,
    }


STARTED_AT = time.time()


@router.get("/self", summary="Assistant self-status and capabilities")
def self_status() -> Dict[str, Any]:
    identity = {
        "name": os.getenv("ASSISTANT_NAME", "quantum-commander"),
        "version": os.getenv("ASSISTANT_VERSION", "0.0.0"),
    }
    models = [_provider_info()]
    tools = _tools_info()
    policies = _policies_info()
    env = {
        "os": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "repo_root": str(REPO_ROOT),
    }
    health = {
        "uptime_s": int(time.time() - STARTED_AT),
        "status": "ok",
    }
    ident = {**identity, **_git_info()}

    # Build a compact summary for chat/UI
    enabled_tools = ", ".join([t["name"] for t in tools if t.get("enabled")]) or "none"
    prov = models[0].get("provider") or "(none)"
    model = models[0].get("model") or "(unset)"
    keys = models[0].get("providers_with_keys") or {}
    keys_on = [k for k, v in keys.items() if v]
    summary = (
        f"{ident.get('name')}@{ident.get('branch') or '?'}({ident.get('sha') or '?'}) "
        f"on {env['os']} py{env['python']} — provider: {prov}, model: {model}, "
        f"keys: {','.join(keys_on) if keys_on else 'none'}, tools: {enabled_tools}, "
        f"policy: {policies.get('exec_policy')} allowed: {len(policies.get('allowed_commands') or [])}, "
        f"rules: {','.join(policies.get('rule_files') or []) or 'none'}, uptime: {health['uptime_s']}s"
    )

    return {
        "identity": ident,
        "models": models,
        "tools": tools,
        "policies": policies,
        "environment": env,
        "health": health,
        "summary": summary,
    }
