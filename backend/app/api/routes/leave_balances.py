from app.api.access_control import employee_scope, require_access
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_db, get_tenant_id
from app.api.leave import leave_type_for_company
from app.api.org import company_for_tenant
from app.models import Company, Employee, LeaveBalance, LeaveType, User
from app.schemas.leave import LeaveBalanceAdjust, LeaveBalanceRead
from app.services.leave_balances import as_of_for_year, balance_for

router = APIRouter(prefix="/leave-balances", tags=["leave-balances"])


def _read(row) -> LeaveBalanceRead:
    return LeaveBalanceRead(
        employee_id=row.employee_id,
        employee_name=row.employee_name,
        employee_number=row.employee_number,
        leave_type_id=row.leave_type_id,
        leave_type_name=row.leave_type_name,
        year=row.year,
        accrued=row.accrued,
        unlimited=row.unlimited,
        entitled=row.entitled,
        extra=row.extra,
        used=row.used,
        pending=row.pending,
        remaining=row.remaining,
    )


@router.get("", response_model=list[LeaveBalanceRead], dependencies=[Depends(require_access('leave.view_all', 'leave.view_own', 'leave.view_team', 'leave.manage'))])
async def list_leave_balances(
    company_id: uuid.UUID | None = Query(default=None),
    employee_id: uuid.UUID | None = Query(default=None),
    leave_type_id: uuid.UUID | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[LeaveBalanceRead]:
    chosen_year = year or date.today().year
    as_of = as_of_for_year(chosen_year)
    if company_id is not None:
        await company_for_tenant(session, company_id, tenant_id)
        company_ids = [company_id]
    else:
        company_ids = list((await session.scalars(select(Company.id).where(Company.tenant_id == tenant_id))).all())
    if not company_ids:
        return []

    people_stmt = select(Employee).where(Employee.company_id.in_(company_ids), await employee_scope(session, user, "leave")).order_by(Employee.first_name, Employee.last_name)
    if employee_id is not None:
        people_stmt = people_stmt.where(Employee.id == employee_id)
    else:
        people_stmt = people_stmt.where(Employee.status.in_(("ACTIVE", "SUSPENDED")))
    people = list((await session.scalars(people_stmt)).all())
    if employee_id is not None and not people:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if employee_id is not None:
        await company_for_tenant(session, people[0].company_id, tenant_id)

    types_stmt = select(LeaveType).where(LeaveType.company_id.in_(company_ids)).order_by(LeaveType.sort_order, LeaveType.name)
    if leave_type_id is not None:
        types_stmt = types_stmt.where(LeaveType.id == leave_type_id)
    types = list((await session.scalars(types_stmt)).all())
    if not people or not types:
        return []

    out: list[LeaveBalanceRead] = []
    for person in people:
        for leave_type in types:
            if leave_type.company_id != person.company_id:
                continue
            out.append(_read(await balance_for(session, person, leave_type, chosen_year, as_of)))
    return out


@router.patch("", response_model=LeaveBalanceRead, dependencies=[Depends(require_access('leave.manage'))])
async def adjust_leave_balance(
    payload: LeaveBalanceAdjust,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_tenant_db),
) -> LeaveBalanceRead:
    employee = await session.get(Employee, payload.employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    leave_type = await leave_type_for_company(session, payload.leave_type_id, employee.company_id)
    row = await session.scalar(
        select(LeaveBalance).where(
            LeaveBalance.employee_id == employee.id,
            LeaveBalance.leave_type_id == leave_type.id,
            LeaveBalance.year == payload.year,
        )
    )
    extra = Decimal(payload.extra_days)
    if row is None:
        if extra != 0:
            session.add(
                LeaveBalance(
                    company_id=employee.company_id,
                    employee_id=employee.id,
                    leave_type_id=leave_type.id,
                    year=payload.year,
                    extra_days=extra,
                )
            )
            await session.flush()
    else:
        row.extra_days = extra
        await session.flush()
    return _read(await balance_for(session, employee, leave_type, payload.year, as_of_for_year(payload.year)))
