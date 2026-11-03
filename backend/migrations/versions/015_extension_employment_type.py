"""store employment type on period extensions

Revision ID: 015_extension_employment_type
Revises: 014_period_extension
Create Date: 2026-09-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_extension_employment_type"
down_revision: Union[str, Sequence[str], None] = "014_period_extension"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employee_lifecycle_events", sa.Column("employment_type", sa.String(length=30), nullable=True))
    op.execute(
        """
        UPDATE employee_lifecycle_events AS event
        SET employment_type = employee.employment_type
        FROM employees AS employee
        WHERE event.employee_id = employee.id
          AND event.event_type = 'EXTENDED'
        """
    )


def downgrade() -> None:
    op.drop_column("employee_lifecycle_events", "employment_type")
