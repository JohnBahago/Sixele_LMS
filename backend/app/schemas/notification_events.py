from pydantic import BaseModel, Field
from typing import Literal

class NotificationEventTest(BaseModel):
    recipient_ids: list[str] = Field(min_length=1)
    event: Literal["enrollment", "submission", "grading", "revision", "assessment", "completion", "course", "system"]
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=2000)
    course_id: str | None = None
    action_url: str | None = None
