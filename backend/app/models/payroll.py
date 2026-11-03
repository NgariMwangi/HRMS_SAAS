"""Payroll packs (platform) and tenant compensation / runs."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.tenancy import Company, Country, Employee, uuid_pk


class PayrollPack(Base):
    __tablename__ = "payroll_packs"
    __table_args__ = (
        UniqueConstraint("country_id", "version", name="uq_payroll_pack_version"),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED')", name="ck_payroll_pack_status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    country_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("countries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    country: Mapped["Country"] = relationship(back_populates="payroll_packs")
    components: Mapped[list["PayrollPackComponent"]] = relationship(
        back_populates="pack", cascade="all, delete-orphan", order_by="PayrollPackComponent.sort_order"
    )
    constants: Mapped[list["PayrollPackConstant"]] = relationship(
        back_populates="pack", cascade="all, delete-orphan"
    )


class PayrollPackComponent(Base):
    __tablename__ = "payroll_pack_components"
    __table_args__ = (
        UniqueConstraint("pack_id", "code", name="uq_payroll_pack_component_code"),
        CheckConstraint("party IN ('EMPLOYEE', 'EMPLOYER')", name="ck_payroll_component_party"),
        CheckConstraint(
            "formula_kind IN ('PROGRESSIVE_BANDS', 'PERCENT', 'FIXED')",
            name="ck_payroll_component_formula",
        ),
        CheckConstraint(
            "base IN ('GROSS', 'BASIC', 'TAXABLE', 'PENSIONABLE')",
            name="ck_payroll_component_base",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payroll_packs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    party: Mapped[str] = mapped_column(String(20), nullable=False)
    formula_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    base: Mapped[str] = mapped_column(String(20), nullable=False)
    percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    cap: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    floor: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    min_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    relief_key: Mapped[str | None] = mapped_column(String(40))
    reduces_taxable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    pack: Mapped["PayrollPack"] = relationship(back_populates="components")
    bands: Mapped[list["PayrollPackBand"]] = relationship(
        back_populates="component", cascade="all, delete-orphan", order_by="PayrollPackBand.sort_order"
    )


class PayrollPackBand(Base):
    __tablename__ = "payroll_pack_bands"

    id: Mapped[uuid.UUID] = uuid_pk()
    component_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payroll_pack_components.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    from_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    to_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    rate_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)

    component: Mapped["PayrollPackComponent"] = relationship(back_populates="bands")


class PayrollPackConstant(Base):
    __tablename__ = "payroll_pack_constants"
    __table_args__ = (UniqueConstraint("pack_id", "key", name="uq_payroll_pack_constant_key"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payroll_packs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(40), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    pack: Mapped["PayrollPack"] = relationship(back_populates="constants")


class CompanyPayrollSettings(Base):
    __tablename__ = "company_payroll_settings"
    __table_args__ = (
        CheckConstraint(
            "frequency IN ('MONTHLY', 'BIWEEKLY', 'WEEKLY')",
            name="ck_payroll_settings_frequency",
        ),
        CheckConstraint(
            "salary_structure IN ('GROSS_ONLY', 'BASIC_PLUS_ALLOWANCES')",
            name="ck_payroll_settings_structure",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    frequency: Mapped[str] = mapped_column(String(20), nullable=False, default="MONTHLY")
    salary_structure: Mapped[str] = mapped_column(String(30), nullable=False, default="GROSS_ONLY")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    company: Mapped["Company"] = relationship(back_populates="payroll_settings")


class EmployeeCompensation(Base):
    __tablename__ = "employee_compensation"
    __table_args__ = (
        UniqueConstraint("employee_id", "effective_from", name="uq_employee_compensation_from"),
        CheckConstraint(
            "structure IN ('GROSS_ONLY', 'BASIC_PLUS_ALLOWANCES')",
            name="ck_compensation_structure",
        ),
        Index("ix_employee_compensation_employee", "employee_id", "effective_from"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    structure: Mapped[str] = mapped_column(String(30), nullable=False)
    gross_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    basic_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    voluntary_pension: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    pension_scheme: Mapped[str | None] = mapped_column(String(100))
    currency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("currencies.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    company: Mapped["Company"] = relationship(back_populates="compensations")
    employee: Mapped["Employee"] = relationship(back_populates="compensations")
    lines: Mapped[list["EmployeePayLine"]] = relationship(
        back_populates="compensation", cascade="all, delete-orphan", order_by="EmployeePayLine.sort_order"
    )

    @property
    def computed_gross(self) -> Decimal:
        if self.structure == "GROSS_ONLY":
            return self.gross_amount or Decimal("0")
        basic = self.basic_amount or Decimal("0")
        return basic + sum((line.amount for line in self.lines), Decimal("0"))

    @property
    def computed_basic(self) -> Decimal | None:
        if self.structure == "GROSS_ONLY":
            return None
        return self.basic_amount or Decimal("0")


class EmployeePayLine(Base):
    __tablename__ = "employee_pay_lines"
    __table_args__ = (CheckConstraint("kind IN ('ALLOWANCE')", name="ck_pay_line_kind"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    compensation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employee_compensation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="ALLOWANCE")
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    compensation: Mapped["EmployeeCompensation"] = relationship(back_populates="lines")


class DeductionType(Base):
    """Company catalog of non-statutory deductions (loans, SACCO, welfare schemes)."""

    __tablename__ = "deduction_types"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_deduction_type_name"),
        CheckConstraint("category IN ('PERSONAL', 'COMPANY')", name="ck_deduction_type_category"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    default_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class EmployeeDeduction(Base):
    """A deduction taken from one employee's net pay, every period or once."""

    __tablename__ = "employee_deductions"
    __table_args__ = (
        CheckConstraint("frequency IN ('RECURRING', 'ONE_OFF')", name="ck_employee_deduction_frequency"),
        CheckConstraint("status IN ('ACTIVE', 'STOPPED')", name="ck_employee_deduction_status"),
        CheckConstraint("amount > 0", name="ck_employee_deduction_amount"),
        Index("ix_employee_deductions_employee", "employee_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    deduction_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deduction_types.id"), nullable=False, index=True
    )
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    reference: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    deduction_type: Mapped["DeductionType"] = relationship()


