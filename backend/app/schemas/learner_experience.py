from datetime import datetime
from pydantic import BaseModel

class LearningItem(BaseModel):
    id: str
    item_type: str
    title: str
    module_id: str | None = None
    module_title: str | None = None
    order: int = 0
    is_required: bool = True
    status: str
    completed: bool = False
    locked: bool = False
    route: str

class LearnerResumeResponse(BaseModel):
    enrollment_id: str
    course_id: str
    course_title: str
    progress_percent: float
    completed: bool
    current_item: LearningItem | None = None
    next_item: LearningItem | None = None
    last_activity_at: datetime | None = None

class LearnerCourseExperienceResponse(BaseModel):
    enrollment_id: str
    course_id: str
    course_title: str
    progress_percent: float
    completed: bool
    total_items: int
    completed_items: int
    required_items: int
    completed_required_items: int
    current_item: LearningItem | None = None
    next_item: LearningItem | None = None
    items: list[LearningItem]

class LearnerNavigationResponse(BaseModel):
    enrollment_id: str
    current_item: LearningItem
    previous_item: LearningItem | None = None
    next_item: LearningItem | None = None
