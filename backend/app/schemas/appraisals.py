import uuid
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Criterion(Input):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1, max_length=80)
    section: Literal["OBJECTIVE", "BEHAVIOUR"] = "OBJECTIVE"
    title: str = Field(min_length=1, max_length=200)
    expected: str = Field(min_length=1, max_length=2000)
    evidence: str = Field(default="", max_length=2000)
    due_date: date | None = None
    weight: Decimal = Field(default=Decimal(0), ge=0, le=100, decimal_places=2)


class TemplateInput(Input):
    name: str = Field(min_length=1, max_length=160)
    weighted: bool = False
    criteria: list[Criterion] = Field(min_length=1, max_length=50)
    version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def unique(self):
        if len({c.id for c in self.criteria}) != len(self.criteria):
            raise ValueError("Each criterion must have a unique identifier")
        return self


class ReviewInput(Input):
    name: str = Field(min_length=1, max_length=160)
    start_date: date
    end_date: date
    employee_deadline: date
    manager_deadline: date
    acknowledgement_deadline: date
    template_id: uuid.UUID
    preparation: Literal["HR", "MANAGER"] = "HR"
    employee_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)
    version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def dates(self):
        if not self.start_date <= self.end_date <= self.employee_deadline <= self.manager_deadline <= self.acknowledgement_deadline:
            raise ValueError("Use a valid performance period followed by employee, manager and acknowledgement deadlines")
        if len(set(self.employee_ids)) != len(self.employee_ids):
            raise ValueError("Select each employee only once")
        return self


class Version(Input):
    version: int = Field(ge=1)


class PreparationInput(Version):
    manager_id: uuid.UUID | None = None
    criteria: list[Criterion] = Field(min_length=1, max_length=50)
    ready: bool = False


class ResponseItem(Input):
    criterion_id: str = Field(min_length=1, max_length=80)
    comment: str = Field(default="", max_length=4000)
    rating: int | None = Field(default=None, ge=1, le=5)


class AssessmentInput(Version):
    responses: list[ResponseItem] = Field(default_factory=list, max_length=50)
    achievements: str = Field(default="", max_length=5000)
    challenges: str = Field(default="", max_length=5000)
    support: str = Field(default="", max_length=5000)
    summary: str = Field(default="", max_length=5000)
    submit: bool = False


class DevelopmentItem(Input):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), max_length=80)
    title: str = Field(min_length=1, max_length=500)
    owner_id: uuid.UUID
    due_date: date
    status: Literal["NOT_STARTED", "IN_PROGRESS", "COMPLETED"] = "NOT_STARTED"


class DiscussionInput(Version):
    meeting_date: date
    summary: str = Field(min_length=1, max_length=5000)
    actions: list[DevelopmentItem] = Field(default_factory=list, max_length=30)
    submit: bool = False


class ActionInput(Version):
    action: Literal["RETURN_SELF", "RETURN_MANAGER", "PUBLISH", "ACKNOWLEDGE", "CLOSE", "REOPEN"]
    reason: str = Field(default="", max_length=4000)
    agrees: bool = True


class DevelopmentUpdate(Version):
    action_id: str = Field(max_length=80)
    status: Literal["NOT_STARTED", "IN_PROGRESS", "COMPLETED"]
