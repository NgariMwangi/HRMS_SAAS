"""Non-statutory deductions: company catalog, per-employee schedules, and per-period amounts."""

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.org import branch_for_company, company_for_tenant
from app.models import (
    DeductionType,
    Employee,
    EmployeeDeduction,
    PayrollPayslip,
    PayrollPayslipLine,
    PayrollRun,
)

CATEGORIES = {"PERSONAL", "COMPANY"}
FREQUENCIES = {"RECURRING", "ONE_OFF"}
STATUSES = {"ACTIVE", "STOPPED"}
ZERO = Decimal("0")


def _bad(detail: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


async def list_types(session: AsyncSession, company_id: uuid.UUID, tenant_id: uuid.UUID) -> list[DeductionType]:
    await company_for_tenant(session, company_id, tenant_id)
    return list(
        (
            await session.scalars(
                select(DeductionType)
                .where(DeductionType.company_id == company_id)
                .order_by(DeductionType.category, DeductionType.name)
            )
        ).all()
    )


async def type_for_tenant(session: AsyncSession, type_id: uuid.UUID, tenant_id: uuid.UUID) -> DeductionType:
    row = await session.get(DeductionType, type_id)
    if row is None:
        raise _bad("Deduction type not found", 404)
    await company_for_tenant(session, row.company_id, tenant_id)
    return row


async def _ensure_unique_name(session: AsyncSession, company_id, name: str, exclude_id=None) -> None:
    stmt = select(DeductionType.id).where(
        DeductionType.company_id == company_id,
        func.lower(DeductionType.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(DeductionType.id != exclude_id)
    if await session.scalar(stmt) is not None:
        raise _bad("A deduction type with this name already exists", status.HTTP_409_CONFLICT)


def _apply_type_fields(row: DeductionType, payload) -> None:
    if payload.category not in CATEGORIES:
        raise _bad("category must be PERSONAL or COMPANY")
    row.name = payload.name.strip()
    row.category = payload.category
    row.default_amount = payload.default_amount
    row.is_active = payload.is_active


async def create_type(session: AsyncSession, tenant_id: uuid.UUID, payload) -> DeductionType:
    await company_for_tenant(session, payload.company_id, tenant_id)
    await _ensure_unique_name(session, payload.company_id, payload.name.strip())
    row = DeductionType(company_id=payload.company_id)
    _apply_type_fields(row, payload)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def update_type(session: AsyncSession, row: DeductionType, payload) -> DeductionType:
    await _ensure_unique_name(session, row.company_id, payload.name.strip(), exclude_id=row.id)
    _apply_type_fields(row, payload)
    await session.flush()
    await session.refresh(row)
    return row


async def delete_type(session: AsyncSession, row: DeductionType) -> None:
    used = await session.scalar(
        select(EmployeeDeduction.id).where(EmployeeDeduction.deduction_type_id == row.id).limit(1)
    )
    if used is not None:
        raise _bad(
            "This type is assigned to employees. Deactivate it instead of deleting.",
            status.HTTP_409_CONFLICT,
        )
    await session.delete(row)
    await session.flush()


async def _enrolled_ids(session: AsyncSession, row: DeductionType) -> set[uuid.UUID]:
    return set(
        (
            await session.scalars(
                select(EmployeeDeduction.employee_id).where(
                    EmployeeDeduction.deduction_type_id == row.id,
                    EmployeeDeduction.frequency == "RECURRING",
                    EmployeeDeduction.status == "ACTIVE",
                )
            )
        ).all()
    )


async def _active_people(session: AsyncSession, row: DeductionType, branch_id) -> list[Employee]:
    stmt = select(Employee).where(Employee.company_id == row.company_id, Employee.status == "ACTIVE")
    if branch_id is not None:
        await branch_for_company(session, branch_id, row.company_id)
        stmt = stmt.where(Employee.branch_id == branch_id)
    return list((await session.scalars(stmt.order_by(Employee.first_name, Employee.last_name))).all())


async def enrol_candidates(session: AsyncSession, row: DeductionType, branch_id) -> list[dict]:
    people = await _active_people(session, row, branch_id)
    enrolled = await _enrolled_ids(session, row)
    return [
        {
            "employee_id": person.id,
            "name": " ".join(part for part in (person.first_name, person.other_names, person.last_name) if part),
            "employee_number": person.employee_number,
            "branch_id": person.branch_id,
            "enrolled": person.id in enrolled,
        }
        for person in people
    ]


async def enrol_employees(session: AsyncSession, row: DeductionType, payload) -> dict:
    if not row.is_active:
        raise _bad("Activate this deduction type before enrolling employees")
    amount = payload.amount or row.default_amount
    if amount is None:
        raise _bad("Enter an amount or set a default amount on the deduction type")
    people = [person.id for person in await _active_people(session, row, payload.branch_id)]
    if payload.employee_ids is not None:
        chosen = set(payload.employee_ids)
        people = [employee_id for employee_id in people if employee_id in chosen]
        if not people:
            raise _bad("Select at least one active employee to enrol")
    enrolled_ids = await _enrolled_ids(session, row)
    added = 0
    for employee_id in people:
        if employee_id in enrolled_ids:
            continue
        session.add(
            EmployeeDeduction(
                company_id=row.company_id,
                employee_id=employee_id,
                deduction_type_id=row.id,
                frequency="RECURRING",
                amount=amount,
                start_date=payload.start_date,
                status="ACTIVE",
            )
        )
        added += 1
    await session.flush()
    return {"enrolled": added, "already_enrolled": len(people) - added}


async def recovered_amounts(session: AsyncSession, deduction_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    """Amounts already taken in approved payroll runs, per employee deduction."""
    if not deduction_ids:
        return {}
    rows = await session.execute(
        select(PayrollPayslipLine.employee_deduction_id, func.sum(PayrollPayslipLine.amount))
        .join(PayrollPayslip, PayrollPayslip.id == PayrollPayslipLine.payslip_id)
        .join(PayrollRun, PayrollRun.id == PayrollPayslip.run_id)
        .where(
            PayrollRun.status == "APPROVED",
            PayrollPayslipLine.employee_deduction_id.in_(deduction_ids),
        )
        .group_by(PayrollPayslipLine.employee_deduction_id)
    )
    return {row[0]: Decimal(row[1]) for row in rows.all()}


def _limit(row: EmployeeDeduction) -> Decimal | None:
    if row.frequency == "ONE_OFF":
        return row.amount
    return row.total_amount


def deduction_to_read(row: EmployeeDeduction, recovered: Decimal) -> dict:
    limit = _limit(row)
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "deduction_type_id": row.deduction_type_id,
        "type_name": row.deduction_type.name,
        "category": row.deduction_type.category,
        "frequency": row.frequency,
        "amount": row.amount,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "total_amount": row.total_amount,
        "reference": row.reference,
        "status": row.status,
        "recovered": recovered,
        "balance": None if limit is None else max(ZERO, limit - recovered),
        "created_at": row.created_at,
    }


async def _load_deduction(session: AsyncSession, deduction_id) -> EmployeeDeduction | None:
    return await session.scalar(
        select(EmployeeDeduction)
        .options(selectinload(EmployeeDeduction.deduction_type))
        .where(EmployeeDeduction.id == deduction_id)
        .execution_options(populate_existing=True)
    )


async def list_employee_deductions(session: AsyncSession, employee: Employee) -> list[dict]:
    rows = list(
        (
            await session.scalars(
                select(EmployeeDeduction)
                .options(selectinload(EmployeeDeduction.deduction_type))
                .where(EmployeeDeduction.employee_id == employee.id)
                .order_by(EmployeeDeduction.status, EmployeeDeduction.start_date.desc())
            )
        ).all()
    )
    recovered = await recovered_amounts(session, [row.id for row in rows])
    return [deduction_to_read(row, recovered.get(row.id, ZERO)) for row in rows]


async def _apply_deduction_fields(
    session: AsyncSession, employee: Employee, row: EmployeeDeduction, payload, *, creating: bool
) -> None:
    if payload.frequency not in FREQUENCIES:
        raise _bad("frequency must be RECURRING or ONE_OFF")
    if payload.status not in STATUSES:
        raise _bad("status must be ACTIVE or STOPPED")
    kind = await session.get(DeductionType, payload.deduction_type_id)
    if kind is None or kind.company_id != employee.company_id:
        raise _bad("Deduction type not found for this company")
    if creating and not kind.is_active:
        raise _bad("This deduction type is inactive")
    recurring = payload.frequency == "RECURRING"
    end_date = payload.end_date if recurring else None
    if end_date is not None and end_date < payload.start_date:
        raise _bad("end_date must be on or after start_date")
    row.deduction_type_id = kind.id
    row.frequency = payload.frequency
    row.amount = payload.amount
    row.start_date = payload.start_date
    row.end_date = end_date
    row.total_amount = payload.total_amount if recurring else None
    row.reference = (payload.reference or "").strip() or None
    row.status = payload.status


async def add_employee_deduction(session: AsyncSession, employee: Employee, payload) -> dict:
    row = EmployeeDeduction(company_id=employee.company_id, employee_id=employee.id)
    await _apply_deduction_fields(session, employee, row, payload, creating=True)
    session.add(row)
    await session.flush()
    loaded = await _load_deduction(session, row.id)
    assert loaded is not None
    return deduction_to_read(loaded, ZERO)


async def _deduction_for_employee(session: AsyncSession, employee: Employee, deduction_id) -> EmployeeDeduction:
    row = await _load_deduction(session, deduction_id)
    if row is None or row.employee_id != employee.id:
        raise _bad("Deduction not found", 404)
    return row


async def update_employee_deduction(session: AsyncSession, employee: Employee, deduction_id, payload) -> dict:
    row = await _deduction_for_employee(session, employee, deduction_id)
    await _apply_deduction_fields(session, employee, row, payload, creating=False)
    await session.flush()
    loaded = await _load_deduction(session, row.id)
    assert loaded is not None
    recovered = await recovered_amounts(session, [loaded.id])
    return deduction_to_read(loaded, recovered.get(loaded.id, ZERO))


async def delete_employee_deduction(session: AsyncSession, employee: Employee, deduction_id) -> None:
    row = await _deduction_for_employee(session, employee, deduction_id)
    recovered = await recovered_amounts(session, [row.id])
    if recovered.get(row.id, ZERO) > ZERO:
        raise _bad(
            "This deduction is on an approved payroll. Stop it instead of deleting.",
            status.HTTP_409_CONFLICT,
        )
    await session.delete(row)
    await session.flush()


def _period_amount(row: EmployeeDeduction, recovered: Decimal, start: date, end: date) -> Decimal:
    if row.status != "ACTIVE":
        return ZERO
    if row.frequency == "ONE_OFF":
        if not (start <= row.start_date <= end):
            return ZERO
    else:
        if row.start_date > end:
            return ZERO
        if row.end_date is not None and row.end_date < start:
            return ZERO
    limit = _limit(row)
    if limit is None:
        return row.amount
    return max(ZERO, min(row.amount, limit - recovered))


async def deductions_for_period(
    session: AsyncSession,
    employee_ids: list[uuid.UUID],
    period_start: date,
    period_end: date,
) -> dict[uuid.UUID, list[dict]]:
    """Scheduled amounts per employee for one pay period, before any net-pay cap."""
    if not employee_ids:
        return {}
    rows = list(
        (
            await session.scalars(
                select(EmployeeDeduction)
                .options(selectinload(EmployeeDeduction.deduction_type))
                .where(
                    EmployeeDeduction.employee_id.in_(employee_ids),
                    EmployeeDeduction.status == "ACTIVE",
                    EmployeeDeduction.start_date <= period_end,
                )
                .order_by(EmployeeDeduction.start_date, EmployeeDeduction.created_at)
            )
        ).all()
    )
    recovered = await recovered_amounts(session, [row.id for row in rows])
    out: dict[uuid.UUID, list[dict]] = defaultdict(list)
    for row in rows:
        amount = _period_amount(row, recovered.get(row.id, ZERO), period_start, period_end)
        if amount <= ZERO:
            continue
        name = row.deduction_type.name
        if row.reference:
            name = f"{name} ({row.reference})"
        out[row.employee_id].append({"id": row.id, "name": name[:100], "amount": amount})
    return out
