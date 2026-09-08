from datetime import datetime
from pydantic import BaseModel, Field

class AssignInstructorsRequest(BaseModel):
    user_ids: list[str] = Field(default_factory=list)

class CourseInstructorResponse(BaseModel):
    user_id: str
    full_name: str
    email: str
    is_active: bool
    role_ids: list[str]
    assigned_at: datetime | None = None

class CourseAccessResponse(BaseModel):
    course_id: str
    user_id: str
    assigned: bool
    access_scope: str
