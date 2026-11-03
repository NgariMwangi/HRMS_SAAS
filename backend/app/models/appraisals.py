"""Independent employee appraisals; legacy performance records remain intact."""
import uuid
from datetime import date
from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.performance import PerformanceRow


class AppraisalTemplate(PerformanceRow, Base):
    __tablename__ = "appraisal_templates"
    name: Mapped[str] = mapped_column(String(160))
    weighted: Mapped[bool] = mapped_column(Boolean, default=False)
    criteria: Mapped[list] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)


class AppraisalReview(PerformanceRow, Base):
    __tablename__ = "appraisal_reviews"
    __table_args__ = (CheckConstraint("start_date <= end_date", name="ck_simple_review_period"),
        CheckConstraint("end_date <= employee_deadline AND employee_deadline <= manager_deadline AND manager_deadline <= acknowledgement_deadline", name="ck_simple_review_deadlines"),
        CheckConstraint("preparation IN ('HR','MANAGER')", name="ck_simple_preparation"),
        CheckConstraint("status IN ('DRAFT','PUBLISHED','COMPLETED')", name="ck_simple_review_status"))
    name: Mapped[str] = mapped_column(String(160))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    employee_deadline: Mapped[date] = mapped_column(Date)
    manager_deadline: Mapped[date] = mapped_column(Date)
    acknowledgement_deadline: Mapped[date] = mapped_column(Date)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("appraisal_templates.id"))
    template_snapshot: Mapped[dict] = mapped_column(JSONB)
    preparation: Mapped[str] = mapped_column(String(20), default="HR")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    version: Mapped[int] = mapped_column(Integer, default=1)


class EmployeeAppraisal(PerformanceRow, Base):
    __tablename__ = "employee_appraisals"
    __table_args__ = (UniqueConstraint("review_id", "employee_id", name="uq_simple_appraisal_employee"),
        CheckConstraint("employee_id <> manager_id", name="ck_simple_appraiser_not_self"),
        CheckConstraint("version >= 1", name="ck_simple_appraisal_version"),
        CheckConstraint("status IN ('PREPARATION','SELF_REVIEW','MANAGER_REVIEW','DISCUSSION','HR_REVIEW','ACKNOWLEDGEMENT','COMPLETED')", name="ck_simple_appraisal_status"))
    review_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("appraisal_reviews.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    context: Mapped[dict] = mapped_column(JSONB)
    criteria: Mapped[list] = mapped_column(JSONB)
    preparation_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="PREPARATION")
    self_review: Mapped[dict] = mapped_column(JSONB, default=dict)
    manager_review: Mapped[dict] = mapped_column(JSONB, default=dict)
    discussion: Mapped[dict] = mapped_column(JSONB, default=dict)
    acknowledgement: Mapped[dict] = mapped_column(JSONB, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    history: Mapped[list] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
