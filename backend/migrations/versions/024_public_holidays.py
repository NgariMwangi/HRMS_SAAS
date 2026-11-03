"""company public holidays

Revision ID: 024_public_holidays
Revises: 023_leave_requests
Create Date: 2026-09-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "024_public_holidays"
down_revision: Union[str, Sequence[str], None] = "023_leave_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COMPANY_SCOPE = """
                current_setting('app.is_platform_admin', true) = 'true'
                OR company_id IN (
                    SELECT id FROM companies
                    WHERE tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
"""


def upgrade() -> None:
    op.create_table(
        "public_holidays",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("day", sa.Integer(), nullable=True),
        sa.Column("observed_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("company_id", "name", name="uq_public_holiday_name"),
        sa.CheckConstraint("kind IN ('YEARLY', 'ONCE')", name="ck_public_holiday_kind"),
        sa.CheckConstraint(
            "(kind = 'YEARLY' AND month IS NOT NULL AND day IS NOT NULL AND observed_on IS NULL)"
            " OR (kind = 'ONCE' AND observed_on IS NOT NULL AND month IS NULL AND day IS NULL)",
            name="ck_public_holiday_shape",
        ),
    )
    op.create_index("ix_public_holidays_company_id", "public_holidays", ["company_id"])
    op.create_index(
        "uq_public_holiday_yearly",
        "public_holidays",
        ["company_id", "month", "day"],
        unique=True,
        postgresql_where=sa.text("kind = 'YEARLY'"),
    )
    op.create_index(
        "uq_public_holiday_once",
        "public_holidays",
        ["company_id", "observed_on"],
        unique=True,
        postgresql_where=sa.text("kind = 'ONCE'"),
    )
    op.execute("ALTER TABLE public_holidays ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public_holidays FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_public_holidays ON public_holidays
            USING ({_COMPANY_SCOPE})
            WITH CHECK ({_COMPANY_SCOPE})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_public_holidays ON public_holidays")
    op.drop_index("uq_public_holiday_once", table_name="public_holidays")
    op.drop_index("uq_public_holiday_yearly", table_name="public_holidays")
    op.drop_index("ix_public_holidays_company_id", table_name="public_holidays")
    op.drop_table("public_holidays")
