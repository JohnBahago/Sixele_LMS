from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

class NotificationType(str, Enum):
    system = "system"
    enrollment = "enrollment"
    submission = "submission"
    grading = "grading"
    revision = "revision"
    assessment = "assessment"
    completion = "completion"
    course = "course"
    attendance = "attendance"

class NotificationCreate(BaseModel):
    recipient_ids: list[str] = Field(min_length=1)
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=2000)
    notification_type: NotificationType = NotificationType.system
    course_id: str | None = None
    action_url: str | None = None

class NotificationPreferenceUpdate(BaseModel):
    email_enabled: bool = True
    enrollment: bool = True
    submission: bool = True
    grading: bool = True
    revision: bool = True
    assessment: bool = True
    completion: bool = True
    course: bool = True
    attendance: bool = True
    system: bool = True

class NotificationResponse(BaseModel):
    id: str
    recipient_id: str
    title: str
    message: str
    notification_type: str
    course_id: str | None = None
    action_url: str | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime

class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    unread_count: int
    total: int

class NotificationPreferenceResponse(NotificationPreferenceUpdate):
    user_id: str
    updated_at: datetime
