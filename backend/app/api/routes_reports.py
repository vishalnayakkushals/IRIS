"""Reports routes — walkin sessions, store day summaries, image scan results,
model version history, and pipeline run quality stats."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, func

from backend.app.auth.dependencies import get_current_user
from backend.app.db.canonical_metadata import (
    model_versions,
    onfly_walkin_sessions,
    report_store_day_summary,
    report_image_scan_results,
    pipeline_run_log,
    stores,
)
from backend.app.db.session import AsyncSessionLocal

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/walkins")
async def get_walkins(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 200,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(onfly_walkin_sessions)
            .order_by(onfly_walkin_sessions.c.created_at.desc())
            .limit(limit)
        )
        if store_id:
            stmt = stmt.where(onfly_walkin_sessions.c.store_id == store_id)
        if business_date:
            stmt = stmt.where(onfly_walkin_sessions.c.business_date == business_date)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.get("/summary")
async def get_store_day_summary(
    store_id: str | None = None,
    limit: int = 90,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(report_store_day_summary)
            .order_by(
                report_store_day_summary.c.business_date.desc(),
                report_store_day_summary.c.store_id,
            )
            .limit(limit)
        )
        if store_id:
            stmt = stmt.where(report_store_day_summary.c.store_id == store_id)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.get("/image-scans")
async def get_image_scans(
    store_id: str | None = None,
    business_date: str | None = None,
    limit: int = 200,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(report_image_scan_results)
            .order_by(report_image_scan_results.c.created_at.desc())
            .limit(limit)
        )
        if store_id:
            stmt = stmt.where(report_image_scan_results.c.store_id == store_id)
        if business_date:
            stmt = stmt.where(report_image_scan_results.c.business_date == business_date)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]


@router.get("/model-accuracy")
async def get_model_accuracy(_: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(model_versions).order_by(model_versions.c.created_at.desc()).limit(50)
        )
        return [dict(r) for r in result.mappings().all()]


@router.get("/stores-with-data")
async def get_stores_with_data(_: str = Depends(get_current_user)) -> list[dict[str, Any]]:
    """List stores that have at least one day of report data."""
    async with AsyncSessionLocal() as session:
        subq = (
            select(report_store_day_summary.c.store_id)
            .group_by(report_store_day_summary.c.store_id)
            .subquery()
        )
        result = await session.execute(
            select(stores.c.store_id, stores.c.store_name)
            .where(stores.c.store_id.in_(select(subq)))
            .order_by(stores.c.store_id)
        )
        return [dict(r) for r in result.mappings().all()]


@router.get("/pipeline-quality")
async def get_pipeline_quality(
    store_id: str | None = None,
    limit: int = 50,
    _: str = Depends(get_current_user),
) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(pipeline_run_log)
            .order_by(pipeline_run_log.c.created_at.desc())
            .limit(limit)
        )
        if store_id:
            stmt = stmt.where(pipeline_run_log.c.store_id == store_id)
        result = await session.execute(stmt)
        return [dict(r) for r in result.mappings().all()]
