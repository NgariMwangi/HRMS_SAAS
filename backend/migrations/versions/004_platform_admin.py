"""platform admins + RLS bypass for the system owner

Revision ID: 004_platform_admin
Revises: 003_users_trial
Create Date: 2026-09-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_platform_admin"
down_revision: Union[str, Sequence[str], None] = "003_users_trial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_admins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="ACTIVE"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.UniqueConstraint("email"),
    )

    op.execute("DROP POLICY IF EXISTS tenant_isolation_companies ON companies")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_branches ON branches")
    op.execute(
        """
        CREATE POLICY tenant_isolation_companies ON companies
            USING (
                current_setting('app.is_platform_admin', true) = 'true'
                OR tenant_id = current_setting('app.current_tenant_id', true)::uuid
            )
            WITH CHECK (
                current_setting('app.is_platform_admin', true) = 'true'
                OR tenant_id = current_setting('app.current_tenant_id', true)::uuid
            )
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_branches ON branches
            USING (
                current_setting('app.is_platform_admin', true) = 'true'
                OR company_id IN (
                    SELECT id FROM companies
                    WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
            )
            WITH CHECK (
                current_setting('app.is_platform_admin', true) = 'true'
                OR company_id IN (
                    SELECT id FROM companies
                    WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
            )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_companies ON companies")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_branches ON branches")
    op.execute(
        """
        CREATE POLICY tenant_isolation_companies ON companies
            USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_branches ON branches
            USING (
                company_id IN (
                    SELECT id FROM companies
                    WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
            )
            WITH CHECK (
                company_id IN (
                    SELECT id FROM companies
                    WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
            )
        """
    )
    op.drop_table("platform_admins")
