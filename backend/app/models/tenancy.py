"""
Tenant -> Company -> Branch, plus platform-owned Country / Currency.

Countries and currencies are not tenant-scoped. Tenants may read them;
only seed/platform-admin code writes them.
"""

import uuid
from datetime import date, datetime

from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, LargeBinary, Numeric, String, Text, UniqueConstraint, func, inspect as sa_inspect, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Currency(Base):
    __tablename__ = "currencies"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(10))
    decimal_places: Mapped[int] = mapped_column(default=2, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Country(Base):
    __tablename__ = "countries"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(2), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    default_currency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("currencies.id")
    )
    default_timezone: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    default_currency: Mapped["Currency | None"] = relationship()
    branches: Mapped[list["Branch"]] = relationship(back_populates="country")
    public_holidays: Mapped[list["PublicHoliday"]] = relationship(back_populates="country")
    payroll_packs: Mapped[list["PayrollPack"]] = relationship(back_populates="country")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subscription_tier: Mapped[str] = mapped_column(
        String(30), default="TRIAL", nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(nullable=True)

    companies: Mapped[list["Company"]] = relationship(back_populates="tenant")
    users: Mapped[list["User"]] = relationship(back_populates="tenant")


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    registration_number: Mapped[str | None] = mapped_column(String(100))

    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    website: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="companies")
    branches: Mapped[list["Branch"]] = relationship(back_populates="company")
    departments: Mapped[list["Department"]] = relationship(back_populates="company")
    job_titles: Mapped[list["JobTitle"]] = relationship(back_populates="company")
    employees: Mapped[list["Employee"]] = relationship(back_populates="company")
    document_categories: Mapped[list["DocumentCategory"]] = relationship(back_populates="company")
    leave_types: Mapped[list["LeaveType"]] = relationship(back_populates="company")
    leave_requests: Mapped[list["LeaveRequest"]] = relationship(back_populates="company")
    leave_balances: Mapped[list["LeaveBalance"]] = relationship(back_populates="company")
    public_holidays: Mapped[list["PublicHoliday"]] = relationship(back_populates="company")
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(back_populates="company")
    payroll_settings: Mapped["CompanyPayrollSettings | None"] = relationship(
        back_populates="company", uselist=False
    )
    compensations: Mapped[list["EmployeeCompensation"]] = relationship(back_populates="company")
    payroll_runs: Mapped[list["PayrollRun"]] = relationship(back_populates="company")


