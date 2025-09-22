from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Query

REPO_ROOT = Path(__file__).resolve().parent.parent
router = APIRouter()


def _verify(x_vc_token: str = Header(default="")):
    token = os.getenv("VC_TOKEN") or os.getenv("OPS_TOKEN")  # fall back to ops token if set
    if not token or x_vc_token != token:
        raise HTTPException(401, "unauthorized")


def _inside_repo(p: Path) -> bool:
    try:
        p.resolve().relative_to(REPO_ROOT)
        return True
    except Exception:
        return False


def _code_path() -> str:
    return os.environ.get("CODE_CLI", "code")


@router.post("/vscode/open")
def vscode_open(path: str = Query(..., description="Repo-relative file path"), line: int = 1, col: int = 1, x_vc_token: str = Header(default="")):
    _verify(x_vc_token)
    p = (REPO_ROOT / path).resolve()
    if not _inside_repo(p):
        raise HTTPException(400, "path must be inside repository root")
    if not p.exists():
        raise HTTPException(404, "file not found")
    cmd = [_code_path(), "--reuse-window", "--goto", f"{str(p)}:{line}:{col}"]
    cp = subprocess.run(cmd, text=True, capture_output=True)
    return {"ok": cp.returncode == 0, "cmd": " ".join(shlex.quote(x) for x in cmd), "rc": cp.returncode}


@router.post("/vscode/diff")
def vscode_diff(left: str, right: str, x_vc_token: str = Header(default="")):
    _verify(x_vc_token)
    lp = (REPO_ROOT / left).resolve()
    rp = (REPO_ROOT / right).resolve()
    if not (_inside_repo(lp) and _inside_repo(rp)):
        raise HTTPException(400, "paths must be inside repository root")
    if not (lp.exists() and rp.exists()):
        raise HTTPException(404, "left or right file not found")
    cmd = [_code_path(), "--reuse-window", "--diff", str(lp), str(rp)]
    cp = subprocess.run(cmd, text=True, capture_output=True)
    return {"ok": cp.returncode == 0, "rc": cp.returncode}


@router.post("/vscode/open-workspace")
def vscode_open_workspace(x_vc_token: str = Header(default="")):
    _verify(x_vc_token)
    ws = Path(os.environ.get("VC_WORKSPACE", str(REPO_ROOT.parent / "DevWorkspace.code-workspace")))
    cmd = [_code_path(), str(ws)]
    cp = subprocess.run(cmd, text=True, capture_output=True)
    return {"ok": cp.returncode == 0, "workspace": str(ws), "rc": cp.returncode}