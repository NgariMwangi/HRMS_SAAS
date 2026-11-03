"""
Idempotent seed for East Africa reference data.

Safe to run twice: existing currency/country codes are left unchanged.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.payroll_packs import seed_payroll_packs
from app.db.session import dispose_engine, get_session_maker
from app.models import Country, Currency, PlatformAdmin

__all__ = ["seed_countries", "seed_payroll_packs", "seed_platform_admin", "main"]

CURRENCIES = [
    {"code": "KES", "name": "Kenyan Shilling", "symbol": "KSh", "decimal_places": 2},
    {"code": "UGX", "name": "Ugandan Shilling", "symbol": "USh", "decimal_places": 0},
    {"code": "TZS", "name": "Tanzanian Shilling", "symbol": "TSh", "decimal_places": 2},
    {"code": "RWF", "name": "Rwandan Franc", "symbol": "FRw", "decimal_places": 0},
]

COUNTRIES = [
    {"code": "KE", "name": "Kenya", "currency_code": "KES", "timezone": "Africa/Nairobi"},
    {"code": "UG", "name": "Uganda", "currency_code": "UGX", "timezone": "Africa/Kampala"},
    {
        "code": "TZ",
        "name": "Tanzania",
        "currency_code": "TZS",
        "timezone": "Africa/Dar_es_Salaam",
    },
    {"code": "RW", "name": "Rwanda", "currency_code": "RWF", "timezone": "Africa/Kigali"},
]


async def seed_countries(session: AsyncSession) -> None:
    currency_by_code: dict[str, Currency] = {}

    for row in CURRENCIES:
        existing = await session.scalar(
            select(Currency).where(Currency.code == row["code"])
        )
        if existing is None:
            existing = Currency(**row)
            session.add(existing)
        currency_by_code[row["code"]] = existing

    await session.flush()

    for row in COUNTRIES:
        existing = await session.scalar(
            select(Country).where(Country.code == row["code"])
        )
        if existing is None:
            session.add(
                Country(
                    code=row["code"],
                    name=row["name"],
                    default_currency_id=currency_by_code[row["currency_code"]].id,
                    default_timezone=row["timezone"],
                )
            )

    await session.flush()


async def seed_platform_admin(session: AsyncSession) -> None:
    settings = get_settings()
    email = settings.platform_admin_email.lower()
    existing = await session.scalar(
        select(PlatformAdmin).where(PlatformAdmin.email == email)
    )
    if existing is not None:
        return
    session.add(
        PlatformAdmin(
            email=email,
            password_hash=hash_password(settings.platform_admin_password),
            full_name=settings.platform_admin_name,
            status="ACTIVE",
        )
    )
    await session.flush()


async def main() -> None:
    maker = get_session_maker()
    async with maker() as session:
        await seed_countries(session)
        await seed_payroll_packs(session)
        await seed_platform_admin(session)
        await session.commit()
        print("Seeded reference data and platform owner (idempotent).")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
