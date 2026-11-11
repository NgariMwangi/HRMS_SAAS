"""Preserve the branch and currency of an overtime request."""
from alembic import op
import sqlalchemy as sa

revision = "050_overtime_currency"
down_revision = "049_workforce_payments"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("overtime_requests", sa.Column("branch_id", sa.UUID(), sa.ForeignKey("branches.id")))
    op.add_column("overtime_requests", sa.Column("currency_id", sa.UUID(), sa.ForeignKey("currencies.id")))
    op.execute("""UPDATE overtime_requests o SET branch_id=e.branch_id,
        currency_id=COALESCE(b.currency_id,c.default_currency_id)
        FROM employees e JOIN branches b ON b.id=e.branch_id
        JOIN countries c ON c.id=b.country_id WHERE o.employee_id=e.id""")
    op.alter_column("overtime_requests", "branch_id", nullable=False)
    op.alter_column("overtime_requests", "currency_id", nullable=False)


def downgrade():
    op.drop_column("overtime_requests", "currency_id")
    op.drop_column("overtime_requests", "branch_id")
