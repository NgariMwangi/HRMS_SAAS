"""employee passport photo

Revision ID: 010_employee_photo
Revises: 009_employee_period
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_employee_photo"
down_revision: Union[str, Sequence[str], None] = "009_employee_period"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("photo_content_type", sa.String(length=80), nullable=True))
    op.add_column("employees", sa.Column("photo_bytes", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "photo_bytes")
    op.drop_column("employees", "photo_content_type")
