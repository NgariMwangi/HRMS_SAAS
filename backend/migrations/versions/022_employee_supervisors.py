"""optional employee supervisors

Revision ID: 022_employee_supervisors
Revises: 021_leave_types
Create Date: 2026-09-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "022_employee_supervisors"
down_revision: Union[str, Sequence[str], None] = "021_leave_types"
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
        "employee_supervisors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supervisor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supervisor_id"], ["employees.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("employee_id", "supervisor_id", name="uq_employee_supervisor"),
        sa.CheckConstraint("employee_id <> supervisor_id", name="ck_employee_not_own_supervisor"),
    )
    op.create_index("ix_employee_supervisors_company_id", "employee_supervisors", ["company_id"])
    op.create_index("ix_employee_supervisors_employee_id", "employee_supervisors", ["employee_id"])
    op.create_index("ix_employee_supervisors_supervisor_id", "employee_supervisors", ["supervisor_id"])
    op.execute("ALTER TABLE employee_supervisors ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE employee_supervisors FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_employee_supervisors ON employee_supervisors
            USING ({_COMPANY_SCOPE})
            WITH CHECK ({_COMPANY_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_employee_supervisors ON employee_supervisors")
    op.drop_index("ix_employee_supervisors_supervisor_id", table_name="employee_supervisors")
    op.drop_index("ix_employee_supervisors_employee_id", table_name="employee_supervisors")
    op.drop_index("ix_employee_supervisors_company_id", table_name="employee_supervisors")
    op.drop_table("employee_supervisors")
