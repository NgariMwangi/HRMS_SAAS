"""employee other names

Revision ID: 007_other_names
Revises: 006_employees
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_other_names"
down_revision: Union[str, Sequence[str], None] = "006_employees"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("other_names", sa.String(length=150), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "other_names")
