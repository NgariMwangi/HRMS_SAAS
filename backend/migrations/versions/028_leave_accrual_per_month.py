"""leave type monthly accrual rate

Revision ID: 028_leave_accrual_per_month
Revises: 027_leave_balances
Create Date: 2026-09-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028_leave_accrual_per_month"
down_revision: Union[str, Sequence[str], None] = "027_leave_balances"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leave_types",
        sa.Column("accrual_per_month", sa.Numeric(6, 2), nullable=False, server_default="0"),
    )
    op.execute(
        """
        UPDATE leave_types
        SET accrual_per_month = ROUND(days / 12, 2)
        WHERE accrued IS TRUE AND days > 0
        """
    )


def downgrade() -> None:
    op.drop_column("leave_types", "accrual_per_month")
