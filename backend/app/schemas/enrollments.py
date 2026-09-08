from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class EnrollmentStatus(str, Enum):
    active = "active"
    completed = "completed"
    cancelled = "cancelled"

class EnrollmentCreate(BaseModel):
    learner_id: str
    course_id: str

class EnrollmentUpdate(BaseModel):
    status: EnrollmentStatus

class EnrollmentResponse(BaseModel):
    id: str
    course_id: str
    learner_id: str
    status: str
    progress_percent: float
    enrolled_at: datetime
    completed_at: datetime | None
    updated_at: datetime

class LessonProgressResponse(BaseModel):
    lesson_id: str
    learner_id: str
    completed: bool
    completed_at: datetime | None

class ActivityProgressSummary(BaseModel):
    activity_id: str
    status: str
    attempts_used: int = 0
    passed: bool | None = None
    percentage: float | None = None

class QuizProgressSummary(BaseModel):
    quiz_id: str
    attempts_used: int = 0
    passed: bool | None = None
    best_percentage: float | None = None

class CourseProgressResponse(BaseModel):
    enrollment_id: str
    course_id: str
    learner_id: str
    progress_percent: float
    completed: bool
    final_project_required: bool = False
    final_project_completed: bool = False
    lessons_required: int
    lessons_completed: int
    activities_required: int
    activities_passed: int
    assessments_required: int
    assessments_passed: int
    lesson_progress: list[LessonProgressResponse]
    activity_progress: list[ActivityProgressSummary]
    assessment_progress: list[QuizProgressSummary]
    minimum_score: float | None
    calculated_score: float | None
