from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class JobStatus(BaseModel):
    key: str
    name: str
    status: str          # idle | queued | running | done | failed
    remarks: str
    last_run_at: Optional[str]
    triggered_by: Optional[str]
    run_id: Optional[str]


class TriggerResponse(BaseModel):
    run_id: str
    job_key: str
    status: str = "queued"
    message: str
