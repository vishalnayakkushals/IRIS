from __future__ import annotations

import os
from pathlib import Path
import sys

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, MetaData, Table, Text, create_engine, text


def _load_runtime() -> tuple[Path, str]:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from iris.runtime_bootstrap import load_env_file
    from backend.app.config import get_settings

    load_env_file()
    settings = get_settings()
    sync_url = os.environ.get("POSTGRES_SYNC_URL", "").strip() or settings.postgres_url
    if sync_url.startswith("postgresql+asyncpg://"):
        sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if not sync_url:
        raise SystemExit("POSTGRES_SYNC_URL or POSTGRES_URL is required.")
    return Path(repo_root), sync_url


def _ensure_track_sessions_table(engine) -> None:
    meta = MetaData()
    table = Table(
        "onfly_track_sessions",
        meta,
        Column("session_id", Text, primary_key=True),
        Column("run_id", Text, nullable=False),
        Column("store_id", Text, nullable=False),
        Column("business_date", Text, nullable=False, server_default=""),
        Column("track_id_local", Integer, nullable=False),
        Column("track_global_id", Text, nullable=False),
        Column("status", Text, nullable=False, server_default="entry_candidate"),
        Column("entry_frame_idx", Integer, nullable=True),
        Column("exit_frame_idx", Integer, nullable=True),
        Column("entry_image_id", Text, nullable=True),
        Column("exit_image_id", Text, nullable=True),
        Column("dwell_frames", Integer, nullable=False, server_default="0"),
        Column("dwell_seconds", Float, nullable=False, server_default="0"),
        Column("first_seen_at", DateTime(timezone=True), nullable=True),
        Column("last_seen_at", DateTime(timezone=True), nullable=True),
        Column("staff_flag", Boolean, nullable=False, server_default="false"),
        Column("gender", Text, nullable=False, server_default=""),
        Column("confidence", Float, nullable=False, server_default="0"),
        Column("avg_bbox_x1", Float, nullable=True),
        Column("avg_bbox_y1", Float, nullable=True),
        Column("avg_bbox_x2", Float, nullable=True),
        Column("avg_bbox_y2", Float, nullable=True),
        Column("notes", Text, nullable=False, server_default=""),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("NOW()")),
    )
    Index("idx_track_sessions_run_store", table.c.run_id, table.c.store_id)
    Index("idx_track_sessions_store_date", table.c.store_id, table.c.business_date)
    Index("idx_track_sessions_status", table.c.store_id, table.c.status, table.c.business_date)
    meta.create_all(engine, tables=[table], checkfirst=True)


def main() -> None:
    repo_root, sync_url = _load_runtime()
    from backend.app.db.canonical_metadata import metadata

    engine = create_engine(sync_url, future=True)
    try:
        metadata.create_all(engine, checkfirst=True)
        _ensure_track_sessions_table(engine)
    finally:
        engine.dispose()
    print(f"[iris-db] schema ready for {repo_root}")


if __name__ == "__main__":
    main()
