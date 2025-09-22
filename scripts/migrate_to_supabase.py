#!/usr/bin/env python3
"""
Migrate local JSON stores (bots, chats, kb, skills) into Supabase.

Usage:
  python scripts/migrate_to_supabase.py [--dry-run]

Requires in .env:
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
Optional environment overrides:
  QC_BOTS_TABLE, QC_CHATS_TABLE, QC_KB_TABLE, QC_SKILLS_TABLE

Notes:
- This script does not create tables. If tables are missing, it will print the SQL
  you can paste into the Supabase SQL editor. You can also GET /supabase/status in
  the running app to copy a consolidated SQL block.
"""
from __future__ import annotations
import os, json, sys, time
from pathlib import Path

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    def load_dotenv(*_, **__):
        return False

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DRY = "--dry-run" in sys.argv or os.getenv("MIGRATE_DRY_RUN", "").lower() in {"1", "true", "yes"}

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required in .env", file=sys.stderr)
    sys.exit(2)

try:
    from supabase import create_client  # type: ignore
except Exception as e:
    print(f"ERROR: supabase python client not installed ({e}). pip install supabase", file=sys.stderr)
    sys.exit(2)

# Table names (can be overridden in env)
T_BOTS = os.getenv("QC_BOTS_TABLE", "bots")
T_CHATS = os.getenv("QC_CHATS_TABLE", "chats")
T_KB = os.getenv("QC_KB_TABLE", "kb")
T_SKILLS = os.getenv("QC_SKILLS_TABLE", "skills")

# Data file paths
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
F_BOTS = Path(os.getenv("QC_BOTS_DB", str(DATA / "bots.json")))
F_CHATS = Path(os.getenv("QC_CHATS_DB", str(DATA / "chats.json")))
F_KB = Path(os.getenv("QC_KB_DB", str(DATA / "kb.json")))
F_SKILLS = Path(os.getenv("QC_SKILLS_DB", str(DATA / "skills.json")))

# SQL schema for convenience if tables are missing
SQL_SCHEMA = """
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

create table if not exists chats (
  id text primary key,
  title text,
  ts double precision,
  transcript jsonb
);

create table if not exists kb (
  id text primary key,
  text text,
  source text,
  ts double precision
);

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
""".strip()

def read_json(p: Path) -> list:
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return []


def chunked(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i+n]


def ensure_tables_and_client():
    sb = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    missing = []
    for t in (T_BOTS, T_CHATS, T_KB, T_SKILLS):
        try:
            sb.table(t).select("id").limit(1).execute()
        except Exception:
            missing.append(t)
    return sb, missing


def migrate_table(sb, table_name: str, rows: list, pk: str = "id") -> tuple[int,int]:
    if not rows:
        return (0, 0)
    if DRY:
        return (0, len(rows))
    inserted = 0
    for batch in chunked(rows, 500):
        # upsert keeps existing rows and updates by PK
        try:
            sb.table(table_name).upsert(batch, on_conflict=pk).execute()
            inserted += len(batch)
        except Exception as e:
            print(f"WARN: upsert to {table_name} failed for batch of {len(batch)} rows: {e}", file=sys.stderr)
    return (inserted, len(rows))


def main():
    sb, missing = ensure_tables_and_client()
    if missing:
        print("One or more tables are missing in Supabase:", ", ".join(missing))
        print("\nCreate them with the following SQL in Supabase SQL editor:\n")
        print(SQL_SCHEMA)
        print("\nThen re-run this script.")
        sys.exit(1)

    bots = read_json(F_BOTS)
    chats = read_json(F_CHATS)
    kb = read_json(F_KB)
    skills = read_json(F_SKILLS)

    print(f"Migrating to Supabase at {SUPABASE_URL}")
    if DRY:
        print("[dry-run] No data will be written.")

    t0 = time.time()
    b_ins, b_total = migrate_table(sb, T_BOTS, bots)
    c_ins, c_total = migrate_table(sb, T_CHATS, chats)
    k_ins, k_total = migrate_table(sb, T_KB, kb)
    s_ins, s_total = migrate_table(sb, T_SKILLS, skills)

    dt = time.time() - t0
    print(f"Done in {dt:.2f}s")
    print(f"bots  : {b_ins}/{b_total}")
    print(f"chats : {c_ins}/{c_total}")
    print(f"kb    : {k_ins}/{k_total}")
    print(f"skills: {s_ins}/{s_total}")

if __name__ == "__main__":
    main()
