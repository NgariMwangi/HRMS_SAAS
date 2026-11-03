import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LeaveEmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID
    branch_id: uuid.UUID
    first_name: str
    other_names: str | None
    last_name: str
    employee_number: str
    status: str


class LeaveTypeCreate(BaseModel):
    company_id: uuid.UUID
    name: str = Field(min_length=1, max_length=80)
    days: Decimal = Field(default=Decimal("0"), ge=0)
    accrued: bool = False
    accrual_per_month: Decimal | None = Field(default=None, ge=0)
    day_basis: str = Field(default="WORKING", max_length=20)


class LeaveTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    days: Decimal | None = Field(default=None, ge=0)
    accrued: bool | None = None
    accrual_per_month: Decimal | None = Field(default=None, ge=0)
    day_basis: str | None = Field(default=None, max_length=20)
    sort_order: int | None = None


class LeaveHrCreate(BaseModel):
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    start_on: date
    end_on: date
    reason: str | None = Field(default=None, max_length=500)
    hr_action: str = Field(min_length=1, max_length=30)


class LeaveSelfCreate(BaseModel):
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    start_on: date
    end_on: date
    reason: str | None = Field(default=None, max_length=500)
    approval_mode: str = Field(default="SUPERVISOR_THEN_HR", max_length=30)


class LeaveSupervisorCreate(BaseModel):
    supervisor_employee_id: uuid.UUID
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    start_on: date
    end_on: date
    reason: str | None = Field(default=None, max_length=500)


class LeaveDecisionWrite(BaseModel):
    decision: str = Field(min_length=1, max_length=20)
    note: str | None = Field(default=None, max_length=500)
    supervisor_employee_id: uuid.UUID | None = None


class LeaveDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    step: str
    decision: str
    note: str | None
    actor_user_id: uuid.UUID | None
    actor_employee_id: uuid.UUID | None
    actor_name: str | None = None
    created_at: datetime | None


class LeaveRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    employee_number: str
    leave_type_id: uuid.UUID
    leave_type_name: str
    day_basis: str
    start_on: date
    end_on: date
    days: Decimal
    reason: str | None
    requested_as: str
    approval_mode: str
    status: str
    requested_by_user_id: uuid.UUID | None
    requested_by_employee_id: uuid.UUID | None
    requested_by_name: str | None = None
    decisions: list[LeaveDecisionRead] = []
    created_at: datetime | None
    updated_at: datetime | None


class LeaveTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    days: Decimal
    accrued: bool
    accrual_per_month: Decimal
    day_basis: str
    sort_order: int
    created_at: datetime | None
    updated_at: datetime | None


class LeaveBalanceRead(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    employee_number: str
    leave_type_id: uuid.UUID
    leave_type_name: str
    year: int
    accrued: bool
    unlimited: bool
    entitled: Decimal
    extra: Decimal
    used: Decimal
    pending: Decimal
    remaining: Decimal | None


class LeaveBalanceAdjust(BaseModel):
    employee_id: uuid.UUID
    leave_type_id: uuid.UUID
    year: int = Field(ge=2000, le=2100)
    extra_days: Decimal


class PublicHolidayCreate(BaseModel):
    company_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    country_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(min_length=1, max_length=20)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    observed_on: date | None = None


class PublicHolidayUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: str | None = Field(default=None, min_length=1, max_length=20)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    observed_on: date | None = None


class PublicHolidayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    country_id: uuid.UUID | None
    name: str
    kind: str
    month: int | None
    day: int | None
    observed_on: date | None
    created_at: datetime | None
    updated_at: datetime | None
