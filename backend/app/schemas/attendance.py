from datetime import datetime
from pydantic import BaseModel, Field

class AttendanceCorrection(BaseModel):
    status: str
    note: str = Field(default="", max_length=1000)

class AttendanceLockResponse(BaseModel):
    session_id: str
    locked: bool
    locked_at: datetime | None = None
    locked_by: str | None = None

class SessionAttendanceRecord(BaseModel):
    learner_id: str
    full_name: str = ""
    email: str = ""
    status: str | None = None
    note: str = ""
    marked_at: datetime | None = None
    marked_by: str | None = None

class SessionAttendanceResponse(BaseModel):
    session_id: str
    cohort_id: str
    session_title: str
    starts_at: datetime
    ends_at: datetime
    session_status: str
    attendance_locked: bool
    total_learners: int
    marked_count: int
    present_count: int
    late_count: int
    absent_count: int
    excused_count: int
    records: list[SessionAttendanceRecord]

class LearnerAttendanceRow(BaseModel):
    session_id: str
    session_title: str
    starts_at: datetime
    status: str | None = None
    note: str = ""

class LearnerAttendanceResponse(BaseModel):
    cohort_id: str
    learner_id: str
    attendance_rate: float
    attended_sessions: int
    total_sessions: int
    records: list[LearnerAttendanceRow]
