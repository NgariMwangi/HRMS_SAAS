"""Recruitment workflow and role grants."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "041_recruitment"
down_revision = "040_employee_portal"
branch_labels = None
depends_on = None


def fk(name, table, nullable=True, ondelete="SET NULL", **kwargs):
    return sa.Column(name, sa.UUID(), sa.ForeignKey(f"{table}.id", ondelete=ondelete), nullable=nullable, **kwargs)


def create(name, *columns):
    op.create_table(name, sa.Column("id", sa.UUID(), primary_key=True),
        fk("tenant_id", "tenants", False, "CASCADE"), fk("company_id", "companies", False, "CASCADE"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False), *columns)
    for column in ("tenant_id", "company_id"):
        op.create_index(f"ix_{name}_{column}", name, [column])
    op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
    scope = "current_setting('app.is_platform_admin', true) = 'true' OR tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid"
    op.execute(f"CREATE POLICY tenant_isolation_{name} ON {name} USING ({scope}) WITH CHECK ({scope})")


def upgrade():
    create("recruitment_jobs", sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False), sa.Column("requirements", sa.Text(), nullable=False),
        sa.Column("location", sa.String(160), nullable=False), sa.Column("employment_type", sa.String(30), nullable=False),
        sa.Column("openings", sa.Integer(), nullable=False), sa.Column("closing_date", sa.Date()),
        fk("department_id", "departments"), fk("job_title_id", "job_titles"), fk("manager_id", "employees"),
        sa.Column("status", sa.String(20), nullable=False), sa.CheckConstraint("openings > 0", name="ck_recruitment_openings"))
    create("recruitment_candidates", sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False), sa.Column("email", sa.String(254), nullable=False),
        sa.Column("phone", sa.String(50), nullable=False), sa.Column("source", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False), sa.Column("cv_name", sa.String(255)),
        sa.Column("cv_type", sa.String(100)), sa.Column("cv_data", sa.LargeBinary()), fk("employee_id", "employees"),
        sa.UniqueConstraint("company_id", "email", name="uq_recruitment_candidate_email"))
    create("recruitment_applications", fk("job_id", "recruitment_jobs", False, "CASCADE"),
        fk("candidate_id", "recruitment_candidates", False, "CASCADE"), sa.Column("stage", sa.String(30), nullable=False),
        sa.UniqueConstraint("job_id", "candidate_id", name="uq_recruitment_application"))
    create("recruitment_interviews", fk("application_id", "recruitment_applications", False, "CASCADE"),
        sa.Column("title", sa.String(160), nullable=False), sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False), sa.Column("location", sa.String(255), nullable=False),
        sa.Column("interviewer_ids", JSONB(), nullable=False), sa.Column("feedback", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False))
    create("recruitment_offers", fk("application_id", "recruitment_applications", False, "CASCADE", unique=True),
        sa.Column("salary", sa.Numeric(14, 2), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False), sa.Column("expires_on", sa.Date()),
        sa.Column("terms", sa.Text(), nullable=False), sa.Column("status", sa.String(20), nullable=False))
    create("recruitment_events", fk("application_id", "recruitment_applications", True, "CASCADE"),
        fk("job_id", "recruitment_jobs", False, "CASCADE"), fk("actor_id", "users"),
        sa.Column("action", sa.String(100), nullable=False), sa.Column("note", sa.Text(), nullable=False))
    for table, columns in {"applications": ["job_id", "candidate_id"], "interviews": ["application_id"], "events": ["application_id", "job_id"]}.items():
        for column in columns:
            op.create_index(f"ix_recruitment_{table}_{column}", f"recruitment_{table}", [column])
    op.execute("SELECT set_config('app.is_platform_admin', 'true', true)")
    for permission, roles in {"recruitment.manage": "'OWNER','ADMIN','HR'", "recruitment.view_assigned": "'OWNER','ADMIN','HR','MANAGER'", "recruitment.interview": "'OWNER','ADMIN','HR','MANAGER'"}.items():
        op.get_bind().execute(sa.text(f"""INSERT INTO access_role_permissions (id, tenant_id, role_id, permission)
            SELECT gen_random_uuid(), tenant_id, id, :permission FROM access_roles WHERE key IN ({roles})
            ON CONFLICT ON CONSTRAINT uq_access_role_permission DO NOTHING"""), {"permission": permission})


def downgrade():
    op.execute("SELECT set_config('app.is_platform_admin', 'true', true)")
    op.execute("DELETE FROM access_role_permissions WHERE permission LIKE 'recruitment.%'")
    for table in ("events", "offers", "interviews", "applications", "candidates", "jobs"):
        op.drop_table(f"recruitment_{table}")
