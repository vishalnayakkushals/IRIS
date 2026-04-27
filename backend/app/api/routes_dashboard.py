from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from backend.app.config import Settings, get_settings
from backend.app.db.platform_data import get_overview_metrics, get_pipeline_runs, get_traffic_series

router = APIRouter()


@router.get("/traffic")
async def get_traffic_data(
    store_id: str | None = None,
    days: int = 30,
    _email: str = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    series = get_traffic_series(settings.db_path_obj, store_id, days)
    # Sort ascending for chart display
    series.sort(key=lambda x: x.get("date", ""))
    return {"series": series, "store_id": store_id or "all", "days": days}


@router.get("/pipeline-runs")
async def get_pipeline_runs_route(
    limit: int = 50,
    _email: str = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    runs = get_pipeline_runs(settings.db_path_obj, limit)
    return {"runs": runs, "total": len(runs)}


@router.get("/overview")
async def get_dashboard_overview(
    _email: str = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """
    Provides top-level walk-in and conversion metrics for the React frontend.
    Prefers Postgres-backed on-fly session data, but falls back to SQLite so
    the current runtime continues to work until backfill is complete.
    """
    return await get_overview_metrics(settings.db_path_obj)
