from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import json, time, os, uuid

router = APIRouter()
DB = Path(os.environ.get("QC_CHATS_DB","data/chats.json"))
DB.parent.mkdir(parents=True, exist_ok=True)
if not DB.exists(): DB.write_text("[]","utf-8")

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
    return {"ok": True, "chats": _load()}

@router.post("/chats")
def create_chat(c: ChatCreate):
    rows = _load()
    cid = uuid.uuid4().hex
    row = {"id": cid, "title": c.title, "ts": time.time(), "transcript": [m.model_dump() for m in c.transcript]}
    rows.insert(0, row)
    _save(rows)
    return {"ok": True, "chat": row}

@router.get("/chats/{cid}")
def get_chat(cid: str):
    for r in _load():
        if r["id"] == cid:
            return {"ok": True, "chat": r}
    raise HTTPException(404, "chat not found")

