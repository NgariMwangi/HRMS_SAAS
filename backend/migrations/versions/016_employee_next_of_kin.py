"""employee next of kin

Revision ID: 016_employee_next_of_kin
Revises: 015_extension_employment_type
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016_employee_next_of_kin"
down_revision: Union[str, Sequence[str], None] = "015_extension_employment_type"
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
        "employee_next_of_kin",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("relationship", sa.String(length=80), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=False),
        sa.Column("other_phone", sa.String(length=50), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_employee_next_of_kin_company_id", "employee_next_of_kin", ["company_id"])
    op.create_index("ix_employee_next_of_kin_employee_id", "employee_next_of_kin", ["employee_id"])

    op.execute("ALTER TABLE employee_next_of_kin ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE employee_next_of_kin FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_employee_next_of_kin ON employee_next_of_kin
            USING ({_COMPANY_SCOPE})
            WITH CHECK ({_COMPANY_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_employee_next_of_kin ON employee_next_of_kin")
    op.execute("ALTER TABLE employee_next_of_kin NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE employee_next_of_kin DISABLE ROW LEVEL SECURITY")
    op.drop_table("employee_next_of_kin")
