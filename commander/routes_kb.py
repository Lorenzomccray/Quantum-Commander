from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import json, os, time, math

router = APIRouter()
DB = Path(os.environ.get("QC_KB_DB","data/kb.json"))
if not DB.exists(): DB.write_text("[]","utf-8")

class KBItem(BaseModel):
    id: str
    text: str
    source: str
    ts: float

def _load():
    try: return json.loads(DB.read_text("utf-8"))
    except Exception: return []

def _save(rows):
    tmp = DB.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(DB)

@router.post("/kb/index")
def kb_index(text: str, source: str = "manual"):
    rows = _load()
    item = {"id": f"kb_{int(time.time()*1000)}", "text": text, "source": source, "ts": time.time()}
    rows.insert(0, item)
    _save(rows)
    return {"ok": True, "item": item}

@router.get("/kb/search")
def kb_search(q: str, k: int = 5):
    # toy scoring: length-normalized token overlap
    rows = _load()
    qs = set(q.lower().split())
    def score(t):
        s = set(t.lower().split())
        return len(qs & s) / math.sqrt(len(s)+1e-6)
    ranked = sorted(rows, key=lambda r: score(r["text"]), reverse=True)[:max(1,min(k,20))]
    return {"ok": True, "hits": ranked}

