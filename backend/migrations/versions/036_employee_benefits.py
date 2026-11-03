"""benefit types, employee benefits, payslip line link

Revision ID: 036_employee_benefits
Revises: 035_other_deductions
Create Date: 2026-10-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "036_employee_benefits"
down_revision: Union[str, Sequence[str], None] = "035_other_deductions"
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
        "benefit_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("default_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("company_id", "name", name="uq_benefit_type_name"),
    )
    op.create_index("ix_benefit_types_company_id", "benefit_types", ["company_id"])
    _rls("benefit_types")

    op.create_table(
        "employee_benefits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("benefit_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note", sa.String(100), nullable=True),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["benefit_type_id"], ["benefit_types.id"]),
        sa.CheckConstraint("frequency IN ('RECURRING', 'ONE_OFF')", name="ck_employee_benefit_frequency"),
        sa.CheckConstraint("status IN ('ACTIVE', 'STOPPED')", name="ck_employee_benefit_status"),
        sa.CheckConstraint("amount > 0", name="ck_employee_benefit_amount"),
    )
    op.create_index("ix_employee_benefits_company_id", "employee_benefits", ["company_id"])
    op.create_index("ix_employee_benefits_benefit_type_id", "employee_benefits", ["benefit_type_id"])
    op.create_index("ix_employee_benefits_employee", "employee_benefits", ["employee_id", "status"])
    _rls("employee_benefits")

    op.add_column(
        "payroll_payslip_lines",
        sa.Column("employee_benefit_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_payslip_lines_employee_benefit",
        "payroll_payslip_lines",
        "employee_benefits",
        ["employee_benefit_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_payroll_payslip_lines_employee_benefit_id",
        "payroll_payslip_lines",
        ["employee_benefit_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_payroll_payslip_lines_employee_benefit_id", table_name="payroll_payslip_lines")
    op.drop_constraint("fk_payslip_lines_employee_benefit", "payroll_payslip_lines", type_="foreignkey")
    op.drop_column("payroll_payslip_lines", "employee_benefit_id")
    for table in ["employee_benefits", "benefit_types"]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
