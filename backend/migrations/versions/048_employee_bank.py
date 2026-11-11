"""Employee bank information and proration policy."""
from alembic import op
import sqlalchemy as sa

revision = "048_employee_bank"
down_revision = "047_leave_emails"
branch_labels = None
depends_on = None


def upgrade():
    for name, length in [("bank_name", 100), ("bank_branch", 100),
                         ("bank_account_number", 50), ("bank_code", 20), ("swift_code", 20)]:
        op.add_column("employees", sa.Column(name, sa.String(length)))
    op.add_column("employees", sa.Column("prorate_payroll", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    for name in ["prorate_payroll", "swift_code", "bank_code", "bank_account_number", "bank_branch", "bank_name"]:
        op.drop_column("employees", name)
