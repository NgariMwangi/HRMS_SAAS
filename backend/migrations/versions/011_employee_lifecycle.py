"""employee lifecycle events and people statuses

Revision ID: 011_employee_lifecycle
Revises: 010_employee_photo
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "011_employee_lifecycle"
down_revision: Union[str, Sequence[str], None] = "010_employee_photo"
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
    op.add_column(
        "employees",
        sa.Column("previous_employee_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_employees_previous_employee_id", "employees", ["previous_employee_id"])
    op.create_foreign_key(
        "fk_employees_previous_employee_id",
        "employees",
        "employees",
        ["previous_employee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        """
        UPDATE employees
        SET status = CASE
            WHEN status = 'INACTIVE' AND date_ended IS NOT NULL THEN 'TERMINATED'
            WHEN status = 'INACTIVE' THEN 'SUSPENDED'
            ELSE status
        END
        """
    )

    op.create_table(
        "employee_lifecycle_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.String(length=80), nullable=True),
        sa.Column("effective_on", sa.Date(), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("from_department_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_department_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("from_job_title_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_job_title_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("from_branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("to_branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("related_employee_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_employee_id"], ["employees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_employee_lifecycle_events_company_id", "employee_lifecycle_events", ["company_id"])
    op.create_index("ix_employee_lifecycle_events_employee_id", "employee_lifecycle_events", ["employee_id"])

    op.execute("ALTER TABLE employee_lifecycle_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE employee_lifecycle_events FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_employee_lifecycle_events ON employee_lifecycle_events
            USING ({_COMPANY_SCOPE})
            WITH CHECK ({_COMPANY_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_employee_lifecycle_events ON employee_lifecycle_events")
    op.execute("ALTER TABLE employee_lifecycle_events NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE employee_lifecycle_events DISABLE ROW LEVEL SECURITY")
    op.drop_table("employee_lifecycle_events")
    op.drop_constraint("fk_employees_previous_employee_id", "employees", type_="foreignkey")
    op.drop_index("ix_employees_previous_employee_id", table_name="employees")
    op.drop_column("employees", "previous_employee_id")
    op.execute("UPDATE employees SET status = 'INACTIVE' WHERE status IN ('SUSPENDED', 'TERMINATED')")
