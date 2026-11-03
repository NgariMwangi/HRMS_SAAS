"""Versioned KE / UG / TZ statutory tables as data, not calculator code."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Country, PayrollPack, PayrollPackBand, PayrollPackComponent, PayrollPackConstant

D = Decimal


def _percent(
    code,
    name,
    party,
    base,
    percent,
    *,
    floor=None,
    cap=None,
    max_amount=None,
    min_amount=None,
    reduces=False,
    order=0,
):
    return {
        "code": code,
        "name": name,
        "party": party,
        "formula_kind": "PERCENT",
        "base": base,
        "percent": D(percent),
        "floor": D(floor) if floor is not None else None,
        "cap": D(cap) if cap is not None else None,
        "amount": D(max_amount) if max_amount is not None else None,
        "min_amount": D(min_amount) if min_amount is not None else None,
        "relief_key": None,
        "reduces_taxable": reduces,
        "sort_order": order,
        "bands": [],
    }


def _nssf_tier(code, name, party, *, floor=None, cap, max_amount, order, reduces=False):
    return _percent(
        code,
        name,
        party,
        "PENSIONABLE",
        "6",
        floor=floor,
        cap=cap,
        max_amount=max_amount,
        reduces=reduces,
        order=order,
    )


def _paye(code, name, bands, *, relief_key=None, order=90):
    return {
        "code": code,
        "name": name,
        "party": "EMPLOYEE",
        "formula_kind": "PROGRESSIVE_BANDS",
        "base": "TAXABLE",
        "percent": None,
        "floor": None,
        "cap": None,
        "amount": None,
        "min_amount": None,
        "relief_key": relief_key,
        "reduces_taxable": False,
        "sort_order": order,
        "bands": bands,
    }


def _band(from_amount, to_amount, rate, order):
    return {
        "from_amount": D(from_amount),
        "to_amount": D(to_amount) if to_amount is not None else None,
        "rate_percent": D(rate),
        "sort_order": order,
    }


# Gazetted monthly figures stored as pack data so platform can edit them.
# Kenya NSSF: 6% employee + 6% employer on two slices of monthly earnings (max 540 / 5,940).
# Pensionable earnings are gross pay, including cash allowances, capped at the upper limit.
# SHIF is 2.75% of gross with a statutory minimum contribution per month.
# Taxable pay = gross − NSSF − SHIF − housing levy; PAYE runs on that remainder.
# PAYE monthly bands per Finance Act 2023 (from 1 July 2023), less personal relief.
# Pension relief (ITA s.22A, Tax Laws (Amendment) Act 2024, from 27 Dec 2024): employee
# pension contributions (NSSF + voluntary) are deductible up to the lowest of actual,
# 30% of pensionable pay, and 30,000/month. Any voluntary excess is taken after PAYE.
KE_PAYE_BANDS = [
    _band("0", "24000", "10", 0),
    _band("24000", "32333", "25", 1),
    _band("32333", "500000", "30", 2),
    _band("500000", "800000", "32.5", 3),
    _band("800000", None, "35", 4),
]

KE_PACK = {
    "effective_from": date(2025, 2, 1),
    "constants": [
        {"key": "personal_relief", "amount": D("2400")},
        {"key": "pension_relief_cap", "amount": D("30000")},
        {"key": "pension_relief_percent", "amount": D("30")},
    ],
    "components": [
        _nssf_tier("NSSF_I", "NSSF Tier I", "EMPLOYEE", cap="9000", max_amount="540", reduces=True, order=10),
        _nssf_tier("NSSF_I_ER", "NSSF Tier I (employer)", "EMPLOYER", cap="9000", max_amount="540", order=11),
        _nssf_tier(
            "NSSF_II",
            "NSSF Tier II",
            "EMPLOYEE",
            floor="9000",
            cap="108000",
            max_amount="5940",
            reduces=True,
            order=12,
        ),
        _nssf_tier(
            "NSSF_II_ER",
            "NSSF Tier II (employer)",
            "EMPLOYER",
            floor="9000",
            cap="108000",
            max_amount="5940",
            order=13,
        ),
        _percent("SHIF", "SHIF", "EMPLOYEE", "GROSS", "2.75", min_amount="300", reduces=True, order=20),
        _percent("HOUSING", "Housing levy", "EMPLOYEE", "GROSS", "1.5", reduces=True, order=30),
        _percent("HOUSING_ER", "Housing levy (employer)", "EMPLOYER", "GROSS", "1.5", order=31),
        _paye(
            "PAYE",
            "PAYE",
            KE_PAYE_BANDS,
            relief_key="personal_relief",
            order=90,
        ),
    ],
}

def _uganda_nssf_and_paye(bands: list) -> list:
    # NSSF Act: 5% employee + 10% employer of gross, no ceiling.
    # Employee NSSF is not an allowable deduction (ITA s.22(2)(i)); PAYE runs on chargeable employment income.
    return [
        _percent("NSSF", "NSSF", "EMPLOYEE", "GROSS", "5", order=10),
        _percent("NSSF_ER", "NSSF (employer)", "EMPLOYER", "GROSS", "10", order=11),
        _paye("PAYE", "PAYE", bands, order=90),
    ]


UG_BANDS_TO_JUNE_2026 = [
    _band("0", "235000", "0", 0),
    _band("235000", "335000", "10", 1),
    _band("335000", "410000", "20", 2),
    _band("410000", "10000000", "30", 3),
    _band("10000000", None, "40", 4),
]

# URA resident monthly PAYE from 1 July 2026 (Income Tax (Amendment) Act, 2026).
# Nil to 335,000; 20% of the next 75,000; 25% of the next 75,000; 30% to 10m;
# then 30% plus an extra 10% (40%) on the amount above 10m.
UG_BANDS_FROM_JULY_2026 = [
    _band("0", "335000", "0", 0),
    _band("335000", "410000", "20", 1),
    _band("410000", "485000", "25", 2),
    _band("485000", "10000000", "30", 3),
    _band("10000000", None, "40", 4),
]

# Through 30 June 2026 (Income Tax Act 5th Schedule as then in force).
UG_PACK_TO_JUNE_2026 = {
    "effective_from": date(2024, 7, 1),
    "constants": [],
    "components": _uganda_nssf_and_paye(UG_BANDS_TO_JUNE_2026),
}

UG_PACK = {
    "effective_from": date(2026, 7, 1),
    "constants": [],
    "components": _uganda_nssf_and_paye(UG_BANDS_FROM_JULY_2026),
}

TZ_PACK = {
    "effective_from": date(2024, 7, 1),
    "constants": [],
    "components": [
        _percent("NSSF", "NSSF", "EMPLOYEE", "GROSS", "10", reduces=True, order=10),
        _percent("NSSF_ER", "NSSF (employer)", "EMPLOYER", "GROSS", "10", order=11),
        _percent("SDL", "Skills development levy", "EMPLOYER", "GROSS", "4", order=20),
        _percent("WCF", "Workers compensation fund", "EMPLOYER", "GROSS", "0.6", order=21),
        _paye(
            "PAYE",
            "PAYE",
            [
                _band("0", "270000", "0", 0),
                _band("270000", "520000", "8", 1),
                _band("520000", "760000", "20", 2),
                _band("760000", "1000000", "25", 3),
                _band("1000000", None, "30", 4),
            ],
            order=90,
        ),
    ],
}

COUNTRY_PACKS = {"KE": KE_PACK, "UG": UG_PACK, "TZ": TZ_PACK}

_PACK_LOAD = (
    selectinload(PayrollPack.components).selectinload(PayrollPackComponent.bands),
    selectinload(PayrollPack.constants),
)


def _kenya_pack_is_current(pack: PayrollPack) -> bool:
    by_code = {item.code: item for item in pack.components}
    nssf = "NSSF_I" in by_code and "NSSF_II" in by_code
    shif = by_code.get("SHIF")
    housing = by_code.get("HOUSING")
    constants = {row.key for row in pack.constants}
    return bool(
        nssf
        and {"pension_relief_cap", "pension_relief_percent"} <= constants
        and shif is not None
        and shif.reduces_taxable
        and shif.min_amount is not None
        and housing is not None
        and housing.reduces_taxable
        and _paye_bands_match(pack, KE_PAYE_BANDS)
    )


def _uganda_nssf_is_current(pack: PayrollPack) -> bool:
    by_code = {item.code: item for item in pack.components}
    nssf = by_code.get("NSSF")
    employer = by_code.get("NSSF_ER")
    if nssf is None or employer is None:
        return False
    if nssf.percent != D("5") or nssf.reduces_taxable:
        return False
    return employer.percent == D("10")


def _paye_bands_match(pack: PayrollPack, expected: list) -> bool:
    paye = next((item for item in pack.components if item.code == "PAYE"), None)
    if paye is None:
        return False
    bands = sorted(paye.bands, key=lambda row: row.sort_order)
    if len(bands) != len(expected):
        return False
    for row, spec in zip(bands, expected, strict=True):
        if row.from_amount != spec["from_amount"] or row.to_amount != spec["to_amount"]:
            return False
        if row.rate_percent != spec["rate_percent"]:
            return False
    return True


def _uganda_legacy_is_current(pack: PayrollPack) -> bool:
    return (
        pack.effective_from < date(2026, 7, 1)
        and _uganda_nssf_is_current(pack)
        and _paye_bands_match(pack, UG_BANDS_TO_JUNE_2026)
    )


def _uganda_pack_is_current(pack: PayrollPack) -> bool:
    return (
        pack.effective_from >= date(2026, 7, 1)
        and _uganda_nssf_is_current(pack)
        and _paye_bands_match(pack, UG_BANDS_FROM_JULY_2026)
    )


async def _write_pack(session: AsyncSession, country_id, spec: dict, *, version: int) -> None:
    pack = PayrollPack(
        country_id=country_id,
        version=version,
        effective_from=spec["effective_from"],
        status="PUBLISHED",
    )
    session.add(pack)
    await session.flush()
    for const in spec["constants"]:
        session.add(PayrollPackConstant(pack_id=pack.id, key=const["key"], amount=const["amount"]))
    for item in spec["components"]:
        component = PayrollPackComponent(
            pack_id=pack.id,
            code=item["code"],
            name=item["name"],
            party=item["party"],
            formula_kind=item["formula_kind"],
            base=item["base"],
            percent=item["percent"],
            cap=item["cap"],
            floor=item["floor"],
            amount=item["amount"],
            min_amount=item["min_amount"],
            relief_key=item["relief_key"],
            reduces_taxable=item["reduces_taxable"],
            sort_order=item["sort_order"],
        )
        session.add(component)
        await session.flush()
        for band in item["bands"]:
            session.add(
                PayrollPackBand(
                    component_id=component.id,
                    sort_order=band["sort_order"],
                    from_amount=band["from_amount"],
                    to_amount=band["to_amount"],
                    rate_percent=band["rate_percent"],
                )
            )


async def seed_payroll_packs(session: AsyncSession) -> None:
    countries = {
        row.code: row
        for row in (
            await session.scalars(select(Country).where(Country.code.in_(list(COUNTRY_PACKS))))
        ).all()
    }
    for code, spec in COUNTRY_PACKS.items():
        country = countries.get(code)
        if country is None:
            continue
        packs = list(
            (
                await session.scalars(
                    select(PayrollPack)
                    .options(*_PACK_LOAD)
                    .where(PayrollPack.country_id == country.id)
                    .order_by(PayrollPack.version)
                )
            ).all()
        )
        if not packs:
            if code == "UG":
                await _write_pack(session, country.id, UG_PACK_TO_JUNE_2026, version=1)
                await _write_pack(session, country.id, UG_PACK, version=2)
            else:
                await _write_pack(session, country.id, spec, version=1)
        elif code == "KE" and not any(_kenya_pack_is_current(row) for row in packs):
            await _write_pack(session, country.id, spec, version=packs[-1].version + 1)
        elif code == "UG":
            next_version = packs[-1].version + 1
            if not any(_uganda_legacy_is_current(row) for row in packs):
                await _write_pack(session, country.id, UG_PACK_TO_JUNE_2026, version=next_version)
                next_version += 1
            if not any(_uganda_pack_is_current(row) for row in packs):
                await _write_pack(session, country.id, UG_PACK, version=next_version)
    await session.flush()
