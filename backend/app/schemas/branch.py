import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BranchCreate(BaseModel):
    company_id: uuid.UUID
    country_id: uuid.UUID
    currency_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=50)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=30)
    timezone: str | None = Field(default=None, max_length=100)
    status: str = Field(default="ACTIVE", max_length=30)


class BranchUpdate(BaseModel):
    country_id: uuid.UUID | None = None
    currency_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=50)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=30)
    timezone: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=30)


class BranchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    country_id: uuid.UUID
    currency_id: uuid.UUID | None
    name: str
    code: str
    address: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    timezone: str | None
    status: str
    created_at: datetime | None
    updated_at: datetime | None
