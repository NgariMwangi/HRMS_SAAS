"""Consultants, overtime and payment history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "049_workforce_payments"
down_revision = "048_employee_bank"
branch_labels = None
depends_on = None


def scope():
    return [sa.Column("id", sa.UUID(), primary_key=True),
            sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("company_id", sa.UUID(), sa.ForeignKey("companies.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def fk(name, table, nullable=False):
    return sa.Column(name, sa.UUID(), sa.ForeignKey(table + ".id"), nullable=nullable)


def text(name, size=None, nullable=True):
    return sa.Column(name, sa.String(size) if size else sa.Text(), nullable=nullable)


def amount(name, precision=18, scale=2):
    return sa.Column(name, sa.Numeric(precision, scale), nullable=False)


def upgrade():
    op.create_table("consultants", *scope(), fk("branch_id", "branches"),
        text("consultant_number", 50, False), text("first_name", 100, False), text("last_name", 100, False),
        text("other_names", 150), text("email", 255), text("phone", 50), text("id_number", 40), text("pin_number", 40),
        text("bank_name", 100), text("bank_branch", 100), text("bank_account_number", 50), text("bank_code", 20),
        sa.Column("start_date", sa.Date(), nullable=False), sa.Column("end_date", sa.Date()),
        amount("withholding_rate", 6, 3), sa.Column("prorate_payroll", sa.Boolean(), nullable=False),
        text("status", 20, False), text("notes"),
        sa.UniqueConstraint("company_id", "consultant_number", name="uq_consultant_number"),
        sa.CheckConstraint("withholding_rate >= 0 AND withholding_rate <= 100", name="ck_consultant_rate"))
    op.create_table("consultant_compensation", *scope(), fk("consultant_id", "consultants"),
        sa.Column("effective_from", sa.Date(), nullable=False), sa.Column("effective_to", sa.Date()),
        amount("monthly_fee"), amount("other_allowances"), text("notes"),
        sa.UniqueConstraint("consultant_id", "effective_from", name="uq_consultant_fee_date"),
        sa.CheckConstraint("monthly_fee >= 0 AND other_allowances >= 0", name="ck_consultant_fee"))
    op.create_table("consultant_pay", *scope(), fk("consultant_id", "consultants"), fk("branch_id", "branches"),
        fk("compensation_id", "consultant_compensation"), fk("currency_id", "currencies"),
        sa.Column("period_start", sa.Date(), nullable=False), sa.Column("period_end", sa.Date(), nullable=False),
        text("recipient_name", 255, False), amount("gross"), amount("withholding_rate", 6, 3), amount("withholding_tax"), amount("net"),
        sa.Column("payable_days", sa.Integer(), nullable=False), text("status", 20, False),
        fk("approved_by_id", "users", True), sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("consultant_id", "period_start", name="uq_consultant_pay_month"),
        sa.CheckConstraint("status IN ('DRAFT', 'APPROVED')", name="ck_consultant_pay_status"),
        sa.CheckConstraint("gross >= 0 AND withholding_tax >= 0 AND net >= 0 AND gross = withholding_tax + net", name="ck_consultant_pay_amounts"))
    op.create_table("overtime_requests", *scope(), fk("employee_id", "employees"),
        sa.Column("worked_dates", JSONB(), nullable=False), amount("days", 8, 4), amount("daily_rate"), amount("amount"),
        sa.Column("payroll_month", sa.Date(), nullable=False), text("reason"), text("status", 20, False),
        fk("submitted_by_id", "users", True), fk("reviewed_by_id", "users", True), sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        text("review_notes"), fk("employee_benefit_id", "employee_benefits", True),
        sa.CheckConstraint("days > 0 AND daily_rate > 0 AND amount > 0", name="ck_overtime_amounts"),
        sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')", name="ck_overtime_status"))
    op.create_table("payment_records", *scope(), fk("payslip_id", "payroll_payslips", True),
        fk("consultant_pay_id", "consultant_pay", True), fk("benefit_id", "employee_benefits", True),
        sa.Column("period_start", sa.Date(), nullable=False), fk("currency_id", "currencies"), text("recipient_name", 255, False),
        amount("amount"), sa.Column("paid_on", sa.Date(), nullable=False), text("method", 20, False),
        text("reference", 100, False), text("note"), text("status", 20, False),
        fk("recorded_by_id", "users", True), fk("voided_by_id", "users", True),
        sa.Column("voided_at", sa.DateTime(timezone=True)), text("void_reason"),
        sa.CheckConstraint("amount > 0", name="ck_payment_amount"),
        sa.CheckConstraint("status IN ('POSTED', 'VOID')", name="ck_payment_status"),
        sa.CheckConstraint("num_nonnulls(payslip_id, consultant_pay_id, benefit_id) = 1", name="ck_payment_target"),
        sa.UniqueConstraint("company_id", "reference", name="uq_payment_reference"))
    for table in ["consultants", "consultant_compensation", "consultant_pay", "overtime_requests", "payment_records"]:
        op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
        op.create_index(f"ix_{table}_company_id", table, ["company_id"])
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        tenant = "current_setting('app.is_platform_admin', true) = 'true' OR tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid"
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({tenant}) WITH CHECK ({tenant})")
        domain = "current_setting('app.is_platform_admin', true) = 'true' OR nullif(current_setting('app.domain_company_id', true), '') IS NULL OR company_id = nullif(current_setting('app.domain_company_id', true), '')::uuid"
        op.execute(f"CREATE POLICY company_domain_scope ON {table} AS RESTRICTIVE USING ({domain}) WITH CHECK ({domain})")


def downgrade():
    for table in ["payment_records", "overtime_requests", "consultant_pay", "consultant_compensation", "consultants"]:
        op.drop_table(table)
