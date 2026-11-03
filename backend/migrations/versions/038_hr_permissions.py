"""Grant existing built-in roles the new HR permission defaults once.

Revision ID: 038_hr_permissions
Revises: 037_access_roles
"""

from alembic import op
import sqlalchemy as sa

revision = "038_hr_permissions"
down_revision = "037_access_roles"
branch_labels = None
depends_on = None

SELF = {"people.view_own", "documents.view_own", "lifecycle.view_own", "leave.view_own", "attendance.self"}
TEAM = {"people.view_team", "leave.view_team"}
HR = SELF | TEAM | {
    "organization.manage", "people.view_all", "people.manage", "documents.view_all", "documents.manage",
    "lifecycle.view_all", "lifecycle.manage", "leave.view_all", "leave.manage", "attendance.manage",
    "payroll.manage", "audit.view",
}


def upgrade():
    op.execute("SELECT set_config('app.is_platform_admin', 'true', true)")
    for role, grants in {"OWNER": HR, "ADMIN": HR, "HR": HR, "MANAGER": SELF | TEAM, "EMPLOYEE": SELF}.items():
        for permission in sorted(grants):
            op.get_bind().execute(sa.text("""
                INSERT INTO access_role_permissions (id, tenant_id, role_id, permission)
                SELECT gen_random_uuid(), tenant_id, id, :permission FROM access_roles WHERE key = :role
                ON CONFLICT ON CONSTRAINT uq_access_role_permission DO NOTHING
            """), {"role": role, "permission": permission})


def downgrade():
    op.execute("SELECT set_config('app.is_platform_admin', 'true', true)")
    for permission in sorted(HR):
        op.get_bind().execute(sa.text("DELETE FROM access_role_permissions WHERE permission = :permission"), {"permission": permission})
