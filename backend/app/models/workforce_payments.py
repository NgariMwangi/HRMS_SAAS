"""Consultant fees, overtime approvals and an append-only payment ledger."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.tenancy import uuid_pk


class FinancialRow:
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Consultant(FinancialRow, Base):
    __tablename__ = "consultants"
    __table_args__ = (UniqueConstraint("company_id", "consultant_number", name="uq_consultant_number"),
                      CheckConstraint("withholding_rate >= 0 AND withholding_rate <= 100", name="ck_consultant_rate"))
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    consultant_number: Mapped[str] = mapped_column(String(50))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    other_names: Mapped[str | None] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    id_number: Mapped[str | None] = mapped_column(String(40))
    pin_number: Mapped[str | None] = mapped_column(String(40))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    bank_branch: Mapped[str | None] = mapped_column(String(100))
    bank_account_number: Mapped[str | None] = mapped_column(String(50))
    bank_code: Mapped[str | None] = mapped_column(String(20))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    withholding_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    prorate_payroll: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    notes: Mapped[str | None] = mapped_column(Text)


class ConsultantCompensation(FinancialRow, Base):
    __tablename__ = "consultant_compensation"
    __table_args__ = (UniqueConstraint("consultant_id", "effective_from", name="uq_consultant_fee_date"),
                      CheckConstraint("monthly_fee >= 0 AND other_allowances >= 0", name="ck_consultant_fee"))
    consultant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("consultants.id"))
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    monthly_fee: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    other_allowances: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)


class ConsultantPay(FinancialRow, Base):
    __tablename__ = "consultant_pay"
    __table_args__ = (UniqueConstraint("consultant_id", "period_start", name="uq_consultant_pay_month"),
                      CheckConstraint("status IN ('DRAFT', 'APPROVED')", name="ck_consultant_pay_status"),
                      CheckConstraint("gross >= 0 AND withholding_tax >= 0 AND net >= 0 AND gross = withholding_tax + net", name="ck_consultant_pay_amounts"))
    consultant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("consultants.id"))
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    compensation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("consultant_compensation.id"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    currency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("currencies.id"))
    recipient_name: Mapped[str] = mapped_column(String(255))
    gross: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    withholding_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3))
    withholding_tax: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    net: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    payable_days: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OvertimeRequest(FinancialRow, Base):
    __tablename__ = "overtime_requests"
    __table_args__ = (CheckConstraint("days > 0 AND ((daily_rate IS NOT NULL AND amount IS NOT NULL AND daily_rate > 0 AND amount > 0) OR (status IN ('REJECTED', 'CANCELLED') AND daily_rate IS NULL AND amount IS NULL))", name="ck_overtime_amounts"),
                      CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')", name="ck_overtime_status"))
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("employees.id"))
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id"))
    currency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("currencies.id"))
    worked_dates: Mapped[list[str]] = mapped_column(JSONB)
    days: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    daily_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    payroll_month: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    employee_benefit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employee_benefits.id"))


class PaymentRecord(FinancialRow, Base):
    __tablename__ = "payment_records"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_payment_amount"),
                      CheckConstraint("status IN ('POSTED', 'VOID')", name="ck_payment_status"),
                      CheckConstraint("num_nonnulls(payslip_id, consultant_pay_id, benefit_id) = 1", name="ck_payment_target"),
                      UniqueConstraint("company_id", "reference", name="uq_payment_reference"))
    payslip_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("payroll_payslips.id"))
    consultant_pay_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("consultant_pay.id"))
    benefit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("employee_benefits.id"))
    period_start: Mapped[date] = mapped_column(Date)
    currency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("currencies.id"))
    recipient_name: Mapped[str] = mapped_column(String(255))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    paid_on: Mapped[date] = mapped_column(Date)
    method: Mapped[str] = mapped_column(String(20))
    reference: Mapped[str] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="POSTED")
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(Text)
