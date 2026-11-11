"""Benefits: company catalog of extra earnings and per-employee schedules (once or a date range)."""

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.org import company_for_tenant
from app.services.salary_item_types import resolve_type
from app.models import BenefitType, Employee, EmployeeBenefit, PayrollPayslip, PayrollPayslipLine, PayrollRun

FREQUENCIES = {"RECURRING", "ONE_OFF"}
STATUSES = {"ACTIVE", "STOPPED"}
ZERO = Decimal("0")


def _bad(detail: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


async def list_types(session: AsyncSession, company_id: uuid.UUID, tenant_id: uuid.UUID) -> list[BenefitType]:
    await company_for_tenant(session, company_id, tenant_id)
    return list(
        (
            await session.scalars(
                select(BenefitType).where(BenefitType.company_id == company_id).order_by(BenefitType.name)
            )
        ).all()
    )


async def type_for_tenant(session: AsyncSession, type_id: uuid.UUID, tenant_id: uuid.UUID) -> BenefitType:
    row = await session.get(BenefitType, type_id)
    if row is None:
        raise _bad("Benefit type not found", 404)
    await company_for_tenant(session, row.company_id, tenant_id)
    return row


async def _ensure_unique_name(session: AsyncSession, company_id, name: str, exclude_id=None) -> None:
    stmt = select(BenefitType.id).where(
        BenefitType.company_id == company_id,
        func.lower(BenefitType.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(BenefitType.id != exclude_id)
    if await session.scalar(stmt) is not None:
        raise _bad("A benefit type with this name already exists", status.HTTP_409_CONFLICT)


def _apply_type_fields(row: BenefitType, payload) -> None:
    row.name = payload.name.strip()
    row.default_amount = payload.default_amount
    row.is_active = payload.is_active


async def create_type(session: AsyncSession, tenant_id: uuid.UUID, payload) -> BenefitType:
    await company_for_tenant(session, payload.company_id, tenant_id)
    await _ensure_unique_name(session, payload.company_id, payload.name.strip())
    row = BenefitType(company_id=payload.company_id)
    _apply_type_fields(row, payload)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


async def update_type(session: AsyncSession, row: BenefitType, payload) -> BenefitType:
    await _ensure_unique_name(session, row.company_id, payload.name.strip(), exclude_id=row.id)
    _apply_type_fields(row, payload)
    await session.flush()
    await session.refresh(row)
    return row


async def delete_type(session: AsyncSession, row: BenefitType) -> None:
    used = await session.scalar(select(EmployeeBenefit.id).where(EmployeeBenefit.benefit_type_id == row.id).limit(1))
    if used is not None:
        raise _bad(
            "This type is assigned to employees. Deactivate it instead of deleting.",
            status.HTTP_409_CONFLICT,
        )
    await session.delete(row)
    await session.flush()


async def paid_amounts(session: AsyncSession, benefit_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    """Amounts already paid in approved payroll runs, per employee benefit."""
    if not benefit_ids:
        return {}
    rows = await session.execute(
        select(PayrollPayslipLine.employee_benefit_id, func.sum(PayrollPayslipLine.amount))
        .join(PayrollPayslip, PayrollPayslip.id == PayrollPayslipLine.payslip_id)
        .join(PayrollRun, PayrollRun.id == PayrollPayslip.run_id)
        .where(
            PayrollRun.status == "APPROVED",
            PayrollPayslipLine.employee_benefit_id.in_(benefit_ids),
        )
        .group_by(PayrollPayslipLine.employee_benefit_id)
    )
    return {row[0]: Decimal(row[1]) for row in rows.all()}


def benefit_to_read(row: EmployeeBenefit, paid: Decimal) -> dict:
    return {
        "id": row.id,
        "employee_id": row.employee_id,
        "benefit_type_id": row.benefit_type_id,
        "type_name": row.benefit_type.name,
        "note": row.note,
        "frequency": row.frequency,
        "amount": row.amount,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "status": row.status,
        "paid": paid,
        "created_at": row.created_at,
    }


async def _load_benefit(session: AsyncSession, benefit_id) -> EmployeeBenefit | None:
    return await session.scalar(
        select(EmployeeBenefit)
        .options(selectinload(EmployeeBenefit.benefit_type))
        .where(EmployeeBenefit.id == benefit_id)
        .execution_options(populate_existing=True)
    )


async def list_benefits(session: AsyncSession, employee: Employee) -> list[dict]:
    rows = list(
        (
            await session.scalars(
                select(EmployeeBenefit)
                .options(selectinload(EmployeeBenefit.benefit_type))
                .where(EmployeeBenefit.employee_id == employee.id)
                .order_by(EmployeeBenefit.status, EmployeeBenefit.start_date.desc())
            )
        ).all()
    )
    paid = await paid_amounts(session, [row.id for row in rows])
    return [benefit_to_read(row, paid.get(row.id, ZERO)) for row in rows]


async def _apply_benefit_fields(
    session: AsyncSession, employee: Employee, row: EmployeeBenefit, payload, *, creating: bool
) -> None:
    if payload.frequency not in FREQUENCIES:
        raise _bad("frequency must be RECURRING or ONE_OFF")
    if payload.status not in STATUSES:
        raise _bad("status must be ACTIVE or STOPPED")
    kind = await resolve_type(session, BenefitType, employee.company_id, payload.benefit_type_id, payload.title)
    if kind is None or kind.company_id != employee.company_id:
        raise _bad("Benefit type not found for this company")
    if creating and not kind.is_active:
        raise _bad("This benefit type is inactive")
    end_date = payload.end_date if payload.frequency == "RECURRING" else None
    if end_date is not None and end_date < payload.start_date:
        raise _bad("end_date must be on or after start_date")
    row.benefit_type_id = kind.id
    row.note = (payload.note or "").strip() or None
    row.frequency = payload.frequency
    row.amount = payload.amount
    row.start_date = payload.start_date
    row.end_date = end_date
    row.status = payload.status


async def _benefit_for_employee(session: AsyncSession, employee: Employee, benefit_id) -> EmployeeBenefit:
    row = await _load_benefit(session, benefit_id)
    if row is None or row.employee_id != employee.id:
        raise _bad("Benefit not found", 404)
    return row


async def add_benefit(session: AsyncSession, employee: Employee, payload) -> dict:
    row = EmployeeBenefit(company_id=employee.company_id, employee_id=employee.id)
    await _apply_benefit_fields(session, employee, row, payload, creating=True)
    session.add(row)
    await session.flush()
    loaded = await _load_benefit(session, row.id)
    assert loaded is not None
    return benefit_to_read(loaded, ZERO)


async def update_benefit(session: AsyncSession, employee: Employee, benefit_id, payload) -> dict:
    row = await _benefit_for_employee(session, employee, benefit_id)
    await _apply_benefit_fields(session, employee, row, payload, creating=False)
    await session.flush()
    loaded = await _load_benefit(session, row.id)
    assert loaded is not None
    paid = await paid_amounts(session, [loaded.id])
    return benefit_to_read(loaded, paid.get(loaded.id, ZERO))


async def delete_benefit(session: AsyncSession, employee: Employee, benefit_id) -> None:
    row = await _benefit_for_employee(session, employee, benefit_id)
    paid = await paid_amounts(session, [row.id])
    if paid.get(row.id, ZERO) > ZERO:
        raise _bad(
            "This benefit is on an approved payroll. Stop it instead of deleting.",
            status.HTTP_409_CONFLICT,
        )
    await session.delete(row)
    await session.flush()


async def benefits_for_period(
    session: AsyncSession,
    employee_ids: list[uuid.UUID],
    period_start: date,
    period_end: date,
) -> dict[uuid.UUID, list[dict]]:
    if not employee_ids:
        return {}
    rows = (
        await session.scalars(
            select(EmployeeBenefit)
            .options(selectinload(EmployeeBenefit.benefit_type))
            .where(
                EmployeeBenefit.employee_id.in_(employee_ids),
                EmployeeBenefit.status == "ACTIVE",
                EmployeeBenefit.start_date <= period_end,
                or_(EmployeeBenefit.frequency == "RECURRING", EmployeeBenefit.start_date >= period_start),
                or_(EmployeeBenefit.end_date.is_(None), EmployeeBenefit.end_date >= period_start),
            )
            .order_by(EmployeeBenefit.start_date, EmployeeBenefit.created_at)
        )
    ).all()
    out: dict[uuid.UUID, list[dict]] = defaultdict(list)
    for row in rows:
        name = row.benefit_type.name
        if row.note:
            name = f"{name} – {row.note}"
        out[row.employee_id].append({"id": row.id, "name": name[:100], "amount": row.amount})
    return out
