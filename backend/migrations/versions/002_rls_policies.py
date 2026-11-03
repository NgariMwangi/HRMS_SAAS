"""row-level security for tenant isolation

Revision ID: 002_rls
Revises: 001_core
Create Date: 2026-09-09

Every request transaction must:
    SET LOCAL app.current_tenant_id = '<uuid>'
(or SELECT set_config('app.current_tenant_id', '<uuid>', true)).

Auth does not exist yet (Thursday). Today the API sets this from the
trusted X-Tenant-Id header / tenant_id query param. Prove the policies
manually in psql:

    SET app.current_tenant_id = '<tenant-uuid>';
    SELECT * FROM companies;   -- only that tenant's rows
    SELECT * FROM branches;    -- only branches of that tenant's companies

countries and currencies are platform-owned reference data — no RLS,
readable by everyone, writable only via seed / platform-admin (enforced
at the application layer, not RLS).

FORCE ROW LEVEL SECURITY is enabled so the table owner is also subject
to these policies (otherwise owner bypass would hide whether RLS works).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002_rls"
down_revision: Union[str, Sequence[str], None] = "001_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE companies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE companies FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation_companies ON companies
            USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        """
    )

    op.execute("ALTER TABLE branches ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE branches FORCE ROW LEVEL SECURITY")
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


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_branches ON branches")
    op.execute("ALTER TABLE branches NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE branches DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_companies ON companies")
    op.execute("ALTER TABLE companies NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE companies DISABLE ROW LEVEL SECURITY")
