from datetime import datetime
from pydantic import BaseModel

class ReportOverview(BaseModel):
    courses: int
    published_courses: int
    learners: int
    active_enrollments: int
    completed_enrollments: int
    completion_rate: float
    certificates_issued: int
    certificates_revoked: int
    submissions_pending: int
    assessments_pending: int
    average_course_progress: float

class CourseReport(BaseModel):
    course_id: str
    course_title: str
    status: str
    instructors: int
    enrollments: int
    active_learners: int
    completed_learners: int
    completion_rate: float
    average_progress: float
    activities: int
    activity_submissions: int
    pending_submissions: int
    assessments: int
    assessment_attempts: int
    average_assessment_score: float | None = None
    certificates_issued: int

class InstructorReport(BaseModel):
    instructor_id: str
    instructor_name: str
    email: str
    assigned_courses: int
    total_learners: int
    completed_learners: int
    pending_submissions: int
    pending_assessments: int

class LearnerReport(BaseModel):
    learner_id: str
    learner_name: str
    email: str
    enrollments: int
    active_enrollments: int
    completed_courses: int
    average_progress: float
    certificates_issued: int

class SubmissionReport(BaseModel):
    submission_id: str
    activity_id: str
    activity_title: str
    course_id: str
    course_title: str
    learner_id: str
    learner_name: str
    status: str
    score: float | None = None
    percentage: float | None = None
    submitted_at: datetime
    graded_at: datetime | None = None
