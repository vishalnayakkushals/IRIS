# -*- coding: utf-8 -*-
"""
One-time data repair script:
  1. Normalize all existing onfly_walkin_sessions in SQLite:
       - role         → title-case canonical ('Customer', 'Staff', …)
       - business_date → YYYY-MM-DD (from DD-MM-YYYY)
       - date          → YYYY-MM-DD
       - included_in_analytics → 'Yes' / 'No'
  2. Sync all normalized SQLite walkin sessions → PostgreSQL
     (DELETE per run_id + bulk INSERT, avoids partition-key upsert constraint).

Usage:
    python scripts/fix_normalize_and_sync_walkins.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "src"))

from iris.runtime_bootstrap import load_env_file, resolve_runtime_paths

load_env_file()
resolve_runtime_paths()

from sqlalchemy import text as sa_text

from backend.app.config import get_settings
from backend.app.db.session import engine_sync

settings = get_settings()
_SQLITE_PATH = settings.data_root_obj / "store_registry.db"

# ── normalization maps ────────────────────────────────────────────────────────

_ROLE_MAP: dict[str, str] = {
    "customer": "Customer",
    "staff": "Staff",
    "uncertain": "Uncertain",
    "unknown": "Uncertain",
    "passerby": "Passerby",
    "banner": "Banner",
    "poster": "Banner",
    "poster non human": "Banner",
    "poster_non_human": "Banner",
    "poster or non-human": "Banner",
    "inside active": "Customer",
}


def _norm_role(role: str | None) -> str:
    r = str(role or "").strip()
    return _ROLE_MAP.get(r.lower(), r.title() if r else "Uncertain")


def _norm_date(d: str | None) -> str:
    s = str(d or "").strip()
    if len(s) == 10 and s[2] == "-" and s[5] == "-":
        return f"{s[6:10]}-{s[3:5]}-{s[0:2]}"
    return s


def _norm_yn(val: str | None) -> str:
    return "Yes" if str(val or "").strip().lower() == "yes" else "No"


# ── PG columns (must match _PG_WALKIN_COLS in onfly_pipeline.py) ─────────────

_PG_WALKIN_COLS = [
    "store_id", "run_id", "image_id", "source_image_name", "source_folder_name",
    "camera_id", "business_date", "date", "event_type", "event_time", "walkin_id",
    "group_id", "role", "entry_time", "exit_time", "time_spent_mins", "session_status",
    "entry_type", "first_seen_time", "last_seen_time", "matched_session_id", "match_score",
    "match_reason", "direction_confidence", "match_fingerprint", "debug_parsed_time",
    "debug_gpt_event_type", "gender", "age_band", "attire_visual_marker", "primary_clothing",
    "jewellery_load", "bag_type", "clothing_style_archetype", "engagement_type",
    "engagement_depth", "purchase_signal_bag", "included_in_analytics",
]


def normalize_sqlite(conn: sqlite3.Connection, dry_run: bool) -> int:
    """Normalize all rows in onfly_walkin_sessions in SQLite. Returns rows updated."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT id, role, business_date, date, included_in_analytics FROM onfly_walkin_sessions").fetchall()
    updates = 0
    for row in rows:
        new_role = _norm_role(row["role"])
        new_bd   = _norm_date(row["business_date"])
        new_date = _norm_date(row["date"])
        new_yn   = _norm_yn(row["included_in_analytics"])
        changed = (
            new_role != (row["role"] or "")
            or new_bd   != (row["business_date"] or "")
            or new_date != (row["date"] or "")
            or new_yn   != (row["included_in_analytics"] or "")
        )
        if changed:
            updates += 1
            if not dry_run:
                conn.execute(
                    "UPDATE onfly_walkin_sessions SET role=?, business_date=?, date=?, included_in_analytics=? WHERE id=?",
                    (new_role, new_bd, new_date, new_yn, row["id"]),
                )
    if not dry_run:
        conn.commit()
    return updates


def sync_all_to_pg(conn: sqlite3.Connection, dry_run: bool) -> tuple[int, int]:
    """Sync all SQLite walkin sessions to PostgreSQL. Returns (runs synced, rows inserted)."""
    cols_sql = ", ".join(_PG_WALKIN_COLS)
    run_ids = [r[0] for r in conn.execute(
        "SELECT DISTINCT run_id FROM onfly_walkin_sessions ORDER BY run_id"
    ).fetchall()]

    placeholders = ", ".join([f":{c}" for c in _PG_WALKIN_COLS])
    insert_sql = sa_text(f"INSERT INTO onfly_walkin_sessions ({cols_sql}) VALUES ({placeholders})")

    total_rows = 0
    for run_id in run_ids:
        rows = conn.execute(
            f"SELECT {cols_sql} FROM onfly_walkin_sessions WHERE run_id=?",
            (run_id,),
        ).fetchall()
        if not rows:
            continue
        batch = [dict(zip(_PG_WALKIN_COLS, r)) for r in rows]
        if dry_run:
            print(f"  [dry-run] run_id={run_id}: would DELETE+INSERT {len(rows)} rows")
        else:
            with engine_sync.begin() as pg:
                pg.execute(
                    sa_text("DELETE FROM onfly_walkin_sessions WHERE run_id=:rid"),
                    {"rid": run_id},
                )
                pg.execute(insert_sql, batch)
        total_rows += len(rows)

    return len(run_ids), total_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize SQLite walkins + sync to PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    if not _SQLITE_PATH.exists():
        sys.exit(f"SQLite not found: {_SQLITE_PATH}")

    print(f"SQLite : {_SQLITE_PATH}")
    print(f"PG     : {settings.postgres_url}\n")

    conn = sqlite3.connect(str(_SQLITE_PATH), timeout=30)
    try:
        total = conn.execute("SELECT COUNT(*) FROM onfly_walkin_sessions").fetchone()[0]
        print(f"Total SQLite walkin sessions: {total}")

        print("\nStep 1: Normalize SQLite data")
        updated = normalize_sqlite(conn, args.dry_run)
        action = "would update" if args.dry_run else "updated"
        print(f"  Rows {action}: {updated} / {total}")

        print("\nStep 2: Sync to PostgreSQL")
        runs, rows = sync_all_to_pg(conn, args.dry_run)
        action = "would sync" if args.dry_run else "synced"
        print(f"  {action}: {runs} run_ids, {rows} rows")

        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
