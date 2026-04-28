from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.auth.dependencies import get_current_user
from backend.app.db.pipeline_log import get_recent_runs
from backend.app.models.runs import RunListResponse, RunRecord

router = APIRouter()


def _to_run_record(r: dict) -> RunRecord:
    return RunRecord(
        run_id=str(r.get("run_id") or ""),
        job_key=str(r.get("job_key") or ""),
        job_name=str(r.get("job_name") or ""),
        store_id=str(r.get("store_id") or ""),
        status=str(r.get("status") or ""),
        remarks=str(r.get("remarks") or ""),
        triggered_by=str(r.get("triggered_by") or "scheduler"),
        started_at=str(r.get("started_at") or ""),
        completed_at=str(r.get("completed_at") or ""),
        created_at=str(r.get("created_at") or ""),
    )


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    limit: int = 50,
    _email: str = Depends(get_current_user),
) -> RunListResponse:
    rows = await get_recent_runs(limit=limit)
    return RunListResponse(runs=[_to_run_record(r) for r in rows], total=len(rows))


@router.get("/runs/{run_id}", response_model=RunRecord)
async def get_run(
    run_id: str,
    _email: str = Depends(get_current_user),
) -> RunRecord:
    rows = await get_recent_runs(limit=200)
    for r in rows:
        if r.get("run_id") == run_id:
            return _to_run_record(r)
    raise HTTPException(status_code=404, detail="Run not found")
