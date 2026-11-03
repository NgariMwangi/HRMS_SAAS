"""kenya annual holidays for kenya branches

Revision ID: 025_kenya_branch_holidays
Revises: 024_public_holidays
Create Date: 2026-09-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "025_kenya_branch_holidays"
down_revision: Union[str, Sequence[str], None] = "024_public_holidays"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "public_holidays",
        sa.Column("country_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_public_holidays_country_id",
        "public_holidays",
        "countries",
        ["country_id"],
        ["id"],
    )
    op.create_index("ix_public_holidays_country_id", "public_holidays", ["country_id"])
    op.execute(
        """
        UPDATE public_holidays AS holiday
        SET country_id = kenya.id
        FROM countries AS kenya
        WHERE kenya.code = 'KE'
          AND holiday.country_id IS NULL
          AND holiday.kind = 'YEARLY'
          AND (
            (holiday.month, holiday.day) IN (
              (1, 1), (5, 1), (6, 1), (10, 10), (10, 20), (12, 12), (12, 25), (12, 26)
            )
            OR lower(holiday.name) IN (
              'new year''s day', 'labour day', 'madaraka day', 'huduma day',
              'mashujaa day', 'jamhuri day', 'christmas day', 'boxing day'
            )
          )
          AND EXISTS (
            SELECT 1
            FROM branches
            WHERE branches.company_id = holiday.company_id
              AND branches.country_id = kenya.id
          )
        """
    )
    op.execute(
        """
        INSERT INTO public_holidays (id, company_id, country_id, name, kind, month, day)
        SELECT gen_random_uuid(), kenya.company_id, kenya.country_id, holiday.name, 'YEARLY', holiday.month, holiday.day
        FROM (
            SELECT DISTINCT b.company_id, c.id AS country_id
            FROM branches b
            JOIN countries c ON c.id = b.country_id
            WHERE c.code = 'KE'
        ) kenya
        CROSS JOIN (
            VALUES
                ('New Year''s Day', 1, 1),
                ('Labour Day', 5, 1),
                ('Madaraka Day', 6, 1),
                ('Huduma Day', 10, 10),
                ('Mashujaa Day', 10, 20),
                ('Jamhuri Day', 12, 12),
                ('Christmas Day', 12, 25),
                ('Boxing Day', 12, 26)
        ) AS holiday(name, month, day)
        WHERE NOT EXISTS (
            SELECT 1
            FROM public_holidays existing
            WHERE existing.company_id = kenya.company_id
              AND (
                (existing.kind = 'YEARLY' AND existing.month = holiday.month AND existing.day = holiday.day)
                OR lower(existing.name) = lower(holiday.name)
              )
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_public_holidays_country_id", table_name="public_holidays")
    op.drop_constraint("fk_public_holidays_country_id", "public_holidays", type_="foreignkey")
    op.drop_column("public_holidays", "country_id")
