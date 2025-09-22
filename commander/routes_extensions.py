from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from pathlib import Path
import os, importlib.util, sys

router = APIRouter()

REPO = Path(__file__).resolve().parent.parent
EXT_DIR = REPO / "extensions"
EXT_DIR.mkdir(parents=True, exist_ok=True)
(EXT_DIR / "__init__.py").write_text("# extensions package\n", encoding="utf-8") if not (EXT_DIR/"__init__.py").exists() else None

# Reuse ops token verification if available
try:
    from .routes_ops import verify_ops_token as _verify_ops_token  # type: ignore
except Exception:
    def _verify_ops_token(x_ops_token: str = Header(default="")):
        token = os.getenv("OPS_TOKEN")
        if not token or x_ops_token != token:
            raise HTTPException(401, "unauthorized")
        return True

class ExtInstall(BaseModel):
    name: str
    content: str

class ExtCall(BaseModel):
    module: str
    func: str
    args: list = []

@router.get("/extensions/list")
def ext_list():
    mods = [p.name for p in EXT_DIR.glob("*.py")]
    return {"ok": True, "modules": mods}

@router.post("/extensions/install")
def ext_install(req: ExtInstall, _auth=Depends(_verify_ops_token)):
    base = req.name.strip().lower()
    if not base.endswith('.py'):
        base += '.py'
    # sanitize
    safe = ''.join(ch for ch in base if ch.isalnum() or ch in ('_','-','.'))
    if not safe or '..' in safe or '/' in safe:
        raise HTTPException(400, "invalid name")
    path = EXT_DIR / safe
    path.write_text(req.content, encoding='utf-8')
    return {"ok": True, "file": path.name}

@router.post("/extensions/call")
def ext_call(req: ExtCall):
    modname = req.module.strip().replace('-', '_')
    if not modname.isidentifier():
        raise HTTPException(400, "invalid module")
    # import from extensions package
    full = f"extensions.{modname}"
    try:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        mod = __import__(full, fromlist=['*'])
        fn = getattr(mod, req.func)
    except Exception as e:
        raise HTTPException(404, f"not found: {e}")
    try:
        out = fn(*req.args)
    except Exception as e:
        raise HTTPException(500, f"call failed: {e}")
    return {"ok": True, "result": out}

