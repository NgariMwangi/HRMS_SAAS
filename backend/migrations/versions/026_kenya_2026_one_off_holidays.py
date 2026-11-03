"""kenya 2026 one-off public holidays

Revision ID: 026_kenya_2026_one_off_holidays
Revises: 025_kenya_branch_holidays
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op

revision: str = "026_kenya_2026_one_off_holidays"
down_revision: Union[str, Sequence[str], None] = "025_kenya_branch_holidays"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO public_holidays (id, company_id, country_id, name, kind, observed_on)
        SELECT gen_random_uuid(), kenya.company_id, kenya.country_id, holiday.name, 'ONCE', holiday.observed_on
        FROM (
            SELECT DISTINCT b.company_id, c.id AS country_id
            FROM branches b
            JOIN countries c ON c.id = b.country_id
            WHERE c.code = 'KE'
        ) kenya
        CROSS JOIN (
            VALUES
                ('Idd-ul-Fitr', DATE '2026-03-20'),
                ('Good Friday', DATE '2026-04-03'),
                ('Easter Monday', DATE '2026-04-06'),
                ('Idd-ul-Azha', DATE '2026-05-27')
        ) AS holiday(name, observed_on)
        WHERE NOT EXISTS (
            SELECT 1
            FROM public_holidays existing
            WHERE existing.company_id = kenya.company_id
              AND (
                (existing.kind = 'ONCE' AND existing.observed_on = holiday.observed_on)
                OR lower(existing.name) = lower(holiday.name)
              )
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM public_holidays
        WHERE kind = 'ONCE'
          AND observed_on IN (DATE '2026-03-20', DATE '2026-04-03', DATE '2026-04-06', DATE '2026-05-27')
          AND name IN ('Idd-ul-Fitr', 'Good Friday', 'Easter Monday', 'Idd-ul-Azha')
        """
    )
