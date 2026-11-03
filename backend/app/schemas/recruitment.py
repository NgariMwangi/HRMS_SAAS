import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class JobInput(Input):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=20000)
    requirements: str = Field(default="", max_length=20000)
    location: str = Field(default="", max_length=160)
    employment_type: Literal["FULL_TIME", "CONTRACT", "INTERN", "PROBATION"] = "FULL_TIME"
    openings: int = Field(default=1, ge=1, le=1000)
    closing_date: date | None = None
    department_id: uuid.UUID | None = None
    job_title_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None


class CandidateInput(Input):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(default="", max_length=50)
    source: str = Field(default="Direct application", max_length=100)
    notes: str = Field(default="", max_length=10000)
    @field_validator("email")
    @classmethod
    def lower_email(cls, value):
        return value.lower()


class ApplyInput(Input):
    job_id: uuid.UUID
    candidate_id: uuid.UUID


class StageInput(Input):
    stage: Literal["APPLIED", "SHORTLISTED", "INTERVIEW", "REJECTED", "WITHDRAWN"]
    note: str = Field(default="", max_length=5000)


class StatusInput(Input):
    status: str = Field(max_length=30)
    note: str = Field(default="", max_length=5000)


class InterviewInput(Input):
    application_id: uuid.UUID
    title: str = Field(default="Interview", min_length=1, max_length=160)
    starts_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=480)
    location: str = Field(default="", max_length=255)
    interviewer_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    @field_validator("starts_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("Interview time must include a timezone")
        return value


class FeedbackInput(Input):
    rating: int = Field(ge=1, le=5)
    recommendation: Literal["PROCEED", "HOLD", "DO_NOT_PROCEED"]
    comments: str = Field(min_length=1, max_length=10000)


class OfferInput(Input):
    application_id: uuid.UUID
    salary: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3, pattern="^[A-Z]{3}$")
    start_date: date
    expires_on: date | None = None
    terms: str = Field(default="", max_length=20000)
    @model_validator(mode="after")
    def dates(self):
        if self.expires_on and self.expires_on > self.start_date:
            raise ValueError("Offer expiry must be on or before the start date")
        return self


class HireInput(Input):
    branch_id: uuid.UUID
    date_joined: date
    date_ended: date | None = None
    work_email: EmailStr | None = None
