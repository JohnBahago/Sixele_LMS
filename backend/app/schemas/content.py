from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl, model_validator

class ContentStatus(str, Enum):
    active = "active"
    archived = "archived"

class ContentType(str, Enum):
    document = "document"
    image = "image"
    video = "video"
    audio = "audio"
    spreadsheet = "spreadsheet"
    presentation = "presentation"
    archive = "archive"
    other = "other"

class ContentUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    folder: str | None = Field(None, max_length=255)
    status: ContentStatus | None = None
    course_id: str | None = None
    module_id: str | None = None
    lesson_id: str | None = None
    activity_id: str | None = None

class ContentResponse(BaseModel):
    id: str
    name: str
    description: str
    original_filename: str
    content_type: ContentType
    mime_type: str
    extension: str
    size_bytes: int
    storage_path: str
    url: str | None = None
    folder: str
    status: ContentStatus
    course_id: str | None = None
    module_id: str | None = None
    lesson_id: str | None = None
    activity_id: str | None = None
    uploaded_by: str
    created_at: datetime
    updated_at: datetime
