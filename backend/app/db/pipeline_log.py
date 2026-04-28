from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def insert_run_log(
    *,
    run_id: str,
    job_key: str,
    job_name: str,
    store_id: str,
    triggered_by: str = "scheduler",
    status: str = "running",
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


async def update_run_log_status(
    *,
    run_id: str,
    status: str,
    remarks: str = "",
    result_json: str | dict = "{}",
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


async def get_latest_per_job() -> list[dict[str, Any]]:
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
        return [dict(r) for r in result.mappings().all()]


async def get_recent_runs(limit: int = 50) -> list[dict[str, Any]]:
    from backend.app.db.canonical_metadata import pipeline_run_log
    from backend.app.db.session import AsyncSessionLocal

    stmt = select(pipeline_run_log).order_by(pipeline_run_log.c.created_at.desc()).limit(int(limit))
    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


async def get_run_by_id(run_id: str) -> dict[str, Any] | None:
    from backend.app.db.canonical_metadata import pipeline_run_log
    from backend.app.db.session import AsyncSessionLocal

    stmt = select(pipeline_run_log).where(pipeline_run_log.c.run_id == run_id).limit(1)
    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        row = result.mappings().first()
        return dict(row) if row else None


async def upsert_track_sessions(sessions: list[dict[str, Any]]) -> None:
    """Bulk-upsert BoT-SORT track sessions into onfly_track_sessions."""
    from backend.app.db.session import AsyncSessionLocal
    from sqlalchemy import Table, MetaData

    if not sessions:
        return

    async with AsyncSessionLocal() as db_session:
        # Reflect the table lazily — migration 002 must have been applied
        meta = MetaData()
        conn = await db_session.connection()
        await conn.run_sync(meta.reflect, only=["onfly_track_sessions"])
        tbl = meta.tables.get("onfly_track_sessions")
        if tbl is None:
            return  # migration not yet applied; skip silently

        for row in sessions:
            stmt = pg_insert(tbl).values(**row)
            stmt = stmt.on_conflict_do_update(
                index_elements=[tbl.c.session_id],
                set_={k: stmt.excluded[k] for k in row if k != "session_id"},
            )
            await db_session.execute(stmt)
        await db_session.commit()
