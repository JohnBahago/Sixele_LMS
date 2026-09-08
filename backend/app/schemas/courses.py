from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

class CourseStatus(str, Enum):
    draft = "draft"
    setup = "setup"
    review = "review"
    published = "published"
    archived = "archived"

class CourseVisibility(str, Enum):
    private = "private"
    catalog = "catalog"
    unlisted = "unlisted"

class CompletionRule(BaseModel):
    require_all_lessons: bool = True
    require_activities: bool = False
    require_assessments: bool = False
    minimum_score: float | None = Field(default=None, ge=0, le=100)
    require_final_project: bool = False

class CourseCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    short_description: str = Field(default="", max_length=500)
    description: str = ""
    category: str = ""
    level: str = "beginner"
    duration_minutes: int | None = Field(default=None, ge=0)
    objectives: list[str] = []
    visibility: CourseVisibility = CourseVisibility.private
    completion_rule: CompletionRule = CompletionRule()

class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    short_description: str | None = Field(default=None, max_length=500)
    description: str | None = None
    category: str | None = None
    level: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    objectives: list[str] | None = None
    visibility: CourseVisibility | None = None
    completion_rule: CompletionRule | None = None

class CourseResponse(BaseModel):
    id: str
    title: str
    short_description: str
    description: str
    category: str
    level: str
    duration_minutes: int | None
    objectives: list[str]
    visibility: str
    status: str
    completion_rule: CompletionRule
    instructor_ids: list[str]
    created_by: str
    created_at: datetime
    updated_at: datetime

class ModuleCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = ""
    order: int = Field(default=0, ge=0)

class ModuleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    order: int | None = Field(default=None, ge=0)

class ModuleResponse(BaseModel):
    id: str
    course_id: str
    title: str
    description: str
    order: int
    created_at: datetime
    updated_at: datetime

class LessonType(str, Enum):
    video = "video"
    reading = "reading"
    resource = "resource"
    knowledge_check = "knowledge_check"

class LessonCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = ""
    lesson_type: LessonType = LessonType.reading
    content: str = ""
    duration_minutes: int | None = Field(default=None, ge=0)
    order: int = Field(default=0, ge=0)
    is_required: bool = True

class LessonUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    lesson_type: LessonType | None = None
    content: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    order: int | None = Field(default=None, ge=0)
    is_required: bool | None = None

class LessonResponse(BaseModel):
    id: str
    course_id: str
    module_id: str
    title: str
    description: str
    lesson_type: str
    content: str
    duration_minutes: int | None
    order: int
    is_required: bool
    created_at: datetime
    updated_at: datetime

class ResourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    resource_type: str = "link"
    url: str | None = None
    file_url: str | None = None
    description: str = ""

class ResourceResponse(BaseModel):
    id: str
    course_id: str
    module_id: str
    lesson_id: str | None
    name: str
    resource_type: str
    url: str | None
    file_url: str | None
    description: str
    created_at: datetime
