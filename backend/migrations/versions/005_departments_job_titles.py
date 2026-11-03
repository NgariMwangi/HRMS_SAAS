"""departments and job titles, tenant-isolated via company

Revision ID: 005_dept_titles
Revises: 004_platform_admin
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_dept_titles"
down_revision: Union[str, Sequence[str], None] = "004_platform_admin"
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
        "departments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.UniqueConstraint("company_id", "name", name="uq_department_name"),
        sa.UniqueConstraint("company_id", "code", name="uq_department_code"),
    )
    op.create_index("ix_departments_company_id", "departments", ["company_id"])

    op.create_table(
        "job_titles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="ACTIVE"
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"]),
        sa.UniqueConstraint("company_id", "name", name="uq_job_title_name"),
        sa.UniqueConstraint("company_id", "code", name="uq_job_title_code"),
    )
    op.create_index("ix_job_titles_company_id", "job_titles", ["company_id"])
    op.create_index("ix_job_titles_department_id", "job_titles", ["department_id"])

    op.execute("ALTER TABLE departments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE departments FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_departments ON departments
            USING ({_COMPANY_SCOPE})
            WITH CHECK ({_COMPANY_SCOPE})
        """
    )

    op.execute("ALTER TABLE job_titles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE job_titles FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_job_titles ON job_titles
            USING ({_COMPANY_SCOPE})
            WITH CHECK ({_COMPANY_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_job_titles ON job_titles")
    op.execute("ALTER TABLE job_titles NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE job_titles DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_departments ON departments")
    op.execute("ALTER TABLE departments NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE departments DISABLE ROW LEVEL SECURITY")
    op.drop_table("job_titles")
    op.drop_table("departments")
