"""Preserve legacy source provenance and fields without a direct destination."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "051_legacy_import"
down_revision = "050_overtime_currency"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("employee_compensation", sa.Column("is_historical", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table("legacy_import_records",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("companies.id")),
        sa.Column("source", sa.String(150), nullable=False),
        sa.Column("source_table", sa.String(80), nullable=False),
        sa.Column("source_id", sa.String(150), nullable=False),
        sa.Column("destination_table", sa.String(80)),
        sa.Column("destination_ids", JSONB(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "source", "source_table", "source_id", name="uq_legacy_import_origin"))
    for name in ["tenant_id", "company_id"]:
        op.create_index(f"ix_legacy_import_records_{name}", "legacy_import_records", [name])
    op.execute("ALTER TABLE legacy_import_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE legacy_import_records FORCE ROW LEVEL SECURITY")
    tenant = "current_setting('app.is_platform_admin', true) = 'true' OR tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid"
    op.execute(f"CREATE POLICY tenant_isolation ON legacy_import_records USING ({tenant}) WITH CHECK ({tenant})")
    domain = "current_setting('app.is_platform_admin', true) = 'true' OR nullif(current_setting('app.domain_company_id', true), '') IS NULL OR company_id = nullif(current_setting('app.domain_company_id', true), '')::uuid"
    op.execute(f"CREATE POLICY company_domain_scope ON legacy_import_records AS RESTRICTIVE USING ({domain}) WITH CHECK ({domain})")


def downgrade():
    op.drop_table("legacy_import_records")
    op.drop_column("employee_compensation", "is_historical")
