"""Verified company domains and additional company restrictions for domain sessions."""
from alembic import op
import sqlalchemy as sa
revision = "043_company_domains"
down_revision = "042_general_reports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("company_domains",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hostname", sa.String(253), nullable=False, unique=True),
        sa.Column("kind", sa.String(20), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("verification_token", sa.String(100), nullable=False), sa.Column("verified_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('AUTOMATIC','CUSTOM')", name="ck_company_domain_kind"),
        sa.CheckConstraint("status IN ('PENDING','ACTIVE','DISABLED')", name="ck_company_domain_status"))
    for column in ("tenant_id", "company_id"):
        op.create_index(f"ix_company_domains_{column}", "company_domains", [column])
    op.create_index("uq_company_automatic_domain", "company_domains", ["company_id"], unique=True, postgresql_where=sa.text("kind = 'AUTOMATIC'"))
    op.execute("ALTER TABLE company_domains ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE company_domains FORCE ROW LEVEL SECURITY")
    tenant_scope = "current_setting('app.is_platform_admin', true) = 'true' OR tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid"
    op.execute(f"CREATE POLICY tenant_isolation_company_domains ON company_domains USING ({tenant_scope}) WITH CHECK ({tenant_scope})")
    inspector = sa.inspect(op.get_bind())
    for table in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns(table)}
        if table != "companies" and "company_id" not in columns:
            continue
        column = "id" if table == "companies" else "company_id"
        scope = f"current_setting('app.is_platform_admin', true) = 'true' OR nullif(current_setting('app.domain_company_id', true), '') IS NULL OR {column} = nullif(current_setting('app.domain_company_id', true), '')::uuid"
        op.execute(f'CREATE POLICY company_domain_scope ON "{table}" AS RESTRICTIVE USING ({scope}) WITH CHECK ({scope})')
    op.execute("SELECT set_config('app.is_platform_admin', 'true', true)")
    op.execute("""INSERT INTO access_role_permissions (id, tenant_id, role_id, permission)
        SELECT gen_random_uuid(), tenant_id, id, 'domains.manage' FROM access_roles WHERE key IN ('OWNER','ADMIN')
        ON CONFLICT DO NOTHING""")


def downgrade():
    inspector = sa.inspect(op.get_bind())
    for table in inspector.get_table_names():
        op.execute(f'DROP POLICY IF EXISTS company_domain_scope ON "{table}"')
    op.execute("SELECT set_config('app.is_platform_admin', 'true', true)")
    op.execute("DELETE FROM access_role_permissions WHERE permission = 'domains.manage'")
    op.drop_table("company_domains")
