"""Restricted provenance and unmodified business fields from a legacy import."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.models.tenancy import uuid_pk


class LegacyImportRecord(Base):
    __tablename__ = "legacy_import_records"
    __table_args__ = (UniqueConstraint("tenant_id", "source", "source_table", "source_id", name="uq_legacy_import_origin"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), index=True)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), index=True)
    source: Mapped[str] = mapped_column(String(150))
    source_table: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[str] = mapped_column(String(150))
    destination_table: Mapped[str | None] = mapped_column(String(80))
    destination_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    payload: Mapped[dict] = mapped_column(JSONB)
    snapshot_sha256: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
