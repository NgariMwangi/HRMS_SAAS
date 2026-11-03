"""deduction types, employee deductions, payslip line link

Revision ID: 035_other_deductions
Revises: 034_voluntary_pension
Create Date: 2026-10-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "035_other_deductions"
down_revision: Union[str, Sequence[str], None] = "034_voluntary_pension"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COMPANY_SCOPE = """
                current_setting('app.is_platform_admin', true) = 'true'
                OR company_id IN (
                    SELECT id FROM companies
                    WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
"""


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_{table} ON {table}
            USING ({_COMPANY_SCOPE})
            WITH CHECK ({_COMPANY_SCOPE})
        """
    )


def upgrade() -> None:
    op.create_table(
        "deduction_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("default_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("company_id", "name", name="uq_deduction_type_name"),
        sa.CheckConstraint("category IN ('PERSONAL', 'COMPANY')", name="ck_deduction_type_category"),
    )
    op.create_index("ix_deduction_types_company_id", "deduction_types", ["company_id"])
    _rls("deduction_types")

    op.create_table(
        "employee_deductions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deduction_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deduction_type_id"], ["deduction_types.id"]),
        sa.CheckConstraint("frequency IN ('RECURRING', 'ONE_OFF')", name="ck_employee_deduction_frequency"),
        sa.CheckConstraint("status IN ('ACTIVE', 'STOPPED')", name="ck_employee_deduction_status"),
        sa.CheckConstraint("amount > 0", name="ck_employee_deduction_amount"),
    )
    op.create_index("ix_employee_deductions_company_id", "employee_deductions", ["company_id"])
    op.create_index("ix_employee_deductions_deduction_type_id", "employee_deductions", ["deduction_type_id"])
    op.create_index("ix_employee_deductions_employee", "employee_deductions", ["employee_id", "status"])
    _rls("employee_deductions")

    op.add_column(
        "payroll_payslip_lines",
        sa.Column("employee_deduction_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_payslip_lines_employee_deduction",
        "payroll_payslip_lines",
        "employee_deductions",
        ["employee_deduction_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_payroll_payslip_lines_employee_deduction_id",
        "payroll_payslip_lines",
        ["employee_deduction_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_payroll_payslip_lines_employee_deduction_id", table_name="payroll_payslip_lines")
    op.drop_constraint("fk_payslip_lines_employee_deduction", "payroll_payslip_lines", type_="foreignkey")
    op.drop_column("payroll_payslip_lines", "employee_deduction_id")
    for table in ["employee_deductions", "deduction_types"]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
