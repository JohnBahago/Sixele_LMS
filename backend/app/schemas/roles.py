from typing import Any
from pydantic import BaseModel, Field

class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=500)
    permission_ids: list[str] = []
    scope: dict[str, Any] | None = None
    is_active: bool = True

class RoleResponse(RoleCreate):
    id: str
    user_count: int = 0
    is_system: bool = False
    created_at: str
    updated_at: str

class AssignRolesRequest(BaseModel):
    role_ids: list[str]

class RoleStatusUpdate(BaseModel):
    is_active: bool
