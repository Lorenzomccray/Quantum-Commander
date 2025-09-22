from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from pathlib import Path
import os, json, time, subprocess, re

# Simple KB writer (to mirror /kb/index behavior without importing FastAPI router)
_KB = Path(os.environ.get("QC_KB_DB", "data/kb.json"))
_KB.parent.mkdir(parents=True, exist_ok=True)
if not _KB.exists():
    _KB.write_text("[]", "utf-8")

def _kb_index(text: str, source: str):
    try:
        rows = json.loads(_KB.read_text("utf-8"))
    except Exception:
        rows = []
    item = {"id": f"kb_{int(time.time()*1000)}", "text": text, "source": source, "ts": time.time()}
    rows.insert(0, item)
    tmp = _KB.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(_KB)

router = APIRouter()
DB = Path(os.environ.get("QC_SKILLS_DB", "data/skills.json"))
DB.parent.mkdir(parents=True, exist_ok=True)
if not DB.exists():
    DB.write_text("[]", "utf-8")

# Optional Supabase wiring
_SB_OK = False
try:
    from supabase import create_client
    _SB_OK = True
except Exception:
    _SB_OK = False

SKILLS_TABLE = os.environ.get("QC_SKILLS_TABLE", "skills")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

def _sb_client():
    if not (_SB_OK and SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    except Exception:
        return None

def _use_sb():
    sb = _sb_client()
    if not sb: return None
    try:
        sb.table(SKILLS_TABLE).select("id").limit(1).execute()
        return sb
    except Exception:
        return None

class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1)
    cmd: str = Field(..., min_length=1)
    is_root: bool = False
    tags: list[str] = []

class SkillUpdate(BaseModel):
    name: str | None = None
    cmd: str | None = None
    is_root: bool | None = None
    tags: list[str] | None = None

class SkillRunReq(BaseModel):
    name: str | None = None
    id: str | None = None
    args: list[str] = []
    confirm: bool = False


def _load():
    try:
        return json.loads(DB.read_text("utf-8"))
    except Exception:
        return []

def _save(rows):
    tmp = DB.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(DB)


def _find_skill(name: str | None, sid: str | None):
    rows = _load()
    if sid:
        for r in rows:
            if r.get("id") == sid:
                return r
    if name:
        lname = name.strip().lower()
        for r in rows:
            if r.get("name", "").strip().lower() == lname:
                return r
    return None


@router.get("/skills")
def list_skills():
    sb = _use_sb()
    if sb:
        try:
            data = sb.table(SKILLS_TABLE).select("*").order("created_at", desc=True).execute().data or []
            return {"ok": True, "skills": data}
        except Exception:
            pass
    return {"ok": True, "skills": _load()}


@router.post("/skills")
def create_skill(s: SkillCreate):
    rows = _load()
    sid = f"sk_{int(time.time()*1000)}"
    row = {
        "id": sid,
        "name": s.name,
        "cmd": s.cmd,
        "is_root": bool(s.is_root),
        "tags": s.tags or [],
        "created_at": time.time(),
        "updated_at": time.time(),
        "usage": 0,
    }
    # Try supabase first
    sb = _use_sb()
    if sb:
        try:
            res = sb.table(SKILLS_TABLE).insert(row).execute()
            data = (res.data or [row])[0]
            return {"ok": True, "skill": data}
        except Exception:
            pass
    rows.insert(0, row)
    _save(rows)
    return {"ok": True, "skill": row}


@router.delete("/skills/{sid}")
def delete_skill(sid: str):
    sb = _use_sb()
    if sb:
        try:
            sb.table(SKILLS_TABLE).delete().eq("id", sid).execute()
            return {"ok": True, "deleted": sid}
        except Exception:
            pass
    rows = _load()
    nrows = [r for r in rows if r.get("id") != sid]
    if len(nrows) == len(rows):
        raise HTTPException(404, "not found")
    _save(nrows)
    return {"ok": True, "deleted": sid}


# Import ops token verification and danger detection
try:
    from .routes_ops import verify_ops_token as _verify_ops_token  # type: ignore
    from .routes_ops import looks_dangerous as _looks_dangerous  # type: ignore
except Exception:
    def _verify_ops_token(x_ops_token: str = Header(default="")):
        token = os.getenv("OPS_TOKEN")
        if not token or x_ops_token != token:
            raise HTTPException(401, "unauthorized")
        return True
    def _looks_dangerous(cmd: str) -> str | None:
        pats = [r"\brm\s+-rf\s+/(?!tmp|var/tmp)", r"\bmkfs\.", r"\bdd\s+if="]
        for p in pats:
            if re.search(p, cmd, flags=re.IGNORECASE):
                return p
        return None


@router.post("/skills/run")
def run_skill(req: SkillRunReq, _auth=Depends(_verify_ops_token)):
    sk = _find_skill(req.name, req.id)
    if not sk:
        raise HTTPException(404, "skill not found")
    cmd = sk.get("cmd", "")
    # Replace positional placeholders {0},{1},... if provided
    for i, a in enumerate(req.args or []):
        cmd = cmd.replace("{" + str(i) + "}", a)
    if not cmd:
        raise HTTPException(400, "empty cmd")

    if sk.get("is_root"):
        pat = _looks_dangerous(cmd)
        if pat and not req.confirm:
            raise HTTPException(412, detail={
                "confirmation_required": True,
                "pattern": pat,
                "preview": f"About to run as root: {cmd}",
            })
        args = ["/usr/bin/sudo", "-n", "/usr/local/bin/qc-rootsh", "--cwd", "/", "--env-json", "{}", cmd]
        cp = subprocess.run(args, text=True, capture_output=True)
        try:
            payload = json.loads(cp.stdout.strip() or "{}")
        except Exception:
            payload = {"ok": False, "stdout": cp.stdout, "stderr": cp.stderr, "rc": cp.returncode}
        if cp.returncode != 0 or not payload.get("ok", False):
            raise HTTPException(500, detail=payload)
        # Save to KB
        try:
            out = (payload.get("stdout", "") or "") + ("\n" + payload.get("stderr", "") if payload.get("stderr") else "")
            _kb_index(f"[skill:{sk.get('name')}] $ {cmd}\n\n{out[:4000]}", "skill-root")
        except Exception:
            pass
        return payload
    else:
        # Run as current user
        cp = subprocess.run(["/usr/bin/bash", "-lc", cmd], text=True, capture_output=True)
        try:
            _kb_index(f"[skill:{sk.get('name')}] $ {cmd}\n\n{(cp.stdout or '')[:4000]}\n{(cp.stderr or '')[:4000]}", "skill-user")
        except Exception:
            pass
        return {"ok": cp.returncode == 0, "stdout": cp.stdout, "stderr": cp.stderr, "rc": cp.returncode}

