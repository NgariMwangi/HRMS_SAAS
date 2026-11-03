"""intern and contract period extensions

Revision ID: 014_period_extension
Revises: 013_suspension_pay
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014_period_extension"
down_revision: Union[str, Sequence[str], None] = "013_suspension_pay"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employee_lifecycle_events", sa.Column("from_date_ended", sa.Date(), nullable=True))
    op.add_column("employee_lifecycle_events", sa.Column("to_date_ended", sa.Date(), nullable=True))
    op.add_column("employee_lifecycle_events", sa.Column("extension_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("employee_lifecycle_events", "extension_days")
    op.drop_column("employee_lifecycle_events", "to_date_ended")
    op.drop_column("employee_lifecycle_events", "from_date_ended")
