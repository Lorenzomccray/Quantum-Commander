from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
import json, uuid, time, os

router = APIRouter()
DB_PATH = Path(os.environ.get("QC_BOTS_DB","data/bots.json"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
if not DB_PATH.exists(): DB_PATH.write_text("[]", encoding="utf-8")

def _load():
    try: return json.loads(DB_PATH.read_text("utf-8"))
    except Exception: return []

def _save(bots):
    tmp = DB_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(bots, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(DB_PATH)

class BotProfile(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    emoji: str = "🤖"
    system_prompt: str = "You are a helpful assistant."
    provider: str = "openai"
    model: str = "gpt-5"
    temperature: float = 0.2
    max_tokens: int = 800
    tools_enabled: bool = False
    created_at: float = Field(default_factory=lambda: time.time())
    updated_at: float = Field(default_factory=lambda: time.time())

class BotUpdate(BaseModel):
    name: str | None = None
    emoji: str | None = None
    system_prompt: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    tools_enabled: bool | None = None

@router.get("/bots")
def list_bots():
    return {"ok": True, "bots": _load()}

@router.post("/bots")
def create_bot(bot: BotProfile):
    bots = _load()
    bots.insert(0, bot.model_dump())
    _save(bots)
    return {"ok": True, "bot": bot}

@router.get("/bots/{bot_id}")
def get_bot(bot_id: str):
    for b in _load():
        if b["id"] == bot_id:
            return {"ok": True, "bot": b}
    raise HTTPException(404, "bot not found")

@router.patch("/bots/{bot_id}")
def update_bot(bot_id: str, patch: BotUpdate):
    bots = _load()
    for i,b in enumerate(bots):
        if b["id"] == bot_id:
            data = b | {k:v for k,v in patch.model_dump(exclude_none=True).items()}
            data["updated_at"] = time.time()
            bots[i] = data
            _save(bots)
            return {"ok": True, "bot": data}
    raise HTTPException(404, "bot not found")

@router.delete("/bots/{bot_id}")
def delete_bot(bot_id: str):
    bots = _load()
    nb = [b for b in bots if b["id"] != bot_id]
    if len(nb) == len(bots):
        raise HTTPException(404, "bot not found")
    _save(nb)
    return {"ok": True, "deleted": bot_id}

