import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.base import ApiModel


class ClockPayload(BaseModel):
    device_id: str = Field(min_length=8, max_length=64)


class AttendanceMark(BaseModel):
    employee_id: uuid.UUID
    work_on: date
    status: str = Field(min_length=1, max_length=20)
    note: str | None = Field(default=None, max_length=500)


class EmployeeLoginCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str | None = Field(default=None, max_length=255)


class AttendanceRead(ApiModel):
    employee_id: uuid.UUID
    employee_name: str
    employee_number: str
    company_id: uuid.UUID
    branch_id: uuid.UUID
    work_on: date
    status: str
    source: str | None = None
    checked_in_at: datetime | None = None
    checked_out_at: datetime | None = None
    note: str | None = None
    on_leave: bool = False
    has_clock_device: bool = False
    clock_login_email: str | None = None
    record_id: uuid.UUID | None = None
