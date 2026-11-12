"""Company themes and logos; apply the supplied branding to the migrated Nexgen company."""
from alembic import op
import sqlalchemy as sa

revision = "053_company_branding"
down_revision = "052_closed_overtime"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("companies", sa.Column("theme_color", sa.String(7), nullable=False, server_default="#4F46E5"))
    op.add_column("companies", sa.Column("logo_data_url", sa.Text(), nullable=True))
    op.create_check_constraint("ck_company_theme_color", "companies", "theme_color ~ '^#[0-9A-Fa-f]{6}$'")
    from app.services.branding import NEXGEN_LOGO, NEXGEN_COLOR
    op.get_bind().execute(sa.text("SELECT set_config('app.is_platform_admin', 'true', true)"))
    op.get_bind().execute(sa.text("UPDATE companies SET theme_color=:color, logo_data_url=:logo WHERE id=:company AND tenant_id=:tenant"),
        {"color": NEXGEN_COLOR, "logo": NEXGEN_LOGO, "company": "323324db-0fab-46aa-9912-bc9165f8ac52", "tenant": "3373eeb5-77e2-4932-b3e8-c9cda9a8052f"})


def downgrade():
    op.drop_constraint("ck_company_theme_color", "companies", type_="check")
    op.drop_column("companies", "logo_data_url")
    op.drop_column("companies", "theme_color")
