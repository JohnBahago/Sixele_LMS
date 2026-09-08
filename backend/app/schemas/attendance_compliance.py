from pydantic import BaseModel

class AttendanceComplianceRow(BaseModel):
    learner_id: str
    full_name: str = ""
    email: str = ""
    attended_sessions: int
    total_sessions: int
    attendance_rate: float
    status: str

class CohortAttendanceComplianceResponse(BaseModel):
    cohort_id: str
    threshold_percent: float
    learners: list[AttendanceComplianceRow]

class AttendanceComplianceSummary(BaseModel):
    threshold_percent: float
    status: str
    attendance_rate: float
    attended_sessions: int
    total_sessions: int
