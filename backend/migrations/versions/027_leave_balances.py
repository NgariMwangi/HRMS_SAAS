"""employee leave balances

Revision ID: 027_leave_balances
Revises: 026_kenya_2026_one_off_holidays
Create Date: 2026-09-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "027_leave_balances"
down_revision: Union[str, Sequence[str], None] = "026_kenya_2026_one_off_holidays"
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
        "leave_balances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("leave_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("extra_days", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["leave_type_id"], ["leave_types.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("employee_id", "leave_type_id", "year", name="uq_leave_balance_year"),
    )
    op.create_index("ix_leave_balances_company_id", "leave_balances", ["company_id"])
    op.create_index("ix_leave_balances_employee_id", "leave_balances", ["employee_id"])
    op.create_index("ix_leave_balances_leave_type_id", "leave_balances", ["leave_type_id"])
    op.execute("ALTER TABLE leave_balances ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE leave_balances FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_leave_balances ON leave_balances
            USING ({_COMPANY_SCOPE})
            WITH CHECK ({_COMPANY_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_leave_balances ON leave_balances")
    op.drop_index("ix_leave_balances_leave_type_id", table_name="leave_balances")
    op.drop_index("ix_leave_balances_employee_id", table_name="leave_balances")
    op.drop_index("ix_leave_balances_company_id", table_name="leave_balances")
    op.drop_table("leave_balances")
