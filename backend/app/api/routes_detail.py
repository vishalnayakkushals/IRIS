from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from backend.app.db.platform_data import get_store_metrics, get_walkin_sessions, list_store_registry_stores

router = APIRouter()


@router.get("/stores")
async def list_store_options(
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    rows = await list_store_registry_stores()
    return {"stores": rows, "total": len(rows)}


@router.get("/walkins")
async def get_walkin_sessions_route(
    store_id: str | None = None,
    limit: int = 200,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    rows = await get_walkin_sessions(store_id, limit)
    return {"sessions": rows, "total": len(rows), "store_id": store_id or "all"}


@router.get("/{store_id}/walkins")
async def get_store_walkin_sessions_route(
    store_id: str,
    limit: int = 200,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    rows = await get_walkin_sessions(store_id, limit)
    return {"sessions": rows, "total": len(rows), "store_id": store_id}


@router.get("/{store_id}/metrics")
async def get_store_metrics_route(
    store_id: str,
    _email: str = Depends(get_current_user),
) -> dict[str, Any]:
    return await get_store_metrics(store_id)
