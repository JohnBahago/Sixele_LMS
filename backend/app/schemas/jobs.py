from datetime import datetime
from typing import Any
from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    job_name: str
    description: str
    interval_seconds: int
    status: str
    last_run_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str | None = None
    last_result: dict[str, Any] | None = None
    worker_id: str | None = None


class JobRunResponse(BaseModel):
    job_name: str
    skipped: bool = False
    reason: str | None = None
    result: dict[str, Any] | None = None
