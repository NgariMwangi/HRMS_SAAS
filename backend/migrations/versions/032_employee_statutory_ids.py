"""employee ID, NSSF, and SHIF numbers

Revision ID: 032_employee_statutory_ids
Revises: 031_payroll
Create Date: 2026-09-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "032_employee_statutory_ids"
down_revision: Union[str, Sequence[str], None] = "031_payroll"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("id_number", sa.String(length=40), nullable=True))
    op.add_column("employees", sa.Column("nssf_no", sa.String(length=40), nullable=True))
    op.add_column("employees", sa.Column("shif_no", sa.String(length=40), nullable=True))
    op.create_index(
        "uq_employee_id_number_open",
        "employees",
        ["company_id", "id_number"],
        unique=True,
        postgresql_where=sa.text("id_number IS NOT NULL AND status <> 'TERMINATED'"),
    )
    op.create_index(
        "uq_employee_nssf_no_open",
        "employees",
        ["company_id", "nssf_no"],
        unique=True,
        postgresql_where=sa.text("nssf_no IS NOT NULL AND status <> 'TERMINATED'"),
    )
    op.create_index(
        "uq_employee_shif_no_open",
        "employees",
        ["company_id", "shif_no"],
        unique=True,
        postgresql_where=sa.text("shif_no IS NOT NULL AND status <> 'TERMINATED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_employee_shif_no_open", table_name="employees")
    op.drop_index("uq_employee_nssf_no_open", table_name="employees")
    op.drop_index("uq_employee_id_number_open", table_name="employees")
    op.drop_column("employees", "shif_no")
    op.drop_column("employees", "nssf_no")
    op.drop_column("employees", "id_number")
