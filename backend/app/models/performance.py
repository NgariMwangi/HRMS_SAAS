"""Company-scoped performance records. JSON stores immutable configuration/context snapshots."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.tenancy import uuid_pk


class PerformanceRow:
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class PerformanceSettings(PerformanceRow, Base):
    __tablename__ = "performance_settings"
    __table_args__ = (UniqueConstraint("company_id"),)
    config: Mapped[dict] = mapped_column(JSONB)


class RatingScale(PerformanceRow, Base):
    __tablename__ = "performance_rating_scales"
    name: Mapped[str] = mapped_column(String(120))
    levels: Mapped[list] = mapped_column(JSONB)


class Competency(PerformanceRow, Base):
    __tablename__ = "performance_competencies"
    name: Mapped[str] = mapped_column(String(120))
    definition: Mapped[dict] = mapped_column(JSONB)


class PerformanceCycle(PerformanceRow, Base):
    __tablename__ = "performance_cycles"
    __table_args__ = (CheckConstraint("start_date < end_date", name="ck_performance_cycle_dates"),
        CheckConstraint("version >= 1", name="ck_performance_cycle_version"),
        CheckConstraint("status IN ('DRAFT','GOAL_SETTING','ACTIVE','SELF_ASSESSMENT','MANAGER_ASSESSMENT','REVIEW','CALIBRATION','FINALIZATION','COMPLETED')", name="ck_performance_cycle_status"))
    name: Mapped[str] = mapped_column(String(160))
    frequency: Mapped[str] = mapped_column(String(30))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    windows: Mapped[dict] = mapped_column(JSONB)
    config: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    version: Mapped[int] = mapped_column(Integer, default=1)


class PerformanceParticipant(PerformanceRow, Base):
    __tablename__ = "performance_participants"
    __table_args__ = (UniqueConstraint("cycle_id", "employee_id", name="uq_performance_participant"),
        CheckConstraint("employee_id <> manager_id AND employee_id <> reviewer_id", name="ck_performance_not_self_appraiser"))
    cycle_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("performance_cycles.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"))
    context: Mapped[dict] = mapped_column(JSONB)


class Appraisal(PerformanceRow, Base):
    __tablename__ = "performance_appraisals"
    __table_args__ = (UniqueConstraint("participant_id"), CheckConstraint("version >= 1", name="ck_performance_appraisal_version"),
        CheckConstraint("status IN ('GOAL_SETTING','ACTIVE','SELF_ASSESSMENT','MANAGER_ASSESSMENT','REVIEW','CALIBRATION','FINALIZATION','FINALIZED')", name="ck_performance_appraisal_status"))
    participant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("performance_participants.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="GOAL_SETTING")
    version: Mapped[int] = mapped_column(Integer, default=1)
    self_assessment: Mapped[dict] = mapped_column(JSONB, default=dict)
    manager_assessment: Mapped[dict] = mapped_column(JSONB, default=dict)
    competencies: Mapped[list] = mapped_column(JSONB, default=list)
    review: Mapped[dict] = mapped_column(JSONB, default=dict)
    acknowledgement: Mapped[dict] = mapped_column(JSONB, default=dict)
    scores: Mapped[dict] = mapped_column(JSONB, default=dict)
    finalized_at: Mapped[datetime | None] = mapped_column()
    finalized_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class PerformanceGoal(PerformanceRow, Base):
    __tablename__ = "performance_goals"
    __table_args__ = (
        CheckConstraint("weight >= 0 AND weight <= 100", name="ck_performance_goal_weight"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_performance_goal_progress"),
        CheckConstraint("version >= 1", name="ck_performance_goal_version"),
        CheckConstraint("status IN ('DRAFT','PENDING_APPROVAL','APPROVED','IN_PROGRESS','COMPLETED','CANCELLED')", name="ck_performance_goal_status"),
    )
    appraisal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("performance_appraisals.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    definition: Mapped[dict] = mapped_column(JSONB)
    weight: Mapped[Decimal] = mapped_column(Numeric(7, 2))
    progress: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"))
    actual: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    version: Mapped[int] = mapped_column(Integer, default=1)
    approval: Mapped[dict] = mapped_column(JSONB, default=dict)


class GoalProgress(PerformanceRow, Base):
    __tablename__ = "performance_goal_progress"
    goal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("performance_goals.id", ondelete="CASCADE"), index=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    details: Mapped[dict] = mapped_column(JSONB)


class GoalEvidence(PerformanceRow, Base):
    __tablename__ = "performance_goal_evidence"
    goal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("performance_goals.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employee_documents.id", ondelete="CASCADE"), unique=True)


class PerformanceCheckIn(PerformanceRow, Base):
    __tablename__ = "performance_check_ins"
    appraisal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("performance_appraisals.id", ondelete="CASCADE"), index=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    meeting_date: Mapped[date] = mapped_column(Date)
    details: Mapped[dict] = mapped_column(JSONB)


class PerformanceEvent(PerformanceRow, Base):
    """Append-only domain history linked to the existing audit log."""
    __tablename__ = "performance_events"
    appraisal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("performance_appraisals.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    details: Mapped[dict] = mapped_column(JSONB)


class DevelopmentAction(PerformanceRow, Base):
    __tablename__ = "performance_development_actions"
    __table_args__ = (CheckConstraint("progress >= 0 AND progress <= 100", name="ck_development_progress"),
        CheckConstraint("version >= 1", name="ck_development_version"),
        CheckConstraint("status IN ('NOT_STARTED','IN_PROGRESS','COMPLETED','CANCELLED')", name="ck_development_status"))
    appraisal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("performance_appraisals.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    title: Mapped[str] = mapped_column(String(200))
    due_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="NOT_STARTED")
    progress: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"))
    details: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)


class PerformancePIP(PerformanceRow, Base):
    __tablename__ = "performance_pips"
    __table_args__ = (CheckConstraint("start_date < end_date", name="ck_performance_pip_dates"),
        CheckConstraint("version >= 1", name="ck_performance_pip_version"),
        CheckConstraint("employee_id <> manager_id", name="ck_performance_pip_manager"),
        CheckConstraint("status IN ('DRAFT','ACTIVE','EXTENDED','SUCCESSFUL','UNSUCCESSFUL','CANCELLED')", name="ck_performance_pip_status"))
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    manager_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    hr_owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    appraisal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("performance_appraisals.id", ondelete="SET NULL"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    details: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)


class PerformancePIPReview(PerformanceRow, Base):
    __tablename__ = "performance_pip_reviews"
    pip_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("performance_pips.id", ondelete="CASCADE"), index=True)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    meeting_date: Mapped[date] = mapped_column(Date)
    details: Mapped[dict] = mapped_column(JSONB)


class PerformanceNotification(PerformanceRow, Base):
    __tablename__ = "performance_notifications"
    __table_args__ = (UniqueConstraint("user_id", "event_key", name="uq_performance_notice"),)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_key: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(String(500))
    appraisal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("performance_appraisals.id", ondelete="CASCADE"))
    read_at: Mapped[datetime | None] = mapped_column()
