"""tenant roles and role permissions

Revision ID: 037_access_roles
Revises: 036_employee_benefits
Create Date: 2026-10-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "037_access_roles"
down_revision: Union[str, Sequence[str], None] = "036_employee_benefits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_SCOPE = """
                current_setting('app.is_platform_admin', true) = 'true'
                OR tenant_id = current_setting('app.current_tenant_id', true)::uuid
"""


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_{table} ON {table}
            USING ({_TENANT_SCOPE})
            WITH CHECK ({_TENANT_SCOPE})
        """
    )


def upgrade() -> None:
    op.create_table(
        "access_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(30), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_access_role_key"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_access_role_name"),
    )
    op.create_index("ix_access_roles_tenant_id", "access_roles", ["tenant_id"])
    _rls("access_roles")

    op.create_table(
        "access_role_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["access_roles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("role_id", "permission", name="uq_access_role_permission"),
    )
    op.create_index("ix_access_role_permissions_tenant_id", "access_role_permissions", ["tenant_id"])
    op.create_index("ix_access_role_permissions_role_id", "access_role_permissions", ["role_id"])
    _rls("access_role_permissions")


def downgrade() -> None:
    for table in ["access_role_permissions", "access_roles"]:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
