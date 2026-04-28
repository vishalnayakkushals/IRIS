from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_serializer


class JobStatus(BaseModel):
    key: str
    name: str
    status: str
    remarks: str
    last_run_at: Optional[datetime | str]
    triggered_by: Optional[str]
    run_id: Optional[str]

    @field_serializer("last_run_at")
    def serialize_last_run_at(self, v: datetime | str | None) -> str | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return str(v)


class TriggerResponse(BaseModel):
    run_id: str
    job_key: str
    status: str = "queued"
    message: str
