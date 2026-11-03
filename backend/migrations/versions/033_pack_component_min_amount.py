"""minimum contribution on payroll pack components

Revision ID: 033_pack_component_min_amount
Revises: 032_employee_statutory_ids
Create Date: 2026-10-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "033_pack_component_min_amount"
down_revision: Union[str, Sequence[str], None] = "032_employee_statutory_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payroll_pack_components",
        sa.Column("min_amount", sa.Numeric(precision=18, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payroll_pack_components", "min_amount")
