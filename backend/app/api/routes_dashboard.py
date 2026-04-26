from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from backend.app.config import Settings, get_settings
from backend.app.db.platform_data import get_overview_metrics

router = APIRouter()


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
