from datetime import datetime
from pydantic import BaseModel, Field

class LearnerCourseCard(BaseModel):
    enrollment_id: str
    course_id: str
    title: str
    short_description: str
    category: str
    level: str
    progress_percent: float
    enrollment_status: str
    completed: bool
    enrolled_at: datetime
    completed_at: datetime | None = None

class LearnerDashboardResponse(BaseModel):
    learner_id: str
    total_courses: int
    active_courses: int
    completed_courses: int
    average_progress: float
    pending_activities: int
    pending_assessments: int
    pending_assignments: int = 0
    unread_notifications: int
    certificates_count: int
    courses: list[LearnerCourseCard]

class LearnerModule(BaseModel):
    id: str
    title: str
    description: str
    order: int
    lesson_count: int
    activity_count: int
    assessment_count: int

class LearnerCourseDetail(BaseModel):
    enrollment_id: str
    course_id: str
    title: str
    short_description: str
    description: str
    category: str
    level: str
    duration_minutes: int
    objectives: list[str]
    progress_percent: float
    enrollment_status: str
    completed: bool
    modules: list[LearnerModule]

class LearnerLessonDetail(BaseModel):
    id: str
    module_id: str
    course_id: str
    title: str
    description: str
    lesson_type: str
    content: str
    duration_minutes: int
    order: int
    is_required: bool
    completed: bool
    completed_at: datetime | None = None
    resources: list[dict] = []

class LearnerActivityDetail(BaseModel):
    id: str
    course_id: str
    module_id: str
    title: str
    description: str
    activity_type: str
    submission_type: str
    instructions: str
    materials: list[str]
    task_description: str
    max_score: float
    pass_mark: float
    attempts_allowed: int
    due_days: int | None
    is_required: bool
    order: int
    status: str
    progress_status: str
    attempts_used: int
    latest_submission_id: str | None
    score: float | None
    percentage: float | None
    passed: bool | None

class LearnerQuizDetail(BaseModel):
    id: str
    course_id: str
    module_id: str
    title: str
    description: str
    instructions: str
    time_limit_minutes: int | None
    attempts_allowed: int
    pass_mark: float
    is_required: bool
    order: int
    status: str
    question_count: int
    total_points: float
    attempts_used: int
    best_percentage: float | None
    passed: bool | None
    questions: list[dict] = []

class LearnerSubmitActivityResponse(BaseModel):
    submission_id: str
    activity_id: str
    attempt_number: int
    status: str
    message: str

class LearnerSubmitQuizResponse(BaseModel):
    attempt_id: str
    quiz_id: str
    attempt_number: int
    status: str
    score: float | None
    percentage: float | None
    passed: bool | None
    message: str


class LearnerAssignmentDetail(BaseModel):
    id: str
    course_id: str
    module_id: str | None
    title: str
    description: str
    instructions: str
    assignment_type: str
    brief: str
    deliverables: list[str] = []
    submission_type: str
    max_score: float
    pass_mark: float
    attempts_allowed: int
    due_days: int | None
    is_required: bool
    order: int
    status: str
    progress_status: str
    attempts_used: int
    latest_submission_id: str | None
    score: float | None
    percentage: float | None
    passed: bool | None
    feedback: str


class LearnerSubmitAssignmentResponse(BaseModel):
    submission_id: str
    assignment_id: str
    attempt_number: int
    status: str
    message: str


class LearnerAssignmentSummary(BaseModel):
    assignment_id: str
    title: str
    assignment_type: str
    is_required: bool
    status: str
    progress_status: str
    attempts_used: int
    attempts_allowed: int
    percentage: float | None
    passed: bool | None

