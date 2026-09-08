from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class ActivityType(str, Enum):
    practical_task = "practical_task"
    file_submission = "file_submission"
    project = "project"
    checklist = "checklist"
    simulation = "simulation"
    written_response = "written_response"
    evidence_submission = "evidence_submission"
    manual_assessment = "manual_assessment"

class SubmissionType(str, Enum):
    text = "text"
    file = "file"
    files = "files"
    checklist = "checklist"
    evidence = "evidence"
    manual = "manual"
    text_and_file = "text_and_file"

class ActivityStatus(str, Enum):
    draft = "draft"
    published = "published"
    archived = "archived"

class SubmissionStatus(str, Enum):
    submitted = "submitted"
    under_review = "under_review"
    passed = "passed"
    failed = "failed"
    revision_requested = "revision_requested"

class ActivityCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = ""
    activity_type: ActivityType = ActivityType.practical_task
    submission_type: SubmissionType = SubmissionType.text
    instructions: str = ""
    materials: list[str] = []
    task_description: str = ""
    max_score: float = Field(default=100, gt=0)
    pass_mark: float = Field(default=50, ge=0, le=100)
    attempts_allowed: int = Field(default=1, ge=1)
    due_days: int | None = Field(default=None, ge=0)
    is_required: bool = True
    order: int = Field(default=0, ge=0)
    rubric_id: str | None = None
    prerequisite_activity_ids: list[str] = []

class ActivityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    activity_type: ActivityType | None = None
    submission_type: SubmissionType | None = None
    instructions: str | None = None
    materials: list[str] | None = None
    task_description: str | None = None
    max_score: float | None = Field(default=None, gt=0)
    pass_mark: float | None = Field(default=None, ge=0, le=100)
    attempts_allowed: int | None = Field(default=None, ge=1)
    due_days: int | None = Field(default=None, ge=0)
    is_required: bool | None = None
    order: int | None = Field(default=None, ge=0)
    rubric_id: str | None = None
    prerequisite_activity_ids: list[str] | None = None

class ActivityResponse(BaseModel):
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
    rubric_id: str | None
    prerequisite_activity_ids: list[str] = []
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime

class RubricCriterionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    max_score: float = Field(gt=0)
    order: int = Field(default=0, ge=0)

class RubricCriterionResponse(RubricCriterionCreate):
    id: str

class RubricCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = ""
    criteria: list[RubricCriterionCreate] = []

class RubricUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None

class RubricResponse(BaseModel):
    id: str
    activity_id: str
    name: str
    description: str
    criteria: list[RubricCriterionResponse]
    created_by: str
    created_at: datetime
    updated_at: datetime

class SubmissionFile(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    file_url: str = Field(min_length=1)
    file_type: str = ""
    file_size: int | None = Field(default=None, ge=0)

class ChecklistItem(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    completed: bool = False

class SubmissionCreate(BaseModel):
    text_response: str = ""
    files: list[SubmissionFile] = []
    checklist: list[ChecklistItem] = []
    evidence_notes: str = ""

class SubmissionResponse(BaseModel):
    id: str
    activity_id: str
    course_id: str
    module_id: str
    learner_id: str
    attempt_number: int
    text_response: str
    files: list[SubmissionFile]
    checklist: list[ChecklistItem]
    evidence_notes: str
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

class GradeSubmissionRequest(BaseModel):
    score: float = Field(ge=0)
    feedback: str = ""
    criterion_scores: list[dict] = []
    status: SubmissionStatus | None = None

class ActivityProgressResponse(BaseModel):
    activity_id: str
    learner_id: str
    status: str
    latest_submission_id: str | None
    attempts_used: int
    score: float | None
    percentage: float | None
    passed: bool | None
    updated_at: datetime
