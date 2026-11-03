"""employee personal email and second phone

Revision ID: 008_employee_contact
Revises: 007_other_names
Create Date: 2026-09-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_employee_contact"
down_revision: Union[str, Sequence[str], None] = "007_other_names"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("personal_email", sa.String(length=255), nullable=True))
    op.add_column("employees", sa.Column("other_phone", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "other_phone")
    op.drop_column("employees", "personal_email")
