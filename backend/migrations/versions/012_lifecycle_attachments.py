"""lifecycle event attachments

Revision ID: 012_lifecycle_attachments
Revises: 011_employee_lifecycle
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012_lifecycle_attachments"
down_revision: Union[str, Sequence[str], None] = "011_employee_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COMPANY_SCOPE = """
                current_setting('app.is_platform_admin', true) = 'true'
                OR company_id IN (
                    SELECT id FROM companies
                    WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
"""


def upgrade() -> None:
    op.create_table(
        "employee_lifecycle_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("file_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["employee_lifecycle_events.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_employee_lifecycle_attachments_company_id", "employee_lifecycle_attachments", ["company_id"])
    op.create_index("ix_employee_lifecycle_attachments_employee_id", "employee_lifecycle_attachments", ["employee_id"])
    op.create_index("ix_employee_lifecycle_attachments_event_id", "employee_lifecycle_attachments", ["event_id"])

    op.execute("ALTER TABLE employee_lifecycle_attachments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE employee_lifecycle_attachments FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_employee_lifecycle_attachments ON employee_lifecycle_attachments
            USING ({_COMPANY_SCOPE})
            WITH CHECK ({_COMPANY_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_employee_lifecycle_attachments ON employee_lifecycle_attachments")
    op.execute("ALTER TABLE employee_lifecycle_attachments NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE employee_lifecycle_attachments DISABLE ROW LEVEL SECURITY")
    op.drop_table("employee_lifecycle_attachments")
