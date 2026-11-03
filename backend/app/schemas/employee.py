import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer, field_validator


class EmployeeSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    company_id: uuid.UUID
    branch_id: uuid.UUID
    first_name: str
    other_names: str | None
    last_name: str
    employee_number: str
    status: str


class EmployeeCreate(BaseModel):
    company_id: uuid.UUID
    branch_id: uuid.UUID
    department_id: uuid.UUID | None = None
    job_title_id: uuid.UUID | None = None
    employee_number: str | None = Field(default=None, max_length=50)
    first_name: str = Field(min_length=1, max_length=100)
    other_names: str | None = Field(default=None, max_length=150)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date | None = None
    id_number: str | None = Field(default=None, max_length=40)
    nssf_no: str | None = Field(default=None, max_length=40)
    shif_no: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    personal_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    other_phone: str | None = Field(default=None, max_length=50)
    employment_type: str = Field(default="FULL_TIME", max_length=30)
    date_joined: date | None = None
    date_ended: date | None = None
    previous_employee_id: uuid.UUID | None = None
    status: str = Field(default="ACTIVE", max_length=30)
    next_of_kin: list["NextOfKinWrite"] | None = None
    supervisor_ids: list[uuid.UUID] | None = None


class EmployeeUpdate(BaseModel):
    branch_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    job_title_id: uuid.UUID | None = None
    employee_number: str | None = Field(default=None, max_length=50)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    other_names: str | None = Field(default=None, max_length=150)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    date_of_birth: date | None = None
    id_number: str | None = Field(default=None, max_length=40)
    nssf_no: str | None = Field(default=None, max_length=40)
    shif_no: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    personal_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    other_phone: str | None = Field(default=None, max_length=50)
    employment_type: str | None = Field(default=None, max_length=30)
    date_joined: date | None = None
    date_ended: date | None = None
    status: str | None = Field(default=None, max_length=30)
    next_of_kin: list["NextOfKinWrite"] | None = None
    supervisor_ids: list[uuid.UUID] | None = None


class NextOfKinWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    relationship: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=1, max_length=50)
    other_phone: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=255)

    @field_validator("name", "relationship", "phone")
    @classmethod
    def _required_text(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("This field is required")
        return trimmed

    @field_validator("other_phone", "address", mode="before")
    @classmethod
    def _blank_optional(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("email", mode="before")
    @classmethod
    def _blank_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


class NextOfKinRead(NextOfKinWrite):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sort_order: int


class NextOfKinReplace(BaseModel):
    items: list[NextOfKinWrite] = Field(default_factory=list, max_length=20)


class SupervisorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_number: str
    first_name: str
    other_names: str | None
    last_name: str
    status: str


class SupervisorReplace(BaseModel):
    supervisor_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    branch_id: uuid.UUID
    department_id: uuid.UUID | None
    job_title_id: uuid.UUID | None
    employee_number: str
    first_name: str
    other_names: str | None
    last_name: str
    date_of_birth: date | None
    id_number: str | None = None
    nssf_no: str | None = None
    shif_no: str | None = None
    email: str | None
    personal_email: str | None
    phone: str | None
    other_phone: str | None
    employment_type: str
    date_joined: date | None
    date_ended: date | None
    has_photo: bool = False
    previous_employee_id: uuid.UUID | None = None
    status: str
    suspension_pay_treatment: str | None = None
    suspension_pay_deduction_percent: Decimal | None = None
    created_at: datetime | None
    updated_at: datetime | None
    has_clock_device: bool = False
    clock_login_email: str | None = None

    @field_serializer("suspension_pay_deduction_percent")
    def _employee_pay_percent(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class LifecycleAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str


class LifecycleEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    employee_id: uuid.UUID
    event_type: str
    reason: str | None
    effective_on: date
    note: str | None
    from_department_id: uuid.UUID | None
    to_department_id: uuid.UUID | None
    from_job_title_id: uuid.UUID | None
    to_job_title_id: uuid.UUID | None
    from_branch_id: uuid.UUID | None
    to_branch_id: uuid.UUID | None
    related_employee_id: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime | None
    pay_treatment: str | None = None
    pay_deduction_percent: Decimal | None = None
    from_date_ended: date | None = None
    to_date_ended: date | None = None
    extension_days: int | None = None
    employment_type: str | None = None
    employee_number: str | None = None
    employee_name: str | None = None
    attachments: list[LifecycleAttachmentRead] = []

    @field_serializer("pay_deduction_percent")
    def _event_pay_percent(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class LifecycleActionCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=30)
    reason: str | None = Field(default=None, max_length=80)
    effective_on: date
    note: str | None = None
    department_id: uuid.UUID | None = None
    job_title_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    rehire_mode: str | None = Field(default=None, max_length=20)
    copy_from_previous: bool = True
    employee_number: str | None = Field(default=None, max_length=50)
    first_name: str | None = Field(default=None, max_length=100)
    other_names: str | None = Field(default=None, max_length=150)
    last_name: str | None = Field(default=None, max_length=100)
    date_of_birth: date | None = None
    email: EmailStr | None = None
    personal_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    other_phone: str | None = Field(default=None, max_length=50)
    employment_type: str | None = Field(default=None, max_length=30)
    date_joined: date | None = None
    date_ended: date | None = None
    pay_treatment: str | None = Field(default=None, max_length=20)
    pay_deduction_percent: Decimal | None = Field(default=None, ge=0, le=100)
    extension_days: int | None = Field(default=None, ge=1, le=3650)


class LifecycleActionResult(BaseModel):
    event: LifecycleEventRead
    employee: EmployeeRead
    new_employee: EmployeeRead | None = None
