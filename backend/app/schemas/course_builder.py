from pydantic import BaseModel, Field

class CourseValidationIssue(BaseModel):
    code: str
    severity: str = Field(pattern="^(error|warning)$")
    message: str
    resource_type: str | None = None
    resource_id: str | None = None

class CourseValidationResponse(BaseModel):
    course_id: str
    valid: bool
    errors: list[CourseValidationIssue]
    warnings: list[CourseValidationIssue]
    counts: dict[str, int]

class CourseReviewRequest(BaseModel):
    note: str = Field(default="", max_length=2000)
