from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()

class SearchHit(BaseModel):
    title: str
    href: str
    body: str | None = None

@router.get("/search/ddg")
def ddg_search(q: str, k: int = 5):
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except Exception:
        return {"ok": False, "error": "duckduckgo-search not installed"}
    hits: List[SearchHit] = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(q, max_results=max(1, min(k, 20))):
                hits.append(SearchHit(title=r.get("title", ""), href=r.get("href", ""), body=r.get("body")))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "results": [h.model_dump() for h in hits]}