from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
import os

router = APIRouter()

_SQL = {
    "bots": """
create table if not exists bots (
  id text primary key,
  name text not null,
  emoji text,
  system_prompt text,
  provider text,
  model text,
  temperature double precision,
  max_tokens integer,
  tools_enabled boolean default false,
  created_at double precision,
  updated_at double precision
);
""",
    "chats": """
create table if not exists chats (
  id text primary key,
  title text,
  ts double precision,
  transcript jsonb
);
""",
    "kb": """
create table if not exists kb (
  id text primary key,
  text text,
  source text,
  ts double precision
);
""",
    "skills": """
create table if not exists skills (
  id text primary key,
  name text not null,
  cmd text not null,
  is_root boolean default false,
  tags jsonb,
  created_at double precision,
  updated_at double precision,
  usage integer
);
""",
}

try:
    from supabase import create_client
    _HAS_SB = True
except Exception:
    _HAS_SB = False

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TABLES = {
    "bots": os.getenv("QC_BOTS_TABLE", "bots"),
    "chats": os.getenv("QC_CHATS_TABLE", "chats"),
    "kb": os.getenv("QC_KB_TABLE", "kb"),
    "skills": os.getenv("QC_SKILLS_TABLE", "skills"),
}


def _client():
    if not (_HAS_SB and SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    except Exception:
        return None


@router.get("/supabase/status")
def supabase_status():
    configured = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)
    client_ok = False
    tables = {k: "unknown" for k in TABLES}
    sb = _client()
    if sb:
        client_ok = True
        for key, t in TABLES.items():
            try:
                sb.table(t).select("id").limit(1).execute()
                tables[key] = "ok"
            except Exception:
                tables[key] = "missing"
    sql = "\n".join(_SQL.values())
    return {
        "configured": configured,
        "client": client_ok,
        "tables": tables,
        "sql": sql,
        "url": SUPABASE_URL,
    }

