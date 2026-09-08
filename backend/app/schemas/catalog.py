from datetime import datetime
from pydantic import BaseModel, Field

class CatalogCourseResponse(BaseModel):
    id: str
    title: str
    short_description: str
    description: str
    category: str
    level: str
    duration_minutes: int | None
    objectives: list[str]
    visibility: str
    status: str
    instructor_ids: list[str]
    enrolled_count: int = 0
    created_at: datetime

class BulkEnrollmentRequest(BaseModel):
    learner_ids: list[str] = Field(min_length=1, max_length=500)
    course_id: str

class EnrollmentAdminResponse(BaseModel):
    id: str
    learner_id: str
    learner_name: str
    learner_email: str
    course_id: str
    course_title: str
    status: str
    progress_percent: float
    enrolled_at: datetime
    completed_at: datetime | None
    updated_at: datetime

class EnrollmentBulkResult(BaseModel):
    created: list[str] = []
    reactivated: list[str] = []
    skipped: list[str] = []
    errors: list[dict] = []