class BenefitType(Base):
    """Company catalog of extra earnings (commission, bonus, overtime…)."""

    __tablename__ = "benefit_types"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_benefit_type_name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    default_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class EmployeeBenefit(Base):
    """A benefit added to one employee's gross pay, every period in a date range or once."""

    __tablename__ = "employee_benefits"
    __table_args__ = (
        CheckConstraint("frequency IN ('RECURRING', 'ONE_OFF')", name="ck_employee_benefit_frequency"),
        CheckConstraint("status IN ('ACTIVE', 'STOPPED')", name="ck_employee_benefit_status"),
        CheckConstraint("amount > 0", name="ck_employee_benefit_amount"),
        Index("ix_employee_benefits_employee", "employee_id", "status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    benefit_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("benefit_types.id"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(String(100))
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    benefit_type: Mapped["BenefitType"] = relationship()


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("branch_id", "period_start", "period_end", name="uq_payroll_run_branch_period"),
        CheckConstraint("status IN ('DRAFT', 'APPROVED')", name="ck_payroll_run_status"),
        Index("ix_payroll_runs_company_period", "company_id", "period_start"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    payroll_pack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payroll_packs.id"), nullable=False
    )
    currency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("currencies.id"), nullable=False
    )
    gross_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    deduction_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    employer_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    net_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    company: Mapped["Company"] = relationship(back_populates="payroll_runs")
    payslips: Mapped[list["PayrollPayslip"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class PayrollPayslip(Base):
    __tablename__ = "payroll_payslips"
    __table_args__ = (UniqueConstraint("run_id", "employee_id", name="uq_payroll_payslip_employee"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compensation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employee_compensation.id"), nullable=False
    )
    employee_name: Mapped[str] = mapped_column(String(255), nullable=False)
    employee_number: Mapped[str] = mapped_column(String(50), nullable=False)
    gross: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    basic: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    employee_deductions: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    employer_contributions: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    net: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)

    run: Mapped["PayrollRun"] = relationship(back_populates="payslips")
    lines: Mapped[list["PayrollPayslipLine"]] = relationship(
        back_populates="payslip", cascade="all, delete-orphan", order_by="PayrollPayslipLine.sort_order"
    )


class PayrollPayslipLine(Base):
    __tablename__ = "payroll_payslip_lines"
    __table_args__ = (
        CheckConstraint("party IN ('EMPLOYEE', 'EMPLOYER')", name="ck_payslip_line_party"),
        CheckConstraint("kind IN ('EARNING', 'DEDUCTION', 'EMPLOYER')", name="ck_payslip_line_kind"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payslip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payroll_payslips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    party: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    employee_deduction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employee_deductions.id", ondelete="SET NULL"), index=True
    )
    employee_benefit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employee_benefits.id", ondelete="SET NULL"), index=True
    )

    payslip: Mapped["PayrollPayslip"] = relationship(back_populates="lines")
