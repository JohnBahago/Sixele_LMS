from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, model_validator

class QuizQuestionType(str, Enum):
    single_choice = "single_choice"
    multiple_choice = "multiple_choice"
    true_false = "true_false"
    short_answer = "short_answer"
    essay = "essay"

class QuizStatus(str, Enum):
    draft = "draft"
    published = "published"
    archived = "archived"

class QuizAttemptStatus(str, Enum):
    submitted = "submitted"
    needs_manual_grading = "needs_manual_grading"
    graded = "graded"

class QuizCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = ""
    instructions: str = ""
    time_limit_minutes: int | None = Field(default=None, ge=1)
    attempts_allowed: int = Field(default=1, ge=1)
    pass_mark: float = Field(default=50, ge=0, le=100)
    is_required: bool = True
    order: int = Field(default=0, ge=0)

class QuizUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    instructions: str | None = None
    time_limit_minutes: int | None = Field(default=None, ge=1)
    attempts_allowed: int | None = Field(default=None, ge=1)
    pass_mark: float | None = Field(default=None, ge=0, le=100)
    is_required: bool | None = None
    order: int | None = Field(default=None, ge=0)

class QuizResponse(BaseModel):
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
    question_count: int = 0
    total_points: float = 0
    created_by: str
    created_at: datetime
    updated_at: datetime

class QuizQuestionCreate(BaseModel):
    question_text: str = Field(min_length=2)
    question_type: QuizQuestionType = QuizQuestionType.single_choice
    options: list[str] = []
    correct_answers: list[str] = []
    points: float = Field(default=1, gt=0)
    explanation: str = ""
    order: int = Field(default=0, ge=0)
    is_required: bool = True

    @model_validator(mode="after")
    def validate_answers(self):
        if self.question_type in {QuizQuestionType.single_choice, QuizQuestionType.multiple_choice, QuizQuestionType.true_false}:
            if not self.options:
                raise ValueError("Choice-based questions require options")
            if not self.correct_answers:
                raise ValueError("Choice-based questions require at least one correct answer")
            if any(a not in self.options for a in self.correct_answers):
                raise ValueError("Every correct answer must exist in options")
            if self.question_type == QuizQuestionType.single_choice and len(self.correct_answers) != 1:
                raise ValueError("Single-choice questions require exactly one correct answer")
        return self

class QuizQuestionUpdate(BaseModel):
    question_text: str | None = Field(default=None, min_length=2)
    question_type: QuizQuestionType | None = None
    options: list[str] | None = None
    correct_answers: list[str] | None = None
    points: float | None = Field(default=None, gt=0)
    explanation: str | None = None
    order: int | None = Field(default=None, ge=0)
    is_required: bool | None = None

class QuizQuestionResponse(BaseModel):
    id: str
    quiz_id: str
    question_text: str
    question_type: str
    options: list[str]
    points: float
    explanation: str
    order: int
    is_required: bool

class QuizQuestionAdminResponse(QuizQuestionResponse):
    correct_answers: list[str]

class QuizAnswer(BaseModel):
    question_id: str
    answer: str | list[str] | None = None

class QuizAttemptCreate(BaseModel):
    answers: list[QuizAnswer] = []

class QuizAttemptResponse(BaseModel):
    id: str
    quiz_id: str
    learner_id: str
    attempt_number: int
    answers: list[QuizAnswer]
    score: float | None
    total_points: float
    percentage: float | None
    passed: bool | None
    status: str
    manual_grading_required: bool
    feedback: str
    submitted_at: datetime
    graded_at: datetime | None
    updated_at: datetime

class GradeQuizAttemptRequest(BaseModel):
    score: float = Field(ge=0)
    feedback: str = ""
