"""attendance records and employee clock-in device/login link

Revision ID: 030_attendance
Revises: 029_audit_logs
Create Date: 2026-09-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "030_attendance"
down_revision: Union[str, Sequence[str], None] = "029_audit_logs"
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
    op.add_column("employees", sa.Column("clock_device_id", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_users_employee_id",
        "users",
        "employees",
        ["employee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_users_employee_id", "users", ["employee_id"])

    op.create_table(
        "attendance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("work_on", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("source", sa.String(10), nullable=False, server_default="HR"),
        sa.Column("checked_in_at", sa.DateTime(), nullable=True),
        sa.Column("checked_out_at", sa.DateTime(), nullable=True),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("note", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("employee_id", "work_on", name="uq_attendance_employee_day"),
        sa.CheckConstraint("status IN ('PRESENT', 'LATE', 'ABSENT', 'ON_LEAVE')", name="ck_attendance_status"),
        sa.CheckConstraint("source IN ('SELF', 'HR')", name="ck_attendance_source"),
    )
    op.create_index("ix_attendance_records_company_id", "attendance_records", ["company_id"])
    op.create_index("ix_attendance_records_branch_id", "attendance_records", ["branch_id"])
    op.create_index("ix_attendance_records_employee_id", "attendance_records", ["employee_id"])
    op.create_index("ix_attendance_branch_day", "attendance_records", ["branch_id", "work_on"])
    op.execute("ALTER TABLE attendance_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE attendance_records FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_attendance_records ON attendance_records
            USING ({_COMPANY_SCOPE})
            WITH CHECK ({_COMPANY_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_attendance_records ON attendance_records")
    op.drop_index("ix_attendance_branch_day", table_name="attendance_records")
    op.drop_index("ix_attendance_records_employee_id", table_name="attendance_records")
    op.drop_index("ix_attendance_records_branch_id", table_name="attendance_records")
    op.drop_index("ix_attendance_records_company_id", table_name="attendance_records")
    op.drop_table("attendance_records")
    op.drop_constraint("uq_users_employee_id", "users", type_="unique")
    op.drop_constraint("fk_users_employee_id", "users", type_="foreignkey")
    op.drop_column("users", "employee_id")
    op.drop_column("employees", "clock_device_id")
