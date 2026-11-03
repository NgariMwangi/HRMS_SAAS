"""probation type uses existing string; add period end date

Revision ID: 009_employee_period
Revises: 008_employee_contact
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_employee_period"
down_revision: Union[str, Sequence[str], None] = "008_employee_contact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("date_ended", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "date_ended")
