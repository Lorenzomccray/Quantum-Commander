from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import time
from commander.bots_dal import BotsDAL

router = APIRouter()
dal = BotsDAL()

class BotProfile(BaseModel):
    id: str | None = None
    name: str
    emoji: str = "🤖"
    system_prompt: str = "You are a helpful assistant."
    provider: str = "openai"
    model: str = "gpt-5"
    temperature: float = 0.2
    max_tokens: int = 800
    tools_enabled: bool = False
    created_at: float | None = None
    updated_at: float | None = None

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
    return {"ok": True, "bots": dal.list()}

@router.post("/bots")
def create_bot(bot: BotProfile):
    doc = bot.model_dump(exclude_none=True)
    if "created_at" not in doc: doc["created_at"] = time.time()
    created = dal.create(doc)
    return {"ok": True, "bot": created}

@router.get("/bots/{bot_id}")
def get_bot(bot_id: str):
    b = dal.get(bot_id)
    if not b: raise HTTPException(404, "bot not found")
    return {"ok": True, "bot": b}

@router.patch("/bots/{bot_id}")
def update_bot(bot_id: str, patch: BotUpdate):
    updated = dal.update(bot_id, patch.model_dump(exclude_none=True))
    if not updated: raise HTTPException(404, "bot not found")
    return {"ok": True, "bot": updated}

@router.delete("/bots/{bot_id}")
def delete_bot(bot_id: str):
    ok = dal.delete(bot_id)
    if not ok: raise HTTPException(404, "bot not found")
    return {"ok": True, "deleted": bot_id}

