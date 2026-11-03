"""Company-scoped recruitment records. Candidate identity is separate from applications."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Date, DateTime, ForeignKey, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, CheckConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.tenancy import uuid_pk


class RecruitmentRow:
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Vacancy(RecruitmentRow, Base):
    __tablename__ = "recruitment_jobs"
    __table_args__ = (CheckConstraint("openings > 0", name="ck_recruitment_openings"),)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(160), default="")
    employment_type: Mapped[str] = mapped_column(String(30), default="FULL_TIME")
    openings: Mapped[int] = mapped_column(Integer, default=1)
    closing_date: Mapped[date | None] = mapped_column(Date)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"))
    job_title_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("job_titles.id", ondelete="SET NULL"))
    manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")


class Candidate(RecruitmentRow, Base):
    __tablename__ = "recruitment_candidates"
    __table_args__ = (UniqueConstraint("company_id", "email", name="uq_recruitment_candidate_email"),)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str] = mapped_column(String(50), default="")
    source: Mapped[str] = mapped_column(String(100), default="Direct application")
    notes: Mapped[str] = mapped_column(Text, default="")
    cv_name: Mapped[str | None] = mapped_column(String(255))
    cv_type: Mapped[str | None] = mapped_column(String(100))
    cv_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"))


class Application(RecruitmentRow, Base):
    __tablename__ = "recruitment_applications"
    __table_args__ = (UniqueConstraint("job_id", "candidate_id", name="uq_recruitment_application"),)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recruitment_jobs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recruitment_candidates.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(30), default="APPLIED")


class Interview(RecruitmentRow, Base):
    __tablename__ = "recruitment_interviews"
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recruitment_applications.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="Interview")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    location: Mapped[str] = mapped_column(String(255), default="")
    interviewer_ids: Mapped[list] = mapped_column(JSONB, default=list)
    feedback: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="SCHEDULED")


class Offer(RecruitmentRow, Base):
    __tablename__ = "recruitment_offers"
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recruitment_applications.id", ondelete="CASCADE"), unique=True)
    salary: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    start_date: Mapped[date] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    terms: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")


class RecruitmentEvent(RecruitmentRow, Base):
    __tablename__ = "recruitment_events"
    application_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("recruitment_applications.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recruitment_jobs.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(Text, default="")
