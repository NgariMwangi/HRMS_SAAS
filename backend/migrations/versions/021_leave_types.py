"""company leave types

Revision ID: 021_leave_types
Revises: 020_document_categories
Create Date: 2026-09-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "021_leave_types"
down_revision: Union[str, Sequence[str], None] = "020_document_categories"
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
        "leave_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("days", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("accrued", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("day_basis", sa.String(length=20), nullable=False, server_default="WORKING"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("company_id", "name", name="uq_leave_type_name"),
    )
    op.create_index("ix_leave_types_company_id", "leave_types", ["company_id"])
    op.execute("ALTER TABLE leave_types ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE leave_types FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_leave_types ON leave_types
            USING ({_COMPANY_SCOPE})
            WITH CHECK ({_COMPANY_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_leave_types ON leave_types")
    op.drop_index("ix_leave_types_company_id", table_name="leave_types")
    op.drop_table("leave_types")
