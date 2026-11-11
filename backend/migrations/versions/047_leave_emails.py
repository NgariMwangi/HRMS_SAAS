"""Durable leave notification outbox."""
from alembic import op
import sqlalchemy as sa

revision = "047_leave_emails"
down_revision = "046_payroll_exclusions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("leave_emails",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.UUID(), sa.ForeignKey("leave_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event", sa.String(30), nullable=False), sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("recipient_kind", sa.String(20), nullable=False), sa.Column("recipient_id", sa.UUID(), nullable=False),
        sa.Column("recipient_email", sa.String(255)), sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_error", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("request_id", "event", "purpose", "recipient_id", name="uq_leave_email_event"))
    op.create_index("ix_leave_emails_delivery", "leave_emails", ["status", "next_attempt_at"])
    op.execute("ALTER TABLE leave_emails ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE leave_emails FORCE ROW LEVEL SECURITY")
    scope = "current_setting('app.is_platform_admin', true) = 'true' OR tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid"
    op.execute(f"CREATE POLICY tenant_isolation_leave_emails ON leave_emails USING ({scope}) WITH CHECK ({scope})")
    company_scope = "current_setting('app.is_platform_admin', true) = 'true' OR nullif(current_setting('app.domain_company_id', true), '') IS NULL OR company_id = nullif(current_setting('app.domain_company_id', true), '')::uuid"
    op.execute(f"CREATE POLICY company_domain_scope ON leave_emails AS RESTRICTIVE USING ({company_scope}) WITH CHECK ({company_scope})")


def downgrade():
    op.drop_table("leave_emails")
