from datetime import datetime
from pydantic import BaseModel, Field

class CohortCreate(BaseModel):
    course_id: str
    name: str = Field(min_length=2, max_length=150)
    code: str = Field(min_length=2, max_length=50)
    description: str = Field(default="", max_length=1000)
    start_date: datetime | None = None
    end_date: datetime | None = None
    capacity: int | None = Field(default=None, ge=1, le=100000)
    status: str = "draft"

class CohortUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    code: str | None = Field(default=None, min_length=2, max_length=50)
    description: str | None = Field(default=None, max_length=1000)
    start_date: datetime | None = None
    end_date: datetime | None = None
    capacity: int | None = Field(default=None, ge=1, le=100000)
    status: str | None = None

class CohortResponse(BaseModel):
    id: str
    course_id: str
    course_title: str = ""
    name: str
    code: str
    description: str
    start_date: datetime | None
    end_date: datetime | None
    capacity: int | None
    learner_count: int = 0
    instructor_ids: list[str] = []
    status: str
    created_at: datetime
    updated_at: datetime

class CohortMembersRequest(BaseModel):
    learner_ids: list[str] = Field(min_length=1, max_length=1000)

class CohortInstructorsRequest(BaseModel):
    instructor_ids: list[str] = Field(max_length=100)

class SessionCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    starts_at: datetime
    ends_at: datetime
    location: str = Field(default="", max_length=500)
    meeting_url: str | None = Field(default=None, max_length=1000)
    notes: str = Field(default="", max_length=2000)
    status: str = "scheduled"

class SessionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = Field(default=None, max_length=500)
    meeting_url: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)
    status: str | None = None

class SessionResponse(BaseModel):
    id: str
    cohort_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    location: str
    meeting_url: str | None
    notes: str
    status: str
    created_at: datetime
    updated_at: datetime

class AttendanceRequest(BaseModel):
    learner_id: str
    status: str
    note: str = Field(default="", max_length=1000)

class AttendanceBulkRequest(BaseModel):
    records: list[AttendanceRequest] = Field(min_length=1, max_length=1000)

class AttendanceResponse(BaseModel):
    id: str
    session_id: str
    cohort_id: str
    learner_id: str
    status: str
    note: str
    marked_at: datetime
    marked_by: str

class CohortDashboardResponse(BaseModel):
    cohort: CohortResponse
    active_learners: int
    completed_learners: int
    average_progress: float
    upcoming_sessions: int
    attendance_rate: float
