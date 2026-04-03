from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RunRecord(BaseModel):
    run_id: str
    job_key: str
    job_name: str
    store_id: str
    status: str
    remarks: str
    triggered_by: str
    started_at: str
    completed_at: str
    created_at: str


class RunListResponse(BaseModel):
    runs: list[RunRecord]
    total: int
