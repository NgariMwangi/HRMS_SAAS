"""General reports access for administrative roles; existing grants are preserved."""
from alembic import op
import sqlalchemy as sa
revision = "042_general_reports"
down_revision = "041_recruitment"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT set_config('app.is_platform_admin', 'true', true)")
    op.get_bind().execute(sa.text("""INSERT INTO access_role_permissions (id, tenant_id, role_id, permission)
        SELECT gen_random_uuid(), tenant_id, id, 'reports.view' FROM access_roles
        WHERE key IN ('OWNER', 'ADMIN', 'HR')
        ON CONFLICT ON CONSTRAINT uq_access_role_permission DO NOTHING"""))


def downgrade():
    op.execute("SELECT set_config('app.is_platform_admin', 'true', true)")
    op.execute("DELETE FROM access_role_permissions WHERE permission = 'reports.view'")
