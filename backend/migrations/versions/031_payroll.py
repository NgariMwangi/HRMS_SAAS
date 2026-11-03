"""payroll packs, compensation, and payroll runs

Revision ID: 031_payroll
Revises: 030_attendance
Create Date: 2026-09-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "031_payroll"
down_revision: Union[str, Sequence[str], None] = "030_attendance"
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
        "payroll_packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("country_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("country_id", "version", name="uq_payroll_pack_version"),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED')", name="ck_payroll_pack_status"),
    )
    op.create_index("ix_payroll_packs_country_id", "payroll_packs", ["country_id"])

    op.create_table(
        "payroll_pack_components",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("party", sa.String(20), nullable=False),
        sa.Column("formula_kind", sa.String(30), nullable=False),
        sa.Column("base", sa.String(20), nullable=False),
        sa.Column("percent", sa.Numeric(8, 4), nullable=True),
        sa.Column("cap", sa.Numeric(18, 2), nullable=True),
        sa.Column("floor", sa.Numeric(18, 2), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("relief_key", sa.String(40), nullable=True),
        sa.Column("reduces_taxable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["pack_id"], ["payroll_packs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("pack_id", "code", name="uq_payroll_pack_component_code"),
        sa.CheckConstraint("party IN ('EMPLOYEE', 'EMPLOYER')", name="ck_payroll_component_party"),
        sa.CheckConstraint(
            "formula_kind IN ('PROGRESSIVE_BANDS', 'PERCENT', 'FIXED')",
            name="ck_payroll_component_formula",
        ),
        sa.CheckConstraint(
            "base IN ('GROSS', 'BASIC', 'TAXABLE', 'PENSIONABLE')",
            name="ck_payroll_component_base",
        ),
    )
    op.create_index("ix_payroll_pack_components_pack_id", "payroll_pack_components", ["pack_id"])

    op.create_table(
        "payroll_pack_bands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("from_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("to_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("rate_percent", sa.Numeric(8, 4), nullable=False),
        sa.ForeignKeyConstraint(["component_id"], ["payroll_pack_components.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_payroll_pack_bands_component_id", "payroll_pack_bands", ["component_id"])

    op.create_table(
        "payroll_pack_constants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.ForeignKeyConstraint(["pack_id"], ["payroll_packs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("pack_id", "key", name="uq_payroll_pack_constant_key"),
    )
    op.create_index("ix_payroll_pack_constants_pack_id", "payroll_pack_constants", ["pack_id"])

    op.create_table(
        "company_payroll_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False, server_default="MONTHLY"),
        sa.Column("salary_structure", sa.String(30), nullable=False, server_default="GROSS_ONLY"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("company_id"),
        sa.CheckConstraint("frequency IN ('MONTHLY', 'BIWEEKLY', 'WEEKLY')", name="ck_payroll_settings_frequency"),
        sa.CheckConstraint(
            "salary_structure IN ('GROSS_ONLY', 'BASIC_PLUS_ALLOWANCES')",
            name="ck_payroll_settings_structure",
        ),
    )
    _rls("company_payroll_settings")

    op.create_table(
        "employee_compensation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("structure", sa.String(30), nullable=False),
        sa.Column("gross_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("basic_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"]),
        sa.UniqueConstraint("employee_id", "effective_from", name="uq_employee_compensation_from"),
        sa.CheckConstraint(
            "structure IN ('GROSS_ONLY', 'BASIC_PLUS_ALLOWANCES')",
            name="ck_compensation_structure",
        ),
    )
    op.create_index("ix_employee_compensation_company_id", "employee_compensation", ["company_id"])
    op.create_index("ix_employee_compensation_employee", "employee_compensation", ["employee_id", "effective_from"])
    _rls("employee_compensation")

    op.create_table(
        "employee_pay_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("compensation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="ALLOWANCE"),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["compensation_id"], ["employee_compensation.id"], ondelete="CASCADE"),
        sa.CheckConstraint("kind IN ('ALLOWANCE')", name="ck_pay_line_kind"),
    )
    op.create_index("ix_employee_pay_lines_compensation_id", "employee_pay_lines", ["compensation_id"])
    op.execute("ALTER TABLE employee_pay_lines ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE employee_pay_lines FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_employee_pay_lines ON employee_pay_lines
            USING (
                current_setting('app.is_platform_admin', true) = 'true'
                OR compensation_id IN (
                    SELECT id FROM employee_compensation
                    WHERE company_id IN (
                        SELECT id FROM companies
                        WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
                    )
                )
            )
            WITH CHECK (
                current_setting('app.is_platform_admin', true) = 'true'
                OR compensation_id IN (
                    SELECT id FROM employee_compensation
                    WHERE company_id IN (
                        SELECT id FROM companies
                        WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
                    )
                )
            )
        """
    )

    op.create_table(
        "payroll_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("payroll_pack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gross_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("deduction_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("employer_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("net_total", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payroll_pack_id"], ["payroll_packs.id"]),
        sa.ForeignKeyConstraint(["currency_id"], ["currencies.id"]),
        sa.UniqueConstraint("branch_id", "period_start", "period_end", name="uq_payroll_run_branch_period"),
        sa.CheckConstraint("status IN ('DRAFT', 'APPROVED')", name="ck_payroll_run_status"),
    )
    op.create_index("ix_payroll_runs_company_id", "payroll_runs", ["company_id"])
    op.create_index("ix_payroll_runs_branch_id", "payroll_runs", ["branch_id"])
    op.create_index("ix_payroll_runs_company_period", "payroll_runs", ["company_id", "period_start"])
    _rls("payroll_runs")

    op.create_table(
        "payroll_payslips",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("compensation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_name", sa.String(255), nullable=False),
        sa.Column("employee_number", sa.String(50), nullable=False),
        sa.Column("gross", sa.Numeric(18, 2), nullable=False),
        sa.Column("basic", sa.Numeric(18, 2), nullable=True),
        sa.Column("employee_deductions", sa.Numeric(18, 2), nullable=False),
        sa.Column("employer_contributions", sa.Numeric(18, 2), nullable=False),
        sa.Column("net", sa.Numeric(18, 2), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["payroll_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["compensation_id"], ["employee_compensation.id"]),
        sa.UniqueConstraint("run_id", "employee_id", name="uq_payroll_payslip_employee"),
    )
    op.create_index("ix_payroll_payslips_company_id", "payroll_payslips", ["company_id"])
    op.create_index("ix_payroll_payslips_run_id", "payroll_payslips", ["run_id"])
    op.create_index("ix_payroll_payslips_employee_id", "payroll_payslips", ["employee_id"])
    _rls("payroll_payslips")

    op.create_table(
        "payroll_payslip_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payslip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("party", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payslip_id"], ["payroll_payslips.id"], ondelete="CASCADE"),
        sa.CheckConstraint("party IN ('EMPLOYEE', 'EMPLOYER')", name="ck_payslip_line_party"),
        sa.CheckConstraint("kind IN ('EARNING', 'DEDUCTION', 'EMPLOYER')", name="ck_payslip_line_kind"),
    )
    op.create_index("ix_payroll_payslip_lines_company_id", "payroll_payslip_lines", ["company_id"])
    op.create_index("ix_payroll_payslip_lines_payslip_id", "payroll_payslip_lines", ["payslip_id"])
    _rls("payroll_payslip_lines")


def downgrade() -> None:
    for table in [
        "payroll_payslip_lines",
        "payroll_payslips",
        "payroll_runs",
        "employee_pay_lines",
        "employee_compensation",
        "company_payroll_settings",
    ]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
    op.drop_table("payroll_pack_constants")
    op.drop_table("payroll_pack_bands")
    op.drop_table("payroll_pack_components")
    op.drop_table("payroll_packs")
