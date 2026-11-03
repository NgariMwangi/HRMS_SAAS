import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobTitleCreate(BaseModel):
    company_id: uuid.UUID
    department_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    status: str = Field(default="ACTIVE", max_length=30)


class JobTitleUpdate(BaseModel):
    department_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=50)
    description: str | None = None
    status: str | None = Field(default=None, max_length=30)


class JobTitleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    department_id: uuid.UUID | None
    name: str
    code: str | None
    description: str | None
    status: str
    created_at: datetime | None
    updated_at: datetime | None
