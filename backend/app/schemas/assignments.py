from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class AssignmentType(str, Enum):
    assignment = "assignment"
    final_project = "final_project"

class AssignmentStatus(str, Enum):
    draft = "draft"
    published = "published"
    archived = "archived"

class AssignmentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = ""
    instructions: str = ""
    assignment_type: AssignmentType = AssignmentType.assignment
    module_id: str | None = None
    brief: str = ""
    deliverables: list[str] = []
    submission_type: str = "text_and_file"
    max_score: float = Field(default=100, gt=0)
    pass_mark: float = Field(default=50, ge=0, le=100)
    attempts_allowed: int = Field(default=1, ge=1)
    due_days: int | None = Field(default=None, ge=0)
    is_required: bool = True
    order: int = Field(default=0, ge=0)
    rubric_id: str | None = None

class AssignmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    instructions: str | None = None
    assignment_type: AssignmentType | None = None
    module_id: str | None = None
    brief: str | None = None
    deliverables: list[str] | None = None
    submission_type: str | None = None
    max_score: float | None = Field(default=None, gt=0)
    pass_mark: float | None = Field(default=None, ge=0, le=100)
    attempts_allowed: int | None = Field(default=None, ge=1)
    due_days: int | None = Field(default=None, ge=0)
    is_required: bool | None = None
    order: int | None = Field(default=None, ge=0)
    rubric_id: str | None = None

class AssignmentResponse(BaseModel):
    id: str
    course_id: str
    module_id: str | None
    title: str
    description: str
    instructions: str
    assignment_type: str
    brief: str
    deliverables: list[str]
    submission_type: str
    max_score: float
    pass_mark: float
    attempts_allowed: int
    due_days: int | None
    is_required: bool
    order: int
    rubric_id: str | None
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime

class AssignmentSubmissionFile(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    file_url: str = Field(min_length=1)
    file_type: str = ""
    file_size: int | None = Field(default=None, ge=0)

class AssignmentSubmissionCreate(BaseModel):
    text_response: str = ""
    files: list[AssignmentSubmissionFile] = []
    deliverable_notes: str = ""

class AssignmentSubmissionResponse(BaseModel):
    id: str
    assignment_id: str
    course_id: str
    module_id: str | None
    learner_id: str
    attempt_number: int
    text_response: str
    files: list[AssignmentSubmissionFile]
    deliverable_notes: str
    status: str
    score: float | None
    percentage: float | None
    passed: bool | None
    grader_id: str | None
    feedback: str
    criterion_scores: list[dict]
    submitted_at: datetime
    graded_at: datetime | None
    updated_at: datetime

class GradeAssignmentRequest(BaseModel):
    score: float = Field(ge=0)
    feedback: str = ""
    criterion_scores: list[dict] = []
    status: str | None = None

class AssignmentProgressResponse(BaseModel):
    assignment_id: str
    learner_id: str
    status: str
    latest_submission_id: str | None
    attempts_used: int
    score: float | None
    percentage: float | None
    passed: bool | None
    updated_at: datetime
