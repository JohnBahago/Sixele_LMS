from datetime import datetime
from pydantic import BaseModel, Field

class CommunicationCreate(BaseModel):
    type: str = Field(pattern="^(announcement|thread)$")
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    course_id: str | None = None
    recipient_ids: list[str] = Field(default_factory=list, max_length=2000)

class CommunicationReplyCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10000)

class CommunicationResponse(BaseModel):
    id: str
    type: str
    title: str
    body: str
    course_id: str | None = None
    course_title: str = ""
    author_id: str
    author_name: str
    author_role: str = ""
    is_read: bool = False
    status: str = "open"
    replies: list[dict] = []
    created_at: datetime
    updated_at: datetime

class CommunicationListResponse(BaseModel):
    items: list[CommunicationResponse]
    unread_count: int
    total: int