class User(Base):
    """Login identity for a tenant. The first user created at signup is OWNER."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    google_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="OWNER", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    employee: Mapped["Employee | None"] = relationship(
        back_populates="login_user",
        foreign_keys=[employee_id],
    )


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_branch_code"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    country_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("countries.id"), nullable=False, index=True
    )
    currency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("currencies.id")
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)

    address: Mapped[str | None] = mapped_column(String)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(30))
    timezone: Mapped[str | None] = mapped_column(String(100))

    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="branches")
    country: Mapped["Country"] = relationship(back_populates="branches")
    currency: Mapped["Currency | None"] = relationship()
    employees: Mapped[list["Employee"]] = relationship(back_populates="branch")


class Department(Base):
    """How people are grouped inside a company. Employees will reference this."""

    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_department_name"),
        UniqueConstraint("company_id", "code", name="uq_department_code"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="departments")
    job_titles: Mapped[list["JobTitle"]] = relationship(back_populates="department")
    employees: Mapped[list["Employee"]] = relationship(back_populates="department")


class JobTitle(Base):
    """Roles people can hold in a company. Optional department default."""

    __tablename__ = "job_titles"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_job_title_name"),
        UniqueConstraint("company_id", "code", name="uq_job_title_code"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="job_titles")
    department: Mapped["Department | None"] = relationship(back_populates="job_titles")
    employees: Mapped[list["Employee"]] = relationship(back_populates="job_title")


class Employee(Base):
    """A person record in a company. Not the same as a login user."""

    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("company_id", "employee_number", name="uq_employee_number"),
        UniqueConstraint("company_id", "email", name="uq_employee_email"),
        Index(
            "uq_employee_id_number_open",
            "company_id",
            "id_number",
            unique=True,
            postgresql_where=text("id_number IS NOT NULL AND status <> 'TERMINATED'"),
        ),
        Index(
            "uq_employee_nssf_no_open",
            "company_id",
            "nssf_no",
            unique=True,
            postgresql_where=text("nssf_no IS NOT NULL AND status <> 'TERMINATED'"),
        ),
        Index(
            "uq_employee_shif_no_open",
            "company_id",
            "shif_no",
            unique=True,
            postgresql_where=text("shif_no IS NOT NULL AND status <> 'TERMINATED'"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), index=True
    )
    job_title_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_titles.id"), index=True
    )

    employee_number: Mapped[str] = mapped_column(String(50), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    other_names: Mapped[str | None] = mapped_column(String(150))
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    id_number: Mapped[str | None] = mapped_column(String(40))
    nssf_no: Mapped[str | None] = mapped_column(String(40))
    pin_number: Mapped[str | None] = mapped_column(String(40))
    shif_no: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(255))
    personal_email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    other_phone: Mapped[str | None] = mapped_column(String(50))
    employment_type: Mapped[str] = mapped_column(
        String(30), default="FULL_TIME", nullable=False
    )
    date_joined: Mapped[date | None] = mapped_column(Date)
    date_ended: Mapped[date | None] = mapped_column(Date)
    photo_content_type: Mapped[str | None] = mapped_column(String(80))
    photo_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)
    previous_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    clock_device_id: Mapped[str | None] = mapped_column(String(64))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    bank_branch: Mapped[str | None] = mapped_column(String(100))
    bank_account_number: Mapped[str | None] = mapped_column(String(50))
    bank_code: Mapped[str | None] = mapped_column(String(20))
    swift_code: Mapped[str | None] = mapped_column(String(20))
    prorate_payroll: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    suspension_pay_treatment: Mapped[str | None] = mapped_column(String(20))
    suspension_pay_deduction_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    @property
    def has_photo(self) -> bool:
        return self.photo_content_type is not None

    @property
    def has_clock_device(self) -> bool:
        return bool(self.clock_device_id)

    @property
    def clock_login_email(self) -> str | None:
        if "login_user" in sa_inspect(self).unloaded:
            return None
        return self.login_user.email if self.login_user is not None else None

    company: Mapped["Company"] = relationship(back_populates="employees")
    branch: Mapped["Branch"] = relationship(back_populates="employees")
    department: Mapped["Department | None"] = relationship(back_populates="employees")
    job_title: Mapped["JobTitle | None"] = relationship(back_populates="employees")
    previous_employee: Mapped["Employee | None"] = relationship(
        remote_side="Employee.id", foreign_keys=[previous_employee_id]
    )
    login_user: Mapped["User | None"] = relationship(
        back_populates="employee",
        foreign_keys="User.employee_id",
    )
    lifecycle_events: Mapped[list["EmployeeLifecycleEvent"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        foreign_keys="EmployeeLifecycleEvent.employee_id",
    )
    next_of_kin: Mapped[list["EmployeeNextOfKin"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        order_by="EmployeeNextOfKin.sort_order",
    )
    documents: Mapped[list["EmployeeDocument"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    leave_requests: Mapped[list["LeaveRequest"]] = relationship(
        back_populates="employee",
        foreign_keys="LeaveRequest.employee_id",
    )
    leave_balances: Mapped[list["LeaveBalance"]] = relationship(back_populates="employee")
    supervisor_links: Mapped[list["EmployeeSupervisor"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
        foreign_keys="EmployeeSupervisor.employee_id",
        order_by="EmployeeSupervisor.sort_order",
    )
    compensations: Mapped[list["EmployeeCompensation"]] = relationship(back_populates="employee")


class EmployeeLifecycleEvent(Base):
    """Append-only hire, suspend, role, exit, and rehire history."""

    __tablename__ = "employee_lifecycle_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(80))
    effective_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String)
    from_department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    to_department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    from_job_title_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    to_job_title_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    from_branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    to_branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    related_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    pay_treatment: Mapped[str | None] = mapped_column(String(20))
    pay_deduction_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    from_date_ended: Mapped[date | None] = mapped_column(Date)
    to_date_ended: Mapped[date | None] = mapped_column(Date)
    extension_days: Mapped[int | None] = mapped_column(Integer)
    employment_type: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    employee: Mapped["Employee"] = relationship(
        back_populates="lifecycle_events", foreign_keys=[employee_id]
    )
    attachments: Mapped[list["EmployeeLifecycleAttachment"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EmployeeLifecycleAttachment(Base):
    """A file attached to a suspend, role-change, terminate, or extend event."""

    __tablename__ = "employee_lifecycle_attachments"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employee_lifecycle_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    event: Mapped["EmployeeLifecycleEvent"] = relationship(back_populates="attachments")


class EmployeeNextOfKin(Base):
    """Optional emergency contact for an employee. Multiple rows are allowed."""

    __tablename__ = "employee_next_of_kin"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee: Mapped["Employee"] = relationship(back_populates="next_of_kin")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    relationship: Mapped[str] = mapped_column(String(80), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    other_phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class EmployeeSupervisor(Base):
    """Optional reporting link. An employee may have one or many fellow supervisors."""

    __tablename__ = "employee_supervisors"
    __table_args__ = (
        UniqueConstraint("employee_id", "supervisor_id", name="uq_employee_supervisor"),
        CheckConstraint("employee_id <> supervisor_id", name="ck_employee_not_own_supervisor"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supervisor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    employee: Mapped["Employee"] = relationship(
        back_populates="supervisor_links",
        foreign_keys=[employee_id],
    )
    supervisor: Mapped["Employee"] = relationship(foreign_keys=[supervisor_id])


class DocumentCategory(Base):
    """Company-owned file grouping. Lifecycle is seeded and cannot be edited."""

    __tablename__ = "document_categories"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_document_category_name"),
        Index(
            "uq_document_category_system_key",
            "company_id",
            "system_key",
            unique=True,
            postgresql_where=text("system_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    system_key: Mapped[str | None] = mapped_column(String(30))
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="document_categories")
    documents: Mapped[list["EmployeeDocument"]] = relationship(back_populates="document_category")


class EmployeeDocument(Base):
    """A file HR uploaded onto an employee record, grouped by category."""

    __tablename__ = "employee_documents"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_categories.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    issued_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    employee: Mapped["Employee"] = relationship(back_populates="documents")
    document_category: Mapped["DocumentCategory"] = relationship(back_populates="documents")


class PlatformAdmin(Base):
    """You — the system owner. Not tenant-scoped."""

    __tablename__ = "platform_admins"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE", nullable=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class PublicHoliday(Base):
    """Company public holiday. YEARLY repeats every year; ONCE is a single date."""

    __tablename__ = "public_holidays"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_public_holiday_name"),
        CheckConstraint("kind IN ('YEARLY', 'ONCE')", name="ck_public_holiday_kind"),
        CheckConstraint(
            "(kind = 'YEARLY' AND month IS NOT NULL AND day IS NOT NULL AND observed_on IS NULL)"
            " OR (kind = 'ONCE' AND observed_on IS NOT NULL AND month IS NULL AND day IS NULL)",
            name="ck_public_holiday_shape",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    country_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("countries.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    month: Mapped[int | None] = mapped_column(Integer)
    day: Mapped[int | None] = mapped_column(Integer)
    observed_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="public_holidays")
    country: Mapped["Country | None"] = relationship(back_populates="public_holidays")


class LeaveType(Base):
    """Company-owned leave category. Accrual and day counting are editable."""

    __tablename__ = "leave_types"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_leave_type_name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"))
    accrued: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accrual_per_month: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"))
    day_basis: Mapped[str] = mapped_column(String(20), default="WORKING", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="leave_types")
    leave_requests: Mapped[list["LeaveRequest"]] = relationship(back_populates="leave_type")
    leave_balances: Mapped[list["LeaveBalance"]] = relationship(back_populates="leave_type")


class LeaveBalance(Base):
    """HR adjustment for one employee, leave type, and calendar year."""

    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint("employee_id", "leave_type_id", "year", name="uq_leave_balance_year"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leave_types.id", ondelete="CASCADE"), nullable=False, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    extra_days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="leave_balances")
    employee: Mapped["Employee"] = relationship(back_populates="leave_balances")
    leave_type: Mapped["LeaveType"] = relationship(back_populates="leave_balances")


class LeaveRequest(Base):
    """A leave application. Approval path depends on who submitted it."""

    __tablename__ = "leave_requests"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leave_types.id"), nullable=False, index=True
    )
    start_on: Mapped[date] = mapped_column(Date, nullable=False)
    end_on: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    reason: Mapped[str | None] = mapped_column(String)
    requested_as: Mapped[str] = mapped_column(String(20), nullable=False)
    approval_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    requested_by_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="leave_requests")
    employee: Mapped["Employee"] = relationship(
        back_populates="leave_requests",
        foreign_keys=[employee_id],
    )
    leave_type: Mapped["LeaveType"] = relationship(back_populates="leave_requests")
    decisions: Mapped[list["LeaveDecision"]] = relationship(
        back_populates="leave_request",
        cascade="all, delete-orphan",
        order_by="LeaveDecision.created_at",
    )


class LeaveDecision(Base):
    """One supervisor or HR decision on a leave request."""

    __tablename__ = "leave_decisions"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    leave_request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leave_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(String)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    leave_request: Mapped["LeaveRequest"] = relationship(back_populates="decisions")


class AttendanceRecord(Base):
    """One person, one calendar day at a branch. Self clock-in or HR mark."""

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_on", name="uq_attendance_employee_day"),
        CheckConstraint(
            "status IN ('PRESENT', 'LATE', 'ABSENT', 'ON_LEAVE')",
            name="ck_attendance_status",
        ),
        CheckConstraint("source IN ('SELF', 'HR')", name="ck_attendance_source"),
        Index("ix_attendance_branch_day", "branch_id", "work_on"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="HR")
    checked_in_at: Mapped[datetime | None] = mapped_column(nullable=True)
    checked_out_at: Mapped[datetime | None] = mapped_column(nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="attendance_records")
    employee: Mapped["Employee"] = relationship()


class AuditLog(Base):
    """One HTTP request: who made it, what they asked, and whether it succeeded."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("actor_kind IN ('TENANT', 'PLATFORM', 'ANONYMOUS')", name="ck_audit_actor_kind"),
        CheckConstraint("outcome IN ('SUCCESS', 'FAILED')", name="ck_audit_outcome"),
        Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    requester: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    request: Mapped[str] = mapped_column(Text, nullable=False, default="")
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
