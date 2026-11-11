"""Persist employee exclusions for each payroll run."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "046_payroll_exclusions"
down_revision = "045_employee_pin"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payroll_runs", sa.Column("excluded_employee_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))


def downgrade():
    op.drop_column("payroll_runs", "excluded_employee_ids")
