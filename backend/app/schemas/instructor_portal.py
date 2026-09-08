from datetime import datetime
from pydantic import BaseModel

class InstructorLearnerSummary(BaseModel):
    learner_id: str
    full_name: str
    email: str
    enrollment_id: str
    course_id: str
    course_title: str
    status: str
    progress_percent: float = 0
    enrolled_at: datetime
    completed_at: datetime | None = None

class InstructorCourseDetail(BaseModel):
    course_id: str
    title: str
    description: str = ""
    status: str
    visibility: str = "private"
    modules: list[dict] = []
    learner_count: int = 0
    pending_work_count: int = 0

class InstructorWorkItem(BaseModel):
    item_id: str
    item_type: str
    title: str
    course_id: str
    course_title: str
    learner_id: str
    learner_name: str
    attempt_number: int = 1
    status: str
    submitted_at: datetime

class InstructorLearnerDetail(BaseModel):
    learner_id: str
    full_name: str
    email: str
    enrollment_id: str
    course_id: str
    course_title: str
    enrollment_status: str
    progress_percent: float = 0
    lessons_completed: int = 0
    activities_completed: int = 0
    assignments_completed: int = 0
    assessments_completed: int = 0
    recent_work: list[InstructorWorkItem] = []

from app.schemas.instructor_dashboard import InstructorCourseSummary

class InstructorPortalResponse(BaseModel):
    instructor_id: str
    assigned_courses: int
    total_enrollments: int
    active_learners: int
    completed_learners: int
    pending_work: int
    courses: list[InstructorCourseSummary]
    recent_work: list[InstructorWorkItem]
