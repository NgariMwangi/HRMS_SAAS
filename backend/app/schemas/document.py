import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentCategoryCreate(BaseModel):
    company_id: uuid.UUID
    name: str = Field(min_length=1, max_length=80)


class DocumentCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    sort_order: int | None = None


class DocumentCategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    system_key: str | None
    locked: bool
    sort_order: int
    created_at: datetime | None
    updated_at: datetime | None


class CompanyDocumentRead(BaseModel):
    id: uuid.UUID
    source: str
    company_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    employee_number: str | None = None
    category_id: uuid.UUID | None = None
    category: str | None = None
    locked: bool = False
    filename: str
    content_type: str
    size: int = 0
    issued_on: date | None = None
    expires_on: date | None = None
    note: str | None = None
    event_id: uuid.UUID | None = None
    event_type: str | None = None
    event_label: str | None = None
    created_at: datetime | None = None
