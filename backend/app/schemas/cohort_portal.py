from datetime import datetime
from pydantic import BaseModel

class PortalCourseRef(BaseModel):
    id: str
    title: str

class PortalCohortSummary(BaseModel):
    id: str
    name: str
    code: str
    status: str
    start_date: datetime | None = None
    end_date: datetime | None = None
    course: PortalCourseRef
    learner_count: int = 0

class PortalSession(BaseModel):
    id: str
    cohort_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    location: str = ""
    meeting_url: str | None = None
    notes: str = ""
    status: str
    attendance_status: str | None = None

class LearnerCohortDetail(BaseModel):
    cohort: PortalCohortSummary
    progress_percent: float = 0
    enrollment_status: str = "active"
    attendance_rate: float = 0
    present_sessions: int = 0
    attended_sessions: int = 0
    total_sessions: int = 0
    upcoming_sessions: int = 0
    sessions: list[PortalSession] = []

class LearnerCohortPortalResponse(BaseModel):
    learner_id: str
    cohorts: list[LearnerCohortSummary]
    upcoming_sessions: list[PortalSession] = []

class InstructorCohortLearner(BaseModel):
    learner_id: str
    full_name: str
    email: str
    enrollment_status: str = "active"
    progress_percent: float = 0
    attendance_rate: float = 0
    present_sessions: int = 0
    attended_sessions: int = 0
    total_sessions: int = 0

class InstructorCohortDetail(BaseModel):
    cohort: PortalCohortSummary
    learners: list[InstructorCohortLearner] = []
    upcoming_sessions: list[PortalSession] = []
    total_sessions: int = 0
    average_progress: float = 0
    average_attendance_rate: float = 0

class InstructorCohortPortalResponse(BaseModel):
    instructor_id: str
    cohorts: list[PortalCohortSummary]
    upcoming_sessions: list[PortalSession] = []
