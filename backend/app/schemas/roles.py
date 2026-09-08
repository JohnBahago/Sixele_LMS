from pydantic import BaseModel, Field

class Scope(BaseModel):
    type: str = "all"
    ids: list[str] = []

class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = ""
    permissions: list[str] = []
    scope: Scope = Scope()
    is_active: bool = True

class RoleResponse(RoleCreate):
    id: str
