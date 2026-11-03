"""Validated performance inputs. JSON snapshots always originate from these schemas."""
import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_default=True)


class RatingLevel(Input):
    value: Decimal = Field(max_digits=20, decimal_places=2)
    label: str = Field(min_length=1, max_length=80)
    description: str = ""
    minimum: Decimal = Field(max_digits=20, decimal_places=2)
    maximum: Decimal = Field(max_digits=20, decimal_places=2)


class ScaleInput(Input):
    name: str = Field(min_length=1, max_length=120)
    levels: list[RatingLevel] = Field(min_length=2, max_length=20)

    @model_validator(mode="after")
    def ranges(self):
        levels = sorted(self.levels, key=lambda item: item.minimum)
        values = [item.value for item in levels]
        if len(set(values)) != len(values) or values != sorted(values):
            raise ValueError("Rating values must be unique and increase with score ranges")
        for index, level in enumerate(levels):
            if level.minimum > level.maximum or not level.minimum <= level.value <= level.maximum:
                raise ValueError("Invalid rating range/value")
            if level.minimum != level.minimum.quantize(Decimal("0.01")) or level.maximum != level.maximum.quantize(Decimal("0.01")):
                raise ValueError("Score boundaries support at most two decimal places")
            if index and level.minimum <= levels[index - 1].maximum:
                raise ValueError("Rating ranges overlap")
            if index and level.minimum != levels[index - 1].maximum + Decimal("0.01"):
                raise ValueError("Rating ranges must cover every score to two decimal places without gaps")
        self.levels = levels
        return self


class SettingsInput(Input):
    frequency: Literal["ANNUAL", "SEMI_ANNUAL", "QUARTERLY", "PROBATION", "CUSTOM"] = "ANNUAL"
    rating_scale_id: uuid.UUID | None = None
    kpi_weight: Decimal = Field(default=70, ge=0, le=100)
    competency_weight: Decimal = Field(default=30, ge=0, le=100)
    require_self: bool = True
    require_manager: bool = True
    require_review: bool = True
    require_calibration: bool = False
    require_acknowledgement: bool = True
    employee_goal_creation: bool = True
    manager_goal_approval: bool = True
    auto_scoring: bool = False
    employee_view_manager: bool = True
    employee_view_calibration: bool = False
    development_threshold: Decimal | None = None
    pip_threshold: Decimal | None = None

    @model_validator(mode="after")
    def weights(self):
        if self.kpi_weight + self.competency_weight != 100:
            raise ValueError("KPI and competency contributions must total 100")
        return self


class Window(Input):
    start: date
    end: date

    @model_validator(mode="after")
    def dates(self):
        if self.start > self.end:
            raise ValueError("Window start cannot follow end")
        return self


class CycleInput(Input):
    goal_entry_roles: list[Literal["HR", "MANAGER", "EMPLOYEE"]] | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1, max_length=160)
    frequency: Literal["ANNUAL", "SEMI_ANNUAL", "QUARTERLY", "PROBATION", "CUSTOM"] = "ANNUAL"
    start_date: date
    end_date: date
    windows: dict[str, Window] = Field(default_factory=dict)

    @model_validator(mode="after")
    def dates(self):
        if self.start_date >= self.end_date:
            raise ValueError("Performance start must precede end")
        stages = ["GOAL_SETTING", "MID_YEAR", "SELF_ASSESSMENT", "MANAGER_ASSESSMENT", "CALIBRATION", "FINALIZATION"]
        if set(self.windows) - set(stages):
            raise ValueError("Unknown performance window")
        previous = None
        for key in stages:
            if key in self.windows:
                current = self.windows[key]
                if current.start < self.start_date:
                    raise ValueError("Windows cannot precede performance start")
                if previous and current.start < previous.end:
                    raise ValueError("Performance windows must be chronological")
                previous = current
        return self


class VersionInput(Input):
    version: int = Field(ge=1)


class TransitionInput(VersionInput):
    status: str
    reason: str = ""


class ParticipantInput(Input):
    employee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)
    branch_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    job_title_id: uuid.UUID | None = None
    all_employees: bool = False
    manager_id: uuid.UUID | None = None
    reviewer_id: uuid.UUID | None = None


class CycleUpdate(CycleInput):
    version: int = Field(ge=1)
    reason: str = Field(min_length=1)


class AppraiserUpdate(VersionInput):
    manager_id: uuid.UUID
    reviewer_id: uuid.UUID | None = None
    reason: str = Field(min_length=1)


class CompetencyInput(Input):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    category: str = "Core"
    indicators: list[str] = Field(default_factory=list)
    active: bool = True
    weight: Decimal = Field(default=1, gt=0, le=100)
    department_ids: list[uuid.UUID] = Field(default_factory=list)
    job_title_ids: list[uuid.UUID] = Field(default_factory=list)
    employee_ids: list[uuid.UUID] = Field(default_factory=list)


