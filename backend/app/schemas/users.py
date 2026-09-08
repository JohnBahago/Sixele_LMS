from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True
    role_ids: list[str] = []

class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    email: EmailStr | None = None
    is_active: bool | None = None
    role_ids: list[str] | None = None

class UserResponse(BaseModel):
    id: str
    full_name: str
    email: str
    is_active: bool
    is_super_admin: bool = False
    role_ids: list[str] = []
    roles: list[str] = []
    permissions: list[str] = []
    created_at: str
