from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from backend.app.db.platform_data import get_overview_metrics, get_pipeline_runs, get_traffic_series

router = APIRouter()


@router.get("/traffic")
async def get_traffic_data(
    store_id: str | None = None,
    days: int = 30,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    series = await get_traffic_series(store_id, days)
    series.sort(key=lambda x: x.get("date", ""))
    return {"series": series, "store_id": store_id or "all", "days": days}


@router.get("/pipeline-runs")
async def get_pipeline_runs_route(
    limit: int = 50,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    runs = await get_pipeline_runs(limit)
    return {"runs": runs, "total": len(runs)}


@router.get("/overview")
async def get_dashboard_overview(
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    return await get_overview_metrics()
