from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any
import json, os, time, uuid

# Optional Supabase client
_SB_OK = False
try:
    from supabase import create_client, Client  # pip install supabase
    _SB_OK = True
except Exception:
    _SB_OK = False

DB_JSON = Path(os.environ.get("QC_BOTS_DB", "data/bots.json"))
DB_JSON.parent.mkdir(parents=True, exist_ok=True)
if not DB_JSON.exists():
    DB_JSON.write_text("[]", encoding="utf-8")

TABLE = os.environ.get("QC_BOTS_TABLE", "bots")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

def _now() -> float: return time.time()

def _load_json() -> list:
    try: return json.loads(DB_JSON.read_text("utf-8"))
    except Exception: return []

def _save_json(bots: list) -> None:
    tmp = DB_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(bots, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(DB_JSON)

def _sb_client() -> 'Client | None':
    if not (_SB_OK and SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    except Exception:
        return None

def _sb_table_exists(sb: 'Client') -> bool:
    # Cheap probe; if it errors, we fall back to JSON.
    try:
        sb.table(TABLE).select("id").limit(1).execute()
        return True
    except Exception:
        return False

class BotsDAL:
    def __init__(self):
        self.sb = _sb_client()
        self.use_sb = bool(self.sb and _sb_table_exists(self.sb))

    # ---------- CRUD ----------
    def list(self) -> List[Dict[str, Any]]:
        if self.use_sb:
            data = self.sb.table(TABLE).select("*").order("created_at", desc=True).execute().data or []
            return data
        return _load_json()

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        doc = {
            "id": payload.get("id") or uuid.uuid4().hex,
            "name": payload["name"],
            "emoji": payload.get("emoji", "🤖"),
            "system_prompt": payload.get("system_prompt", "You are a helpful assistant."),
            "provider": payload.get("provider", "openai"),
            "model": payload.get("model", "gpt-5"),
            "temperature": float(payload.get("temperature", 0.2)),
            "max_tokens": int(payload.get("max_tokens", 800)),
            "tools_enabled": bool(payload.get("tools_enabled", False)),
            "created_at": payload.get("created_at", _now()),
            "updated_at": _now(),
        }
        if self.use_sb:
            res = self.sb.table(TABLE).insert(doc).execute()
            return (res.data or [doc])[0]
        bots = _load_json()
        bots.insert(0, doc)
        _save_json(bots)
        return doc

    def get(self, bot_id: str) -> Dict[str, Any] | None:
        if self.use_sb:
            res = self.sb.table(TABLE).select("*").eq("id", bot_id).limit(1).execute()
            rows = res.data or []
            return rows[0] if rows else None
        for b in _load_json():
            if b.get("id") == bot_id:
                return b
        return None

    def update(self, bot_id: str, patch: Dict[str, Any]) -> Dict[str, Any] | None:
        patch["updated_at"] = _now()
        if self.use_sb:
            res = self.sb.table(TABLE).update(patch).eq("id", bot_id).execute()
            rows = res.data or []
            return rows[0] if rows else None
        bots = _load_json()
        for i, b in enumerate(bots):
            if b.get("id") == bot_id:
                b.update({k: v for k, v in patch.items() if v is not None})
                bots[i] = b
                _save_json(bots)
                return b
        return None

    def delete(self, bot_id: str) -> bool:
        if self.use_sb:
            self.sb.table(TABLE).delete().eq("id", bot_id).execute()
            return True
        bots = _load_json()
        nb = [b for b in bots if b.get("id") != bot_id]
        if len(nb) == len(bots): return False
        _save_json(nb)
        return True

