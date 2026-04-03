from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.auth.dependencies import get_current_user
from backend.app.config import Settings, get_settings
from backend.app.db.pipeline_log import get_recent_runs
from backend.app.models.runs import RunListResponse, RunRecord

router = APIRouter()


@router.get("/runs", response_model=RunListResponse)
def list_runs(
    limit: int = 50,
    _email: str = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> RunListResponse:
    rows = get_recent_runs(settings.db_path_obj, limit=limit)
    runs = [
        RunRecord(
            run_id=r["run_id"],
            job_key=r["job_key"],
            job_name=r["job_name"],
            store_id=r["store_id"],
            status=r["status"],
            remarks=r.get("remarks", ""),
            triggered_by=r.get("triggered_by", "scheduler"),
            started_at=r.get("started_at", ""),
            completed_at=r.get("completed_at", ""),
            created_at=r.get("created_at", ""),
        )
        for r in rows
    ]
    return RunListResponse(runs=runs, total=len(runs))
