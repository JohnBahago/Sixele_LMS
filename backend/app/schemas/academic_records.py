from datetime import datetime
from pydantic import BaseModel

class AcademicRecordItem(BaseModel):
    course_id: str
    course_title: str
    enrollment_id: str
    status: str
    enrolled_at: datetime | None = None
    completed_at: datetime | None = None
    progress_percent: float = 0
    score: float | None = None
    certificate_number: str | None = None
    certificate_status: str | None = None

class AcademicRecordResponse(BaseModel):
    learner_id: str
    learner_name: str
    email: str
    generated_at: datetime
    total_courses: int
    completed_courses: int
    certificates_issued: int
    average_score: float | None = None
    records: list[AcademicRecordItem]
