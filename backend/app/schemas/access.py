import uuid

from pydantic import BaseModel, ConfigDict, Field


class PermissionRead(BaseModel):
    key: str
    label: str
    group: str


class AccessRoleWrite(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    permissions: list[str] = Field(default_factory=list)


class AccessRoleRead(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    is_system: bool
    locked: bool
    permissions: list[str]
    user_count: int = 0


class AccessUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    status: str
    employee_id: uuid.UUID | None = None


class AccessUserRoleUpdate(BaseModel):
    role: str = Field(min_length=1, max_length=30)


class MyAccessRead(BaseModel):
    role: str
    role_name: str | None
    permissions: list[str]
    employee_id: uuid.UUID | None
