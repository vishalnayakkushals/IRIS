from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _run_sync(coro):
    return asyncio.run(coro)


async def _pg_insert_run_log(
    *,
    run_id: str,
    job_key: str,
    job_name: str,
    store_id: str,
    triggered_by: str,
    status: str,
) -> None:
    from backend.app.db.canonical_metadata import pipeline_run_log
    from backend.app.db.session import AsyncSessionLocal

    now = _now()
    async with AsyncSessionLocal() as session:
        stmt = pg_insert(pipeline_run_log).values(
            run_id=run_id,
            job_key=job_key,
            job_name=job_name,
            store_id=store_id,
            status=status,
            triggered_by=triggered_by,
            started_at=now,
            created_at=now,
            result_json={},
            remarks="",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[pipeline_run_log.c.run_id],
            set_={
                "job_key": stmt.excluded.job_key,
                "job_name": stmt.excluded.job_name,
                "store_id": stmt.excluded.store_id,
                "status": stmt.excluded.status,
                "triggered_by": stmt.excluded.triggered_by,
                "started_at": stmt.excluded.started_at,
                "created_at": stmt.excluded.created_at,
            },
        )
        await session.execute(stmt)
        await session.commit()


async def _pg_update_run_log_status(
    *,
    run_id: str,
    status: str,
    remarks: str,
    result_json: str,
) -> None:
    from backend.app.db.canonical_metadata import pipeline_run_log
    from backend.app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        stmt = (
            pipeline_run_log.update()
            .where(pipeline_run_log.c.run_id == run_id)
            .values(
                status=status,
                remarks=remarks,
                result_json=result_json,
                completed_at=_now(),
            )
        )
        await session.execute(stmt)
        await session.commit()


async def _pg_get_latest_per_job() -> list[dict[str, Any]]:
    from backend.app.db.canonical_metadata import pipeline_run_log
    from backend.app.db.session import AsyncSessionLocal

    subquery = (
        select(
            pipeline_run_log.c.job_key,
            func.max(pipeline_run_log.c.created_at).label("max_at"),
        )
        .group_by(pipeline_run_log.c.job_key)
        .subquery()
    )
    stmt = (
        select(pipeline_run_log)
        .join(
            subquery,
            (pipeline_run_log.c.job_key == subquery.c.job_key)
            & (pipeline_run_log.c.created_at == subquery.c.max_at),
        )
        .order_by(pipeline_run_log.c.job_key)
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        return [dict(row) for row in result.mappings().all()]


async def _pg_get_recent_runs(limit: int = 50) -> list[dict[str, Any]]:
    from backend.app.db.canonical_metadata import pipeline_run_log
    from backend.app.db.session import AsyncSessionLocal

    stmt = select(pipeline_run_log).order_by(pipeline_run_log.c.created_at.desc()).limit(int(limit))
    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        return [dict(row) for row in result.mappings().all()]


def insert_run_log(
    db_path: Path,
    run_id: str,
    job_key: str,
    job_name: str,
    store_id: str,
    triggered_by: str = "scheduler",
    status: str = "running",
) -> None:
    try:
        _run_sync(
            _pg_insert_run_log(
                run_id=run_id,
                job_key=job_key,
                job_name=job_name,
                store_id=store_id,
                triggered_by=triggered_by,
                status=status,
            )
        )
    except Exception:
        pass

    conn = _connect(db_path)
    try:
        now = _now()
        conn.execute(
            """
            INSERT OR REPLACE INTO pipeline_run_log
                (run_id, job_key, job_name, store_id, status, triggered_by, started_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, job_key, job_name, store_id, status, triggered_by, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def update_run_log_status(
    db_path: Path,
    run_id: str,
    status: str,
    remarks: str = "",
    result_json: str = "{}",
) -> None:
    try:
        _run_sync(
            _pg_update_run_log_status(
                run_id=run_id,
                status=status,
                remarks=remarks,
                result_json=result_json,
            )
        )
    except Exception:
        pass

    conn = _connect(db_path)
    try:
        conn.execute(
            """
            UPDATE pipeline_run_log
               SET status=?, remarks=?, result_json=?, completed_at=?
             WHERE run_id=?
            """,
            (status, remarks, result_json, _now(), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_per_job(db_path: Path) -> list[dict[str, Any]]:
    """Return one row per job_key (the most recent run for each job)."""
    try:
        rows = _run_sync(_pg_get_latest_per_job())
        if rows:
            return rows
    except Exception:
        pass

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT r.*
              FROM pipeline_run_log r
             INNER JOIN (
                 SELECT job_key, MAX(created_at) AS max_at
                   FROM pipeline_run_log
                  GROUP BY job_key
             ) latest ON r.job_key = latest.job_key AND r.created_at = latest.max_at
             ORDER BY r.job_key
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_recent_runs(db_path: Path, limit: int = 50) -> list[dict[str, Any]]:
    try:
        rows = _run_sync(_pg_get_recent_runs(limit=limit))
        if rows:
            return rows
    except Exception:
        pass

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM pipeline_run_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
