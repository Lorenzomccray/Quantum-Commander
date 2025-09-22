from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import json, time, os, uuid

router = APIRouter()
DB = Path(os.environ.get("QC_CHATS_DB","data/chats.json"))
DB.parent.mkdir(parents=True, exist_ok=True)
if not DB.exists(): DB.write_text("[]","utf-8")

# Optional Supabase
_SB_OK = False
try:
    from supabase import create_client
    _SB_OK = True
except Exception:
    _SB_OK = False
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
CHATS_TABLE = os.environ.get("QC_CHATS_TABLE", "chats")

def _sb_client():
    if not (_SB_OK and SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    except Exception:
        return None

class Message(BaseModel):
    role: str
    text: str
    ts: float | None = None

class ChatCreate(BaseModel):
    title: str
    transcript: list[Message]

def _load():
    try: return json.loads(DB.read_text("utf-8"))
    except Exception: return []

def _save(rows):
    tmp = DB.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(DB)

@router.get("/chats")
def list_chats():
    sb = _sb_client()
    if sb:
        try:
            data = sb.table(CHATS_TABLE).select("*").order("ts", desc=True).execute().data or []
            return {"ok": True, "chats": data}
        except Exception:
            pass
    return {"ok": True, "chats": _load()}

@router.post("/chats")
def create_chat(c: ChatCreate):
    rows = _load()
    cid = uuid.uuid4().hex
    row = {"id": cid, "title": c.title, "ts": time.time(), "transcript": [m.model_dump() for m in c.transcript]}
    sb = _sb_client()
    if sb:
        try:
            res = sb.table(CHATS_TABLE).insert(row).execute()
            data = (res.data or [row])[0]
            return {"ok": True, "chat": data}
        except Exception:
            pass
    rows.insert(0, row)
    _save(rows)
    return {"ok": True, "chat": row}

@router.get("/chats/{cid}")
def get_chat(cid: str):
    sb = _sb_client()
    if sb:
        try:
            res = sb.table(CHATS_TABLE).select("*").eq("id", cid).limit(1).execute()
            rows = res.data or []
            if rows:
                return {"ok": True, "chat": rows[0]}
        except Exception:
            pass
    for r in _load():
        if r["id"] == cid:
            return {"ok": True, "chat": r}
    raise HTTPException(404, "chat not found")

