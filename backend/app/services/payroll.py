from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.org import branch_for_company, company_for_tenant
from app.models import (
    Branch,
    CompanyPayrollSettings,
    Country,
    Currency,
    Employee,
    EmployeeCompensation,
    EmployeePayLine,
    PayrollPack,
    PayrollPackBand,
    PayrollPackComponent,
    PayrollPackConstant,
    PayrollPayslip,
    PayrollPayslipLine,
    PayrollRun,
)
from app.services.benefits import benefits_for_period
from app.services.deductions import deductions_for_period
from app.services.payroll_calc import calculate_payslip, money, pack_as_of

FREQUENCIES = {"MONTHLY", "BIWEEKLY", "WEEKLY"}
STRUCTURES = {"GROSS_ONLY", "BASIC_PLUS_ALLOWANCES"}
FORMULAS = {"PROGRESSIVE_BANDS", "PERCENT", "FIXED"}
BASES = {"GROSS", "BASIC", "TAXABLE", "PENSIONABLE"}
PARTIES = {"EMPLOYEE", "EMPLOYER"}


def _bad(detail: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


async def pack_with_parts(session: AsyncSession, pack_id) -> PayrollPack | None:
    return await session.scalar(
        select(PayrollPack)
        .options(
            selectinload(PayrollPack.country),
            selectinload(PayrollPack.components).selectinload(PayrollPackComponent.bands),
            selectinload(PayrollPack.constants),
        )
        .where(PayrollPack.id == pack_id)
    )


def pack_to_read(pack: PayrollPack) -> dict:
    return {
        "id": pack.id,
        "country_id": pack.country_id,
        "country_code": pack.country.code if pack.country is not None else None,
        "version": pack.version,
        "effective_from": pack.effective_from,
        "status": pack.status,
        "created_at": pack.created_at,
        "updated_at": pack.updated_at,
        "components": pack.components,
        "constants": pack.constants,
    }


async def list_packs(session: AsyncSession, country_id=None) -> list[PayrollPack]:
    stmt = (
        select(PayrollPack)
        .options(
            selectinload(PayrollPack.country),
            selectinload(PayrollPack.components).selectinload(PayrollPackComponent.bands),
            selectinload(PayrollPack.constants),
        )
        .order_by(PayrollPack.country_id, PayrollPack.version.desc())
    )
    if country_id is not None:
        stmt = stmt.where(PayrollPack.country_id == country_id)
    return list((await session.scalars(stmt)).all())


async def _next_version(session: AsyncSession, country_id) -> int:
    current = await session.scalar(
        select(PayrollPack.version)
        .where(PayrollPack.country_id == country_id)
        .order_by(PayrollPack.version.desc())
        .limit(1)
    )
    return int(current or 0) + 1


def _copy_pack_contents(source: PayrollPack, target: PayrollPack) -> None:
    for const in source.constants:
        target.constants.append(PayrollPackConstant(key=const.key, amount=const.amount))
    for item in source.components:
        component = PayrollPackComponent(
            code=item.code,
            name=item.name,
            party=item.party,
            formula_kind=item.formula_kind,
            base=item.base,
            percent=item.percent,
            cap=item.cap,
            floor=item.floor,
            amount=item.amount,
            min_amount=item.min_amount,
            relief_key=item.relief_key,
            reduces_taxable=item.reduces_taxable,
            sort_order=item.sort_order,
        )
        for band in item.bands:
            component.bands.append(
                PayrollPackBand(
                    sort_order=band.sort_order,
                    from_amount=band.from_amount,
                    to_amount=band.to_amount,
                    rate_percent=band.rate_percent,
                )
            )
        target.components.append(component)


async def create_pack(session: AsyncSession, country_id, effective_from: date, copy_from_id) -> PayrollPack:
    country = await session.get(Country, country_id)
    if country is None:
        raise _bad("Country not found", 404)
    pack = PayrollPack(
        country_id=country_id,
        version=await _next_version(session, country_id),
        effective_from=effective_from,
        status="DRAFT",
    )
    if copy_from_id is not None:
        source = await pack_with_parts(session, copy_from_id)
        if source is None or source.country_id != country_id:
            raise _bad("Pack to copy was not found")
        _copy_pack_contents(source, pack)
    session.add(pack)
    await session.flush()
    loaded = await pack_with_parts(session, pack.id)
    assert loaded is not None
    return loaded


def _replace_contents(pack: PayrollPack, components, constants) -> None:
    pack.components.clear()
    pack.constants.clear()
    for const in constants:
        pack.constants.append(PayrollPackConstant(key=const.key.strip(), amount=const.amount))
    for item in components:
        if item.party not in PARTIES or item.formula_kind not in FORMULAS or item.base not in BASES:
            raise _bad("Invalid component party, formula, or base")
        component = PayrollPackComponent(
            code=item.code.strip().upper(),
            name=item.name.strip(),
            party=item.party,
            formula_kind=item.formula_kind,
            base=item.base,
            percent=item.percent,
            cap=item.cap,
            floor=item.floor,
            amount=item.amount,
            min_amount=item.min_amount,
            relief_key=item.relief_key,
            reduces_taxable=item.reduces_taxable,
            sort_order=item.sort_order,
        )
        for band in item.bands:
            component.bands.append(
                PayrollPackBand(
                    sort_order=band.sort_order,
                    from_amount=band.from_amount,
                    to_amount=band.to_amount,
                    rate_percent=band.rate_percent,
                )
            )
        pack.components.append(component)


async def update_pack(session: AsyncSession, pack: PayrollPack, payload) -> PayrollPack:
    if pack.status != "DRAFT":
        raise _bad("Published packs cannot be edited. Create a new version.")
    if payload.effective_from is not None:
        pack.effective_from = payload.effective_from
    if payload.components is not None or payload.constants is not None:
        _replace_contents(pack, payload.components or [], payload.constants or [])
    await session.flush()
    loaded = await pack_with_parts(session, pack.id)
    assert loaded is not None
    return loaded


async def publish_pack(session: AsyncSession, pack: PayrollPack) -> PayrollPack:
    if pack.status == "PUBLISHED":
        return pack
    if not pack.components:
        raise _bad("A pack needs at least one component before it can be published")
    pack.status = "PUBLISHED"
    await session.flush()
    loaded = await pack_with_parts(session, pack.id)
    assert loaded is not None
    return loaded


async def settings_for(
    session: AsyncSession,
    company_id,
    tenant_id,
    branch: Branch | None,
) -> dict:
    await company_for_tenant(session, company_id, tenant_id)
    row = await session.scalar(
        select(CompanyPayrollSettings).where(CompanyPayrollSettings.company_id == company_id)
    )
    if row is None:
        row = CompanyPayrollSettings(
            company_id=company_id, frequency="MONTHLY", salary_structure="GROSS_ONLY"
        )
        session.add(row)
        await session.flush()
    country = None
    currency = None
    pack = None
    if branch is not None:
        country = await session.get(Country, branch.country_id)
        if branch.currency_id:
            currency = await session.get(Currency, branch.currency_id)
        elif country is not None and country.default_currency_id:
            currency = await session.get(Currency, country.default_currency_id)
        packs = await list_packs(session, branch.country_id)
        pack = pack_as_of(packs, date.today())
    return {
        "company_id": company_id,
        "frequency": row.frequency,
        "salary_structure": row.salary_structure,
        "country_id": branch.country_id if branch else None,
        "country_code": country.code if country else None,
        "country_name": country.name if country else None,
        "currency_id": currency.id if currency else None,
        "currency_code": currency.code if currency else None,
        "currency_symbol": currency.symbol if currency else None,
        "pack_status": pack.status if pack else None,
        "pack_version": pack.version if pack else None,
        "pack_effective_from": pack.effective_from if pack else None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def save_settings(session: AsyncSession, company_id, tenant_id, frequency: str, structure: str) -> CompanyPayrollSettings:
    await company_for_tenant(session, company_id, tenant_id)
    if frequency not in FREQUENCIES:
        raise _bad("frequency must be MONTHLY, BIWEEKLY, or WEEKLY")
    if structure not in STRUCTURES:
        raise _bad("salary_structure must be GROSS_ONLY or BASIC_PLUS_ALLOWANCES")
    row = await session.scalar(
        select(CompanyPayrollSettings).where(CompanyPayrollSettings.company_id == company_id)
    )
    if row is None:
        row = CompanyPayrollSettings(company_id=company_id)
        session.add(row)
    row.frequency = frequency
    row.salary_structure = structure
    await session.flush()
    return row


def _validate_compensation(structure: str, gross, basic, lines) -> None:
    if structure not in STRUCTURES:
        raise _bad("structure must be GROSS_ONLY or BASIC_PLUS_ALLOWANCES")
    if structure == "GROSS_ONLY":
        if gross is None or Decimal(gross) <= 0:
            raise _bad("gross_amount is required")
        if lines:
            raise _bad("Gross-only salary cannot include allowances")
        if basic is not None:
            raise _bad("Gross-only salary does not use basic_amount")
    else:
        if basic is None or Decimal(basic) <= 0:
            raise _bad("basic_amount is required")
        if gross is not None:
            raise _bad("Gross is calculated from basic plus allowances")


def _apply_pension_fields(row: EmployeeCompensation, payload) -> None:
    amount = payload.voluntary_pension
    if amount is None or Decimal(amount) <= 0:
        row.voluntary_pension = None
        row.pension_scheme = None
        return
    row.voluntary_pension = amount
    scheme = (payload.pension_scheme or "").strip()
    row.pension_scheme = scheme or None


async def list_compensation(session: AsyncSession, employee: Employee) -> list[EmployeeCompensation]:
    return list(
        (
            await session.scalars(
                select(EmployeeCompensation)
                .options(selectinload(EmployeeCompensation.lines))
                .where(EmployeeCompensation.employee_id == employee.id)
                .order_by(EmployeeCompensation.effective_from.desc())
            )
        ).all()
    )


async def add_compensation(session: AsyncSession, employee: Employee, payload) -> EmployeeCompensation:
    branch = await session.get(Branch, employee.branch_id)
    if branch is None:
        raise _bad("Branch not found", 404)
    currency_id = branch.currency_id
    if currency_id is None:
        country = await session.get(Country, branch.country_id)
        currency_id = country.default_currency_id if country else None
    if currency_id is None:
        raise _bad("This branch has no currency")
    _validate_compensation(payload.structure, payload.gross_amount, payload.basic_amount, payload.lines)
    existing = await session.scalar(
        select(EmployeeCompensation).where(
            EmployeeCompensation.employee_id == employee.id,
            EmployeeCompensation.effective_from == payload.effective_from,
        )
    )
    if existing is not None:
        raise _bad("A salary already exists for this effective date", status.HTTP_409_CONFLICT)
    row = EmployeeCompensation(
        company_id=employee.company_id,
        employee_id=employee.id,
        effective_from=payload.effective_from,
        structure=payload.structure,
        gross_amount=payload.gross_amount if payload.structure == "GROSS_ONLY" else None,
        basic_amount=payload.basic_amount if payload.structure == "BASIC_PLUS_ALLOWANCES" else None,
        currency_id=currency_id,
    )
    _apply_pension_fields(row, payload)
    if payload.structure == "BASIC_PLUS_ALLOWANCES":
        for index, line in enumerate(payload.lines):
            row.lines.append(
                EmployeePayLine(
                    kind="ALLOWANCE",
                    name=line.name.strip(),
                    amount=line.amount,
                    sort_order=line.sort_order or index,
                )
            )
    session.add(row)
    await session.flush()
    loaded = await session.scalar(
        select(EmployeeCompensation)
        .options(selectinload(EmployeeCompensation.lines))
        .where(EmployeeCompensation.id == row.id)
    )
    assert loaded is not None
    return loaded


def _apply_pay_fields(row: EmployeeCompensation, payload) -> None:
    row.effective_from = payload.effective_from
    row.structure = payload.structure
    row.gross_amount = payload.gross_amount if payload.structure == "GROSS_ONLY" else None
    row.basic_amount = payload.basic_amount if payload.structure == "BASIC_PLUS_ALLOWANCES" else None
    _apply_pension_fields(row, payload)
    row.lines.clear()
    if payload.structure == "BASIC_PLUS_ALLOWANCES":
        for index, line in enumerate(payload.lines):
            row.lines.append(
                EmployeePayLine(
                    kind="ALLOWANCE",
                    name=line.name.strip(),
                    amount=line.amount,
                    sort_order=line.sort_order or index,
                )
            )


async def update_compensation(
    session: AsyncSession,
    employee: Employee,
    compensation_id,
    payload,
) -> EmployeeCompensation:
    row = await session.scalar(
        select(EmployeeCompensation)
        .options(selectinload(EmployeeCompensation.lines))
        .where(
            EmployeeCompensation.id == compensation_id,
            EmployeeCompensation.employee_id == employee.id,
        )
    )
    if row is None:
        raise _bad("Salary record not found", 404)
    _validate_compensation(payload.structure, payload.gross_amount, payload.basic_amount, payload.lines)
    clash = await session.scalar(
        select(EmployeeCompensation.id).where(
            EmployeeCompensation.employee_id == employee.id,
            EmployeeCompensation.effective_from == payload.effective_from,
            EmployeeCompensation.id != row.id,
        )
    )
    if clash is not None:
        raise _bad("A salary already exists for this effective date", status.HTTP_409_CONFLICT)
    _apply_pay_fields(row, payload)
    await session.flush()
    loaded = await session.scalar(
        select(EmployeeCompensation)
        .options(selectinload(EmployeeCompensation.lines))
        .where(EmployeeCompensation.id == row.id)
    )
    assert loaded is not None
    return loaded


async def compensation_as_of(session: AsyncSession, employee_id, on: date) -> EmployeeCompensation | None:
    return await session.scalar(
        select(EmployeeCompensation)
        .options(selectinload(EmployeeCompensation.lines))
        .where(
            EmployeeCompensation.employee_id == employee_id,
            EmployeeCompensation.effective_from <= on,
        )
        .order_by(EmployeeCompensation.effective_from.desc())
        .limit(1)
    )


def _employee_name(employee: Employee) -> str:
    return " ".join(part for part in (employee.first_name, employee.other_names, employee.last_name) if part)


async def create_run(session: AsyncSession, company_id, tenant_id, branch_id, period_start: date, period_end: date) -> tuple[PayrollRun, int]:
    await company_for_tenant(session, company_id, tenant_id)
    branch = await branch_for_company(session, branch_id, company_id)
    if period_end < period_start:
        raise _bad("period_end must be on or after period_start")
    existing = await session.scalar(
        select(PayrollRun)
        .options(selectinload(PayrollRun.payslips).selectinload(PayrollPayslip.lines))
        .where(
            PayrollRun.branch_id == branch_id,
            PayrollRun.period_start == period_start,
            PayrollRun.period_end == period_end,
        )
    )
    if existing is not None and existing.status != "DRAFT":
        raise _bad("This period is already approved", status.HTTP_409_CONFLICT)
    packs = await list_packs(session, branch.country_id)
    pack = pack_as_of(packs, period_end)
    if pack is None:
        raise _bad("No published payroll pack for this branch country")
    currency_id = branch.currency_id
    country = await session.get(Country, branch.country_id)
    if currency_id is None and country is not None:
        currency_id = country.default_currency_id
    if currency_id is None:
        raise _bad("This branch has no currency")
    currency = await session.get(Currency, currency_id)
    places = currency.decimal_places if currency is not None else 2
    people = list(
        (
            await session.scalars(
                select(Employee).where(
                    Employee.company_id == company_id,
                    Employee.branch_id == branch_id,
                    Employee.status == "ACTIVE",
                )
            )
        ).all()
    )
    if existing is not None:
        for slip in list(existing.payslips):
            await session.delete(slip)
        await session.flush()
        run = existing
        run.payroll_pack_id = pack.id
        run.currency_id = currency_id
        run.status = "DRAFT"
    else:
        run = PayrollRun(
            company_id=company_id,
            branch_id=branch_id,
            period_start=period_start,
            period_end=period_end,
            status="DRAFT",
            payroll_pack_id=pack.id,
            currency_id=currency_id,
        )
        session.add(run)
        await session.flush()
    skipped = 0
    gross_total = Decimal("0")
    deduction_total = Decimal("0")
    employer_total = Decimal("0")
    net_total = Decimal("0")
    people_ids = [person.id for person in people]
    scheduled = await deductions_for_period(session, people_ids, period_start, period_end)
    earned = await benefits_for_period(session, people_ids, period_start, period_end)
    for person in people:
        pay = await compensation_as_of(session, person.id, period_end)
        if pay is None or pay.computed_gross <= 0:
            skipped += 1
            continue
        result = calculate_payslip(
            pack,
            pay,
            places=places,
            other_deductions=scheduled.get(person.id),
            benefits=earned.get(person.id),
        )
        payslip = PayrollPayslip(
            company_id=company_id,
            run_id=run.id,
            employee_id=person.id,
            compensation_id=pay.id,
            employee_name=_employee_name(person),
            employee_number=person.employee_number,
            gross=result["gross"],
            basic=result["basic"],
            employee_deductions=result["employee_deductions"],
            employer_contributions=result["employer_contributions"],
            net=result["net"],
        )
        for line in result["lines"]:
            payslip.lines.append(
                PayrollPayslipLine(
                    company_id=company_id,
                    code=line["code"],
                    name=line["name"],
                    party=line["party"],
                    kind=line["kind"],
                    amount=line["amount"],
                    sort_order=line["sort_order"],
                    employee_deduction_id=line.get("employee_deduction_id"),
                    employee_benefit_id=line.get("employee_benefit_id"),
                )
            )
        session.add(payslip)
        gross_total += result["gross"]
        deduction_total += result["employee_deductions"]
        employer_total += result["employer_contributions"]
        net_total += result["net"]
    run.gross_total = money(gross_total, places)
    run.deduction_total = money(deduction_total, places)
    run.employer_total = money(employer_total, places)
    run.net_total = money(net_total, places)
    await session.flush()
    session.expire(run, ["payslips"])
    return run, skipped


async def load_run(session: AsyncSession, run_id) -> PayrollRun | None:
    return await session.scalar(
        select(PayrollRun)
        .options(
            selectinload(PayrollRun.payslips).selectinload(PayrollPayslip.lines),
        )
        .where(PayrollRun.id == run_id)
    )


async def run_to_read(session: AsyncSession, run: PayrollRun, skipped: int = 0) -> dict:
    pack = await session.get(PayrollPack, run.payroll_pack_id)
    country = None
    if pack is not None:
        country = await session.get(Country, pack.country_id)
    currency = await session.get(Currency, run.currency_id)
    return {
        "id": run.id,
        "company_id": run.company_id,
        "branch_id": run.branch_id,
        "period_start": run.period_start,
        "period_end": run.period_end,
        "status": run.status,
        "payroll_pack_id": run.payroll_pack_id,
        "pack_version": pack.version if pack else None,
        "country_code": country.code if country else None,
        "currency_id": run.currency_id,
        "currency_code": currency.code if currency else None,
        "gross_total": run.gross_total,
        "deduction_total": run.deduction_total,
        "employer_total": run.employer_total,
        "net_total": run.net_total,
        "skipped": skipped,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "payslips": run.payslips,
    }


async def approve_run(session: AsyncSession, run: PayrollRun) -> PayrollRun:
    if run.status == "APPROVED":
        return run
    run.status = "APPROVED"
    await session.flush()
    loaded = await load_run(session, run.id)
    assert loaded is not None
    return loaded
