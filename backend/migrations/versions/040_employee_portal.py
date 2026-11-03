"""Employee self-service grants and Google account bindings."""
from alembic import op
import sqlalchemy as sa

revision = "040_employee_portal"
down_revision = "039_performance"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("google_subject", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_users_google_subject", "users", ["google_subject"])
    op.create_table("google_login_challenges", sa.Column("digest", sa.String(64), primary_key=True), sa.Column("expires_at", sa.DateTime(), nullable=False))
    op.create_index("ix_google_login_challenges_expires_at", "google_login_challenges", ["expires_at"])
    op.execute("SELECT set_config('app.is_platform_admin', 'true', true)")
    for permission in ("people.update_own_contact", "payroll.view_own"):
        op.get_bind().execute(sa.text("""
            INSERT INTO access_role_permissions (id, tenant_id, role_id, permission)
            SELECT gen_random_uuid(), tenant_id, id, :permission FROM access_roles
            WHERE key IN ('OWNER', 'ADMIN', 'HR', 'MANAGER', 'EMPLOYEE')
            ON CONFLICT ON CONSTRAINT uq_access_role_permission DO NOTHING
        """), {"permission": permission})


def downgrade():
    op.execute("SELECT set_config('app.is_platform_admin', 'true', true)")
    op.execute("DELETE FROM access_role_permissions WHERE permission IN ('people.update_own_contact', 'payroll.view_own')")
    op.drop_table("google_login_challenges")
    op.drop_constraint("uq_users_google_subject", "users", type_="unique")
    op.drop_column("users", "google_subject")
