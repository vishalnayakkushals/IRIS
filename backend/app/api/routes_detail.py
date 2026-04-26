from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from backend.app.config import Settings, get_settings
from backend.app.db.platform_data import get_store_metrics, list_store_registry_stores

router = APIRouter()


@router.get("/stores")
async def list_store_options(
    _email: str = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    rows = list_store_registry_stores(settings.db_path_obj)
    return {"stores": rows, "total": len(rows)}


@router.get("/{store_id}/metrics")
async def get_store_metrics_route(
    store_id: str,
    _email: str = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """
    Provides isolated metrics specific to a single store for the React Store Detail page.
    Prefers Postgres-backed on-fly session data and falls back to SQLite until migration completes.
    """
    return await get_store_metrics(settings.db_path_obj, store_id)