class GoalInput(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    category: str = "Individual"
    measurement: Literal["NUMBER", "PERCENTAGE", "CURRENCY", "BOOLEAN", "RATING", "MILESTONE", "QUALITATIVE"] = "NUMBER"
    direction: Literal["HIGHER_IS_BETTER", "LOWER_IS_BETTER", "TARGET_IS_BEST", "MILESTONE"] = "HIGHER_IS_BETTER"
    target: Decimal | None = Field(default=None, max_digits=20, decimal_places=4)
    unit: str = ""
    weight: Decimal = Field(ge=0, le=100, decimal_places=2)
    priority: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"
    start_date: date
    due_date: date
    scoring_cap: Decimal = Field(default=120, ge=100, le=200)

    @model_validator(mode="after")
    def dates(self):
        if self.start_date > self.due_date:
            raise ValueError("Goal start cannot follow due date")
        return self


class GoalUpdate(GoalInput):
    version: int = Field(ge=1)
    reason: str = Field(min_length=1)


class ProgressInput(VersionInput):
    progress: Decimal = Field(ge=0, le=100, decimal_places=2)
    actual: Decimal | None = Field(default=None, max_digits=20, decimal_places=4)
    comment: str = Field(min_length=1)
    blockers: str = ""
    achievements: str = ""


class CheckInInput(Input):
    kind: Literal["MONTHLY", "QUARTERLY", "MID_YEAR", "AD_HOC"] = "AD_HOC"
    meeting_date: date
    next_review: date | None = None
    achievements: str = ""
    challenges: str = ""
    employee_comments: str = ""
    manager_feedback: str = ""
    agreed_actions: str = ""
    goal_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def chronology(self):
        if self.next_review and self.next_review < self.meeting_date:
            raise ValueError("Next review cannot precede the check-in")
        return self


class ItemRating(Input):
    id: uuid.UUID
    rating: Decimal = Field(allow_inf_nan=False, max_digits=20, decimal_places=2)
    comment: str = ""


class AssessmentInput(VersionInput):
    goals: list[ItemRating] = Field(default_factory=list)
    competencies: list[ItemRating] = Field(default_factory=list)
    summary: str = ""
    achievements: str = ""
    challenges: str = ""
    support: str = ""
    career_interests: str = ""
    recommendations: str = ""


class ReviewInput(VersionInput):
    meeting_date: date
    attendees: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    employee_comments: str = ""
    manager_comments: str = ""
    achievements: str = ""
    improvements: str = ""
    disagreements: str = ""
    agreed_actions: str = ""
    follow_up: date | None = None

    @model_validator(mode="after")
    def chronology(self):
        if self.follow_up and self.follow_up < self.meeting_date:
            raise ValueError("Follow-up cannot precede the meeting")
        return self


class AcknowledgeInput(VersionInput):
    status: Literal["ACKNOWLEDGED", "ACKNOWLEDGED_WITH_COMMENTS", "DISAGREES"]
    comments: str = ""


class CalibrationInput(VersionInput):
    score: Decimal = Field(allow_inf_nan=False, max_digits=20, decimal_places=2)
    reason: str = Field(min_length=1)


class ReopenInput(VersionInput):
    reason: str = Field(min_length=1)
    stage: Literal["GOAL_SETTING", "SELF_ASSESSMENT", "MANAGER_ASSESSMENT", "REVIEW", "FINALIZATION"] = "MANAGER_ASSESSMENT"


class DevelopmentInput(Input):
    title: str = Field(min_length=1, max_length=200)
    owner_id: uuid.UUID
    due_date: date
    area: str = ""
    skill_gap: str = ""
    desired_outcome: str = ""
    action: str = Field(min_length=1)
    priority: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"
    comments: str = ""


class DevelopmentUpdate(VersionInput):
    status: Literal["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
    progress: Decimal = Field(ge=0, le=100, decimal_places=2)
    comments: str = ""


class PIPObjective(Input):
    title: str = Field(min_length=1)
    expected_standard: str = Field(min_length=1)
    target: str = Field(min_length=1)


class PIPInput(Input):
    employee_id: uuid.UUID
    manager_id: uuid.UUID
    hr_owner_id: uuid.UUID
    appraisal_id: uuid.UUID | None = None
    start_date: date
    end_date: date
    reason: str = Field(min_length=1)
    issues: str = Field(min_length=1)
    support: str = ""
    review_frequency_days: int = Field(default=30, ge=1, le=365)
    objectives: list[PIPObjective] = Field(min_length=1)

    @model_validator(mode="after")
    def dates(self):
        if self.start_date >= self.end_date:
            raise ValueError("PIP start must precede end")
        if self.manager_id == self.employee_id:
            raise ValueError("Employee cannot manage their own PIP")
        return self


class PIPUpdate(VersionInput):
    status: Literal["ACTIVE", "EXTENDED", "SUCCESSFUL", "UNSUCCESSFUL", "CANCELLED"]
    reason: str = Field(min_length=1)
    end_date: date | None = None
    outcome: str = ""


class PIPReviewInput(Input):
    meeting_date: date
    notes: str = Field(min_length=1)
    objective_progress: list[str] = Field(default_factory=list)
    next_review: date | None = None

    @model_validator(mode="after")
    def chronology(self):
        if self.next_review and self.next_review < self.meeting_date:
            raise ValueError("Next review cannot precede this review")
        return self
