from __future__ import annotations

import os
import secrets
from pathlib import Path
from fastapi import Header, HTTPException, status

TOKEN_FILE = Path(".qc_token")


def _write_token_secure(path: Path, token: str) -> None:
    # Write token with 0600 permissions; avoid printing or logging the value
    path.write_text(token, encoding="utf-8")
    try:
        path.chmod(0o600)
    except Exception:
        # best-effort; ignore if filesystem doesn't support chmod
        pass


def ensure_token_on_startup() -> None:
    if os.getenv("QC_TOKEN"):
        # Respect provided env; do not write or print
        return
    token = secrets.token_urlsafe(32)
    _write_token_secure(TOKEN_FILE, token)
    # Set only for the running process
    os.environ["QC_TOKEN"] = token


def require_auth_token(x_auth_token: str | None = Header(default=None, alias="X-Auth-Token")) -> None:
    expected = os.getenv("QC_TOKEN")
    if not expected or not x_auth_token or secrets.compare_digest(x_auth_token, expected) is False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
