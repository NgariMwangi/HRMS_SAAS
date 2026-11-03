"""suspension pay treatment

Revision ID: 013_suspension_pay
Revises: 012_lifecycle_attachments
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_suspension_pay"
down_revision: Union[str, Sequence[str], None] = "012_lifecycle_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("suspension_pay_treatment", sa.String(length=20), nullable=True))
    op.add_column("employees", sa.Column("suspension_pay_deduction_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("employee_lifecycle_events", sa.Column("pay_treatment", sa.String(length=20), nullable=True))
    op.add_column("employee_lifecycle_events", sa.Column("pay_deduction_percent", sa.Numeric(5, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("employee_lifecycle_events", "pay_deduction_percent")
    op.drop_column("employee_lifecycle_events", "pay_treatment")
    op.drop_column("employees", "suspension_pay_deduction_percent")
    op.drop_column("employees", "suspension_pay_treatment")
