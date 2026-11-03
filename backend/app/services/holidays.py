import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Country, PublicHoliday

# Fixed gazetted dates only. Easter and Idd move each year.
ANNUAL_PUBLIC_HOLIDAYS: dict[str, tuple[tuple[str, int, int], ...]] = {
    "KE": (
        ("New Year's Day", 1, 1),
        ("Labour Day", 5, 1),
        ("Madaraka Day", 6, 1),
        ("Huduma Day", 10, 10),
        ("Mashujaa Day", 10, 20),
        ("Jamhuri Day", 12, 12),
        ("Christmas Day", 12, 25),
        ("Boxing Day", 12, 26),
    ),
}

# Gazetted 2026 dates that have already been observed.
ONE_OFF_PUBLIC_HOLIDAYS: dict[str, tuple[tuple[str, date], ...]] = {
    "KE": (
        ("Idd-ul-Fitr", date(2026, 3, 20)),
        ("Good Friday", date(2026, 4, 3)),
        ("Easter Monday", date(2026, 4, 6)),
        ("Idd-ul-Azha", date(2026, 5, 27)),
    ),
}


def annual_holiday_names(country_code: str) -> set[str]:
    return {name for name, _month, _day in ANNUAL_PUBLIC_HOLIDAYS.get(country_code, ())}


def one_off_holiday_names(country_code: str) -> set[str]:
    return {name for name, _on in ONE_OFF_PUBLIC_HOLIDAYS.get(country_code, ())}


async def ensure_country_holidays(
    session: AsyncSession,
    company_id: uuid.UUID,
    country: Country,
) -> None:
    calendar = ANNUAL_PUBLIC_HOLIDAYS.get(country.code, ())
    one_offs = ONE_OFF_PUBLIC_HOLIDAYS.get(country.code, ())
    if not calendar and not one_offs:
        return
    rows = list(
        (await session.scalars(select(PublicHoliday).where(PublicHoliday.company_id == company_id))).all()
    )
    taken_dates = {(row.month, row.day) for row in rows if row.kind == "YEARLY"}
    taken_once = {row.observed_on for row in rows if row.kind == "ONCE" and row.observed_on is not None}
    taken_names = {row.name.casefold() for row in rows}
    for name, month, day in calendar:
        if (month, day) in taken_dates or name.casefold() in taken_names:
            continue
        session.add(
            PublicHoliday(
                company_id=company_id,
                country_id=country.id,
                name=name,
                kind="YEARLY",
                month=month,
                day=day,
            )
        )
        taken_dates.add((month, day))
        taken_names.add(name.casefold())
    for name, observed_on in one_offs:
        if observed_on in taken_once or name.casefold() in taken_names:
            continue
        session.add(
            PublicHoliday(
                company_id=company_id,
                country_id=country.id,
                name=name,
                kind="ONCE",
                observed_on=observed_on,
            )
        )
        taken_once.add(observed_on)
        taken_names.add(name.casefold())
    await session.flush()
