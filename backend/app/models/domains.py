import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.tenancy import uuid_pk


class CompanyDomain(Base):
    __tablename__ = "company_domains"
    __table_args__ = (
        CheckConstraint("kind IN ('AUTOMATIC','CUSTOM')", name="ck_company_domain_kind"),
        CheckConstraint("status IN ('PENDING','ACTIVE','DISABLED')", name="ck_company_domain_status"),
        Index("uq_company_automatic_domain", "company_id", unique=True, postgresql_where=text("kind = 'AUTOMATIC'")),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    hostname: Mapped[str] = mapped_column(String(253), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    verification_token: Mapped[str] = mapped_column(String(100))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime())
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())
