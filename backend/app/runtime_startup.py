from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


async def run_postgres_migrations() -> None:
    from backend.app.db.session import engine
    from sqlalchemy import text

    migrations = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hint VARCHAR(255) DEFAULT ''",
        "ALTER TABLE camera_configs ADD COLUMN IF NOT EXISTS camera_type VARCHAR(64) NOT NULL DEFAULT 'unlabeled'",
        "ALTER TABLE camera_configs ADD COLUMN IF NOT EXISTS sample_image_id VARCHAR(255) NOT NULL DEFAULT ''",
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS open_hour INTEGER NOT NULL DEFAULT 10",
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS open_minute INTEGER NOT NULL DEFAULT 30",
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS close_hour INTEGER NOT NULL DEFAULT 21",
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS close_minute INTEGER NOT NULL DEFAULT 30",
    ]
    async with engine.begin() as conn:
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception as exc:
                logger.warning("Migration skipped: %s — %s", sql[:60], exc)


def run_sqlite_migrations(db_path: Path) -> None:
    if not db_path.exists():
        return
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_walkin_store_date ON onfly_walkin_sessions(store_id, business_date)",
        "CREATE INDEX IF NOT EXISTS idx_walkin_business_date ON onfly_walkin_sessions(business_date)",
        "CREATE INDEX IF NOT EXISTS idx_walkin_created_at ON onfly_walkin_sessions(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_image_state_store_date ON onfly_image_state(store_id, date_source)",
    ]
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        for sql in indexes:
            try:
                conn.execute(sql)
            except Exception as exc:
                logger.warning("SQLite index skipped: %s", exc)
        conn.commit()
        conn.close()
        logger.info("SQLite indexes verified.")
    except Exception as exc:
        logger.warning("SQLite migration failed: %s", exc)


def cleanup_zombie_runs(db_path: Path) -> None:
    from datetime import datetime, timezone

    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        now = datetime.now(timezone.utc).isoformat()
        result = conn.execute(
            """
            UPDATE onfly_pipeline_runs
            SET status='abandoned',
                error_message='Process died — runtime restarted while run was active',
                ended_at=?, updated_at=?
            WHERE status='running'
              AND (last_heartbeat_at IS NULL OR last_heartbeat_at < datetime('now', '-2 minutes'))
            """,
            (now, now),
        )
        count = result.rowcount
        conn.commit()
        conn.close()
        if count:
            logger.info("Startup cleanup: marked %d zombie run(s) as abandoned", count)
    except Exception as exc:
        logger.warning("Startup zombie cleanup failed: %s", exc)


async def prepare_runtime(db_path: Path) -> None:
    cleanup_zombie_runs(db_path)
    run_sqlite_migrations(db_path)
    await run_postgres_migrations()
