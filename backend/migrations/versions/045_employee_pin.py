"""Add optional employee PIN number."""
from alembic import op
import sqlalchemy as sa

revision = "045_employee_pin"
down_revision = "044_simple_appraisals"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("employees", sa.Column("pin_number", sa.String(40), nullable=True))


def downgrade():
    op.drop_column("employees", "pin_number")
