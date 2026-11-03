from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee, LeaveBalance, LeaveRequest, LeaveType

CENTS = Decimal("0.01")
PENDING_STATUSES = {"PENDING_SUPERVISOR", "PENDING_HR"}


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def month_span(start: date, as_of: date) -> int:
    if as_of < start:
        return 0
    end = as_of + timedelta(days=1)
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    return max(0, months)


def monthly_rate(leave_type: LeaveType) -> Decimal:
    rate = getattr(leave_type, "accrual_per_month", None)
    if rate is not None and Decimal(rate) > 0:
        return Decimal(rate)
    if Decimal(leave_type.days) > 0:
        return Decimal(leave_type.days) / Decimal(12)
    return Decimal("0")


def entitled_days(leave_type: LeaveType, joined_on: date | None, year: int, as_of: date) -> Decimal:
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    if joined_on is not None and joined_on > year_end:
        return Decimal("0")
    if not leave_type.accrued:
        if Decimal(leave_type.days) <= 0:
            return Decimal("0")
        return _money(Decimal(leave_type.days))
    rate = monthly_rate(leave_type)
    if rate <= 0:
        return Decimal("0")
    if joined_on is None:
        return _money(rate * 12)
    start = max(joined_on, year_start)
    last = min(as_of, year_end)
    months = min(12, month_span(start, last))
    return _money(rate * Decimal(months))


@dataclass(frozen=True)
class BalanceSnapshot:
    employee_id: uuid.UUID
    employee_name: str
    employee_number: str
    leave_type_id: uuid.UUID
    leave_type_name: str
    year: int
    accrued: bool
    unlimited: bool
    entitled: Decimal
    extra: Decimal
    used: Decimal
    pending: Decimal
    remaining: Decimal | None


def _person_name(row: Employee) -> str:
    return " ".join(part for part in (row.first_name, row.other_names, row.last_name) if part)


def snapshot(
    employee: Employee,
    leave_type: LeaveType,
    year: int,
    extra: Decimal,
    used: Decimal,
    pending: Decimal,
    as_of: date,
) -> BalanceSnapshot:
    unlimited = (not leave_type.accrued) and Decimal(leave_type.days) <= 0
    entitled = Decimal("0") if unlimited else entitled_days(leave_type, employee.date_joined, year, as_of)
    extra = _money(extra)
    used = _money(used)
    pending = _money(pending)
    remaining = None if unlimited else _money(entitled + extra - used - pending)
    return BalanceSnapshot(
        employee_id=employee.id,
        employee_name=_person_name(employee),
        employee_number=employee.employee_number,
        leave_type_id=leave_type.id,
        leave_type_name=leave_type.name,
        year=year,
        accrued=leave_type.accrued,
        unlimited=unlimited,
        entitled=entitled,
        extra=extra,
        used=used,
        pending=pending,
        remaining=remaining,
    )


async def request_totals(
    session: AsyncSession,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    year: int,
) -> tuple[Decimal, Decimal]:
    rows = list(
        (
            await session.scalars(
                select(LeaveRequest).where(
                    LeaveRequest.employee_id == employee_id,
                    LeaveRequest.leave_type_id == leave_type_id,
                )
            )
        ).all()
    )
    used = Decimal("0")
    pending = Decimal("0")
    for row in rows:
        if row.start_on.year != year:
            continue
        if row.status == "APPROVED":
            used += Decimal(row.days)
        elif row.status in PENDING_STATUSES:
            pending += Decimal(row.days)
    return used, pending


async def extra_days(
    session: AsyncSession, employee_id: uuid.UUID, leave_type_id: uuid.UUID, year: int
) -> Decimal:
    row = await session.scalar(
        select(LeaveBalance).where(
            LeaveBalance.employee_id == employee_id,
            LeaveBalance.leave_type_id == leave_type_id,
            LeaveBalance.year == year,
        )
    )
    return Decimal(row.extra_days) if row is not None else Decimal("0")


async def balance_for(
    session: AsyncSession,
    employee: Employee,
    leave_type: LeaveType,
    year: int,
    as_of: date | None = None,
) -> BalanceSnapshot:
    used, pending = await request_totals(session, employee.id, leave_type.id, year)
    extra = await extra_days(session, employee.id, leave_type.id, year)
    return snapshot(employee, leave_type, year, extra, used, pending, as_of or date.today())


def as_of_for_year(year: int, today: date | None = None) -> date:
    today = today or date.today()
    last = date(year, 12, 31)
    if year < today.year:
        return last
    if year > today.year:
        return date(year, 1, 1)
    return min(today, last)
