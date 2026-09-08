from datetime import datetime
from pydantic import BaseModel

class EngagementLearner(BaseModel):
    enrollment_id: str
    learner_id: str
    learner_name: str
    email: str
    course_id: str
    course_title: str
    status: str
    progress_percent: float = 0
    last_activity_at: datetime | None = None
    days_inactive: int = 0
    risk_level: str = "healthy"
    risk_reasons: list[str] = []

class EngagementCourse(BaseModel):
    course_id: str
    course_title: str
    learners: int = 0
    active_learners: int = 0
    average_progress: float = 0
    active_7d: int = 0
    inactive_7d: int = 0
    at_risk: int = 0

class EngagementResponse(BaseModel):
    learners: list[EngagementLearner]
    courses: list[EngagementCourse]
    healthy: int = 0
    watch: int = 0
    high: int = 0
    critical: int = 0
