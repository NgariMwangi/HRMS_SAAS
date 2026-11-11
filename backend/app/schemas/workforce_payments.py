import uuid
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class ConsultantWrite(BaseModel):
    branch_id: uuid.UUID
    consultant_number: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    other_names: str | None = Field(default=None, max_length=150)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    id_number: str | None = Field(default=None, max_length=40)
    pin_number: str | None = Field(default=None, max_length=40)
    bank_name: str | None = Field(default=None, max_length=100)
    bank_branch: str | None = Field(default=None, max_length=100)
    bank_account_number: str | None = Field(default=None, max_length=50)
    bank_code: str | None = Field(default=None, max_length=20)
    start_date: date
    end_date: date | None = None
    withholding_rate: Decimal = Field(ge=0, le=100, decimal_places=3)
    prorate_payroll: bool = True
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("consultant_number", "first_name", "last_name")
    @classmethod
    def required_text(cls, value):
        if not value.strip():
            raise ValueError("This field is required")
        return value.strip()

    @model_validator(mode="after")
    def dates(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date")
        return self


class ConsultantCreate(ConsultantWrite):
    company_id: uuid.UUID


class FeeWrite(BaseModel):
    effective_from: date
    effective_to: date | None = None
    monthly_fee: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    other_allowances: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=2)
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Effective end must be on or after effective start")
        return self


class MonthWrite(BaseModel):
    month: date

    @field_validator("month")
    @classmethod
    def month_start(cls, value):
        return value.replace(day=1)


class OvertimeWrite(MonthWrite):
    employee_id: uuid.UUID
    worked_dates: list[date] = Field(min_length=1, max_length=31)
    days: Decimal = Field(gt=0, le=31, decimal_places=4)
    daily_rate: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    reason: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_days(self):
        if len(set(self.worked_dates)) != len(self.worked_dates):
            raise ValueError("Worked dates must be unique")
        if self.days > len(self.worked_dates):
            raise ValueError("Overtime days cannot exceed the number of worked dates")
        return self


class DecisionWrite(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "CANCELLED"]
    note: str | None = Field(default=None, max_length=5000)


class PaymentWrite(BaseModel):
    kind: Literal["PAYROLL", "CONSULTANT", "BENEFIT"]
    target_id: uuid.UUID
    month: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    paid_on: date
    method: Literal["BANK", "MPESA", "CASH", "OTHER"]
    reference: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=5000)

    @field_validator("reference")
    @classmethod
    def required_reference(cls, value):
        if not value.strip():
            raise ValueError("Payment reference is required")
        return value.strip()


class VoidWrite(BaseModel):
    reason: str = Field(min_length=1, max_length=5000)

    @field_validator("reason")
    @classmethod
    def required_reason(cls, value):
        if not value.strip():
            raise ValueError("Void reason is required")
        return value.strip()
