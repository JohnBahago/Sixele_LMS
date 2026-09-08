from pydantic import BaseModel, Field

class BulkUserStatusRequest(BaseModel):
    user_ids: list[str] = Field(min_length=1, max_length=500)
    is_active: bool

class CourseStatusRequest(BaseModel):
    status: str

class AdminQueueResponse(BaseModel):
    submissions: int
    assessments: int
    pending_enrollments: int
    total: int

class AdminOverviewResponse(BaseModel):
    users: dict
    roles: dict
    courses: dict
    enrollments: dict
    activities: dict
    assignments: dict
    assessments: dict
    submissions: dict
    certificates: dict
    notifications: dict
