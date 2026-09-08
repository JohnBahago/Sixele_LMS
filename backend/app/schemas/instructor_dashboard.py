from datetime import datetime
from pydantic import BaseModel

class InstructorCourseSummary(BaseModel):
    course_id: str
    title: str
    status: str
    enrolled_learners: int = 0
    completed_learners: int = 0
    average_progress: float = 0
    pending_submissions: int = 0
    pending_assessments: int = 0

class LearnerCourseProgress(BaseModel):
    enrollment_id: str
    learner_id: str
    full_name: str
    email: str
    status: str
    progress_percent: float = 0
    enrolled_at: datetime
    completed_at: datetime | None = None

class PendingSubmissionSummary(BaseModel):
    submission_id: str
    activity_id: str
    activity_title: str
    course_id: str
    course_title: str
    learner_id: str
    learner_name: str
    attempt_number: int
    status: str
    submitted_at: datetime

class PendingAssessmentSummary(BaseModel):
    attempt_id: str
    quiz_id: str
    quiz_title: str
    course_id: str
    course_title: str
    learner_id: str
    learner_name: str
    attempt_number: int
    status: str
    submitted_at: datetime

class InstructorDashboardResponse(BaseModel):
    assigned_courses: int
    total_learners: int
    active_learners: int
    completed_learners: int
    pending_submissions: int
    pending_assessments: int
    courses: list[InstructorCourseSummary]
    recent_submissions: list[PendingSubmissionSummary]
    recent_assessments: list[PendingAssessmentSummary]
