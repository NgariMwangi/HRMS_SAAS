"""Retain closed legacy overtime without inventing a rate or amount."""
from alembic import op

revision = "052_closed_overtime"
down_revision = "051_legacy_import"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_overtime_amounts", "overtime_requests", type_="check")
    op.alter_column("overtime_requests", "daily_rate", nullable=True)
    op.alter_column("overtime_requests", "amount", nullable=True)
    op.create_check_constraint("ck_overtime_amounts", "overtime_requests", "days > 0 AND ((daily_rate IS NOT NULL AND amount IS NOT NULL AND daily_rate > 0 AND amount > 0) OR (status IN ('REJECTED', 'CANCELLED') AND daily_rate IS NULL AND amount IS NULL))")


def downgrade():
    # NOT NULL deliberately fails if imported records still have unknown rates;
    # a downgrade must never silently delete those historical records.
    op.drop_constraint("ck_overtime_amounts", "overtime_requests", type_="check")
    op.alter_column("overtime_requests", "daily_rate", nullable=False)
    op.alter_column("overtime_requests", "amount", nullable=False)
    op.create_check_constraint("ck_overtime_amounts", "overtime_requests", "days > 0 AND daily_rate > 0 AND amount > 0")
