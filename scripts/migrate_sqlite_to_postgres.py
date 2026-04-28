# -*- coding: utf-8 -*-
"""
One-time migration: copies all IRIS SQLite tables into Postgres.

Usage (run once after `alembic upgrade head`):
    python scripts/migrate_sqlite_to_postgres.py

Set POSTGRES_URL in your .env / environment before running.
Existing Postgres rows with matching PKs are skipped (INSERT ... ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

import asyncio
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "src"))

from iris.runtime_bootstrap import load_env_file, resolve_runtime_paths

load_env_file()
resolve_runtime_paths()

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.config import get_settings

settings = get_settings()

_DATA_ROOT = settings.data_root_obj
_SQLITE_PATH = _DATA_ROOT / "store_registry.db"

if not _SQLITE_PATH.exists():
    sys.exit(f"SQLite not found at {_SQLITE_PATH}")

# Tables to migrate (order matters for FK constraints)
# conflict_cols: columns used in ON CONFLICT clause (usually PKs)
# bool_cols: columns stored as 0/1 int in SQLite, need bool in Postgres
TABLES = [
    ("stores",              ["store_id"],               set()),
    ("store_master",        ["store_id"],               set()),
    ("store_sync_state",    ["store_id"],               set()),
    ("users",               ["email"],                  {"is_active"}),
    ("pipeline_run_log",    ["run_id"],                 set()),
    ("onfly_image_state",   ["store_id", "image_id"],   {"yolo_relevant"}),
    ("onfly_pipeline_runs", ["run_id"],                 set()),
    ("onfly_walkin_sessions", None,                     set()),
    ("onfly_run_metrics",   ["run_id"],                 set()),
]

# Columns that store ISO datetime strings in SQLite but need datetime objects in PG
_DATETIME_COLS = {
    "created_at", "updated_at", "started_at", "completed_at", "ended_at",
    "last_sync_at", "last_seen_at", "first_seen_at", "discovered_at",
    "last_download_at", "last_heartbeat_at", "expires_at", "reviewed_at",
}

# Store IDs that were actually migrated to Postgres (set after stores migration)
_KNOWN_STORES: set[str] = set()

# Fallback store for users that have empty store_id
_FALLBACK_STORE_ID = ""


def _parse_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt[:19]).replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def _clean_row(row: dict, bool_cols: set[str], fallback_store: str) -> dict:
    cleaned: dict = {}
    for k, v in row.items():
        if v is None and k.endswith("_json"):
            cleaned[k] = {}
        elif k in _DATETIME_COLS:
            cleaned[k] = _parse_dt(v)
        elif k in bool_cols:
            cleaned[k] = bool(v) if v is not None else False
        elif k == "store_id" and (v is None or str(v).strip() == ""):
            # Rows with empty store_id can't satisfy FK — use fallback if available
            cleaned[k] = fallback_store if fallback_store else v
        else:
            cleaned[k] = v
    return cleaned


def _sqlite_rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


async def _pg_table_exists(engine, table: str) -> bool:
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{table}"})
        return result.scalar() is not None


async def _migrate_table(
    engine,
    table: str,
    rows: list[dict],
    conflict_cols: list[str] | None,
    bool_cols: set[str],
) -> int:
    if not rows:
        return 0

    # Determine fallback store_id for tables with store_id FK
    fallback = next(iter(_KNOWN_STORES), "") if _KNOWN_STORES else ""

    cols = list(rows[0].keys())
    conflict_clause = (
        f"ON CONFLICT ({', '.join(conflict_cols)}) DO NOTHING"
        if conflict_cols else "ON CONFLICT DO NOTHING"
    )
    col_list = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    sql = text(f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) {conflict_clause}')  # noqa: S608

    inserted = 0
    async with engine.begin() as conn:
        for idx, row in enumerate(rows):
            cleaned = _clean_row(row, bool_cols, fallback)
            sp = f"sp_{idx}"
            try:
                await conn.execute(text(f"SAVEPOINT {sp}"))
                await conn.execute(sql, cleaned)
                await conn.execute(text(f"RELEASE SAVEPOINT {sp}"))
                inserted += 1
            except Exception as exc:
                await conn.execute(text(f"ROLLBACK TO SAVEPOINT {sp}"))
                short = str(exc)[:120]
                print(f"  SKIP {table}[{idx}]: {short}")
    return inserted


async def main() -> None:
    global _KNOWN_STORES

    print(f"Source SQLite : {_SQLITE_PATH}")
    print(f"Target Postgres: {settings.postgres_url}\n")

    sqlite_conn = sqlite3.connect(str(_SQLITE_PATH), timeout=30, check_same_thread=False)
    engine = create_async_engine(settings.postgres_url, echo=False)

    total_migrated = 0
    for table, conflict_cols, bool_cols in TABLES:
        exists = await _pg_table_exists(engine, table)
        if not exists:
            print(f"  MISS {table}: table missing in PG -- run alembic upgrade head")
            continue

        rows = _sqlite_rows(sqlite_conn, table)
        if not rows:
            print(f"  skip {table}: empty in SQLite")
            continue

        inserted = await _migrate_table(engine, table, rows, conflict_cols, bool_cols)
        print(f"  OK   {table}: {inserted}/{len(rows)} rows migrated")
        total_migrated += inserted

        # After migrating stores, record which store_ids are now in PG
        if table == "stores":
            _KNOWN_STORES = {r["store_id"] for r in rows if r.get("store_id")}

    sqlite_conn.close()
    await engine.dispose()
    print(f"\nDone. Total rows migrated: {total_migrated}")


if __name__ == "__main__":
    asyncio.run(main())
