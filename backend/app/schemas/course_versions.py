from datetime import datetime
from pydantic import BaseModel, Field

class CourseVersionResponse(BaseModel):
    id: str
    course_id: str
    version_number: int
    status: str
    change_note: str
    source_version: int | None = None
    created_by: str
    created_at: datetime
    published_at: datetime | None = None
    published_by: str | None = None
    snapshot_counts: dict[str, int] = {}

class CreateRevisionRequest(BaseModel):
    change_note: str = Field(default="", max_length=1000)

class RollbackRequest(BaseModel):
    change_note: str = Field(default="Rollback to selected course version", max_length=1000)

class CourseVersionCompareResponse(BaseModel):
    course_id: str
    from_version: int
    to_version: int
    changes: dict[str, object]
