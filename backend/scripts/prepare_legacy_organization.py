"""Prepare legacy organizations without replacing existing workspace identities.

Input is an organization-only JSON snapshot, never database credentials. The
default is a dry run; --apply commits. Source company 1 maps to the supplied
Nexgen company, and source branch 1 maps to the existing head office. Extra
Nexgen branches require an explicit list, so ambiguous instructions cannot
silently create or merge branches.
"""
import argparse
import asyncio
import json
import uuid
from pathlib import Path

from sqlalchemy import func, select, text
from app.api.org import ensure_document_categories
from app.db.session import dispose_engine, get_session_maker
from app.models import Branch, Company, Country, Currency, Tenant, User
from app.services.domains import ensure_automatic
from app.services.holidays import ensure_country_holidays

SOURCE_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "hrms-legacy:37.60.242.201/hrms_kenya1")


def legacy_id(table, identity):
    return uuid.uuid5(SOURCE_NAMESPACE, f"{table}/{identity}")


async def prepare(args):
    source = json.loads(Path(args.source_file).read_text(encoding="utf-8"))
    companies = {row["id"]: row for row in source["companies"]}
    branches = {row["id"]: row for row in source["branches"]}
    if set(companies) != {1, 2} or branches[1]["company_id"] != 1:
        raise ValueError("Unexpected source organization layout")
    wanted = {int(value) for value in args.nexgen_branches.split(",") if value}
    if not wanted.issubset({3, 4}):
        raise ValueError("Only source Nexgen branches 3 (Uganda) and 4 (Tanzania) may be added")
    maker = get_session_maker()
    async with maker() as session:
        async with session.begin():
            await session.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('legacy-hrms-organization', 0))"))
            tenant = await session.get(Tenant, args.tenant_id)
            company = await session.get(Company, args.nexgen_company_id)
            head = await session.get(Branch, args.head_office_id)
            owner = await session.get(User, args.owner_id)
            if tenant is None or company is None or company.tenant_id != tenant.id:
                raise ValueError("The existing Nexgen company must belong to the supplied workspace")
            if head is None or head.company_id != company.id:
                raise ValueError("The existing head office does not belong to Nexgen")
            if owner is None or owner.tenant_id != tenant.id or owner.role != "OWNER":
                raise ValueError("The existing owner identity could not be verified")
            mapping = {"tenant_id": str(tenant.id), "companies": {"1": str(company.id)},
                       "branches": {"1": str(head.id)}, "preserved_owner_id": str(owner.id)}
            wash = companies[2]
            target = await session.scalar(select(Company).where(Company.tenant_id == tenant.id,
                func.lower(Company.name) == wash["name"].strip().lower()))
            if target is None:
                target = Company(id=legacy_id("companies", 2), tenant_id=tenant.id, name=wash["name"],
                    legal_name=wash.get("legal_name"), registration_number=wash.get("registration_number"),
                    email=wash.get("email"), phone=wash.get("phone"), status="ACTIVE" if wash["is_active"] else "INACTIVE")
                session.add(target)
                await session.flush()
                await ensure_automatic(session, target)
                await ensure_document_categories(session, target.id)
            mapping["companies"]["2"] = str(target.id)
            for identity, row in branches.items():
                if identity == 1 or (row["company_id"] == 1 and identity not in wanted):
                    continue
                company_id = uuid.UUID(mapping["companies"][str(row["company_id"])])
                country = await session.scalar(select(Country).where(Country.code == row["country_code"]))
                currency = await session.scalar(select(Currency).where(Currency.code == row["currency_code"])) if row.get("currency_code") else None
                if country is None or (currency is None and country.default_currency_id is None):
                    raise ValueError(f"Country/currency is not configured for source branch {identity}")
                existing = await session.scalar(select(Branch).where(Branch.company_id == company_id,
                    func.lower(Branch.name) == row["name"].strip().lower()))
                if existing is None:
                    existing = Branch(id=legacy_id("branches", identity), company_id=company_id,
                        name=row["name"], code="HQ" if identity == 2 else f"LEGACY-{identity}",
                        country_id=country.id, currency_id=currency.id if currency else country.default_currency_id,
                        timezone=row.get("timezone") or country.default_timezone, status="ACTIVE")
                    session.add(existing)
                    await session.flush()
                elif existing.country_id != country.id:
                    raise ValueError(f"An existing branch has a conflicting country: {identity}")
                await ensure_country_holidays(session, company_id, country)
                mapping["branches"][str(identity)] = str(existing.id)
            mapping["mode"] = "APPLY" if args.apply else "DRY_RUN"
            print(json.dumps(mapping, indent=2))
            if not args.apply:
                await session.rollback()
    await dispose_engine()


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-file", required=True)
    for name in ["tenant-id", "nexgen-company-id", "head-office-id", "owner-id"]:
        parser.add_argument(f"--{name}", type=uuid.UUID, required=True)
    parser.add_argument("--nexgen-branches", default="", help="Explicit source IDs: 3, 4, or 3,4")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(prepare(arguments()))
