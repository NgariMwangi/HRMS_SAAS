"""voluntary pension on employee compensation

Revision ID: 034_voluntary_pension
Revises: 033_pack_component_min_amount
Create Date: 2026-10-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "034_voluntary_pension"
down_revision: Union[str, Sequence[str], None] = "033_pack_component_min_amount"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employee_compensation",
        sa.Column("voluntary_pension", sa.Numeric(precision=18, scale=2), nullable=True),
    )
    op.add_column(
        "employee_compensation",
        sa.Column("pension_scheme", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employee_compensation", "pension_scheme")
    op.drop_column("employee_compensation", "voluntary_pension")
