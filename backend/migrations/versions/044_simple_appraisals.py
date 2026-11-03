"""Simple templates, review setup and independently progressing employee appraisals."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "044_simple_appraisals"
down_revision = "043_company_domains"
branch_labels = None
depends_on = None


def common():
    return [sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.UUID(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False)]


def upgrade():
    op.create_table("appraisal_templates", *common(), sa.Column("name", sa.String(160), nullable=False),
        sa.Column("weighted", sa.Boolean(), nullable=False), sa.Column("criteria", JSONB(), nullable=False))
    op.create_table("appraisal_reviews", *common(), sa.Column("name", sa.String(160), nullable=False),
        *[sa.Column(key, sa.Date(), nullable=False) for key in ("start_date", "end_date", "employee_deadline", "manager_deadline", "acknowledgement_deadline")],
        sa.Column("template_id", sa.UUID(), sa.ForeignKey("appraisal_templates.id"), nullable=False),
        sa.Column("template_snapshot", JSONB(), nullable=False), sa.Column("preparation", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.CheckConstraint("start_date <= end_date", name="ck_simple_review_period"),
        sa.CheckConstraint("end_date <= employee_deadline AND employee_deadline <= manager_deadline AND manager_deadline <= acknowledgement_deadline", name="ck_simple_review_deadlines"),
        sa.CheckConstraint("preparation IN ('HR','MANAGER')", name="ck_simple_preparation"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','COMPLETED')", name="ck_simple_review_status"))
    op.create_table("employee_appraisals", *common(),
        sa.Column("review_id", sa.UUID(), sa.ForeignKey("appraisal_reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employee_id", sa.UUID(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manager_id", sa.UUID(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("preparation_ready", sa.Boolean(), nullable=False),
        *[sa.Column(key, JSONB(), nullable=False) for key in ("context", "criteria", "self_review", "manager_review", "discussion", "acknowledgement", "result", "history")],
        sa.UniqueConstraint("review_id", "employee_id", name="uq_simple_appraisal_employee"),
        sa.CheckConstraint("employee_id <> manager_id", name="ck_simple_appraiser_not_self"),
        sa.CheckConstraint("version >= 1", name="ck_simple_appraisal_version"),
        sa.CheckConstraint("status IN ('PREPARATION','SELF_REVIEW','MANAGER_REVIEW','DISCUSSION','HR_REVIEW','ACKNOWLEDGEMENT','COMPLETED')", name="ck_simple_appraisal_status"))
    for table in ("appraisal_templates", "appraisal_reviews", "employee_appraisals"):
        for column in ("tenant_id", "company_id"):
            op.create_index(f"ix_{table}_{column}", table, [column])
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        scope = "current_setting('app.is_platform_admin', true) = 'true' OR tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid"
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING ({scope}) WITH CHECK ({scope})")
        company = "current_setting('app.is_platform_admin', true) = 'true' OR nullif(current_setting('app.domain_company_id', true), '') IS NULL OR company_id = nullif(current_setting('app.domain_company_id', true), '')::uuid"
        op.execute(f"CREATE POLICY company_domain_scope ON {table} AS RESTRICTIVE USING ({company}) WITH CHECK ({company})")
    for column in ("review_id", "employee_id", "manager_id"):
        op.create_index(f"ix_employee_appraisals_{column}", "employee_appraisals", [column])


def downgrade():
    for table in ("employee_appraisals", "appraisal_reviews", "appraisal_templates"):
        op.drop_table(table)
