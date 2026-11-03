from app.api.access_control import require_access
from datetime import date
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_tenant_db, get_tenant_id
from app.api.org import branch_for_company, company_for_tenant
from app.models import Branch, Employee, User
from app.schemas.attendance import AttendanceMark, AttendanceRead, ClockPayload
from app.services.attendance import (
    clock_in,
    clock_out,
    employee_for_user,
    list_day,
    mark_day,
    work_date_for_branch,
)

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.get("", response_model=list[AttendanceRead], dependencies=[Depends(require_access('attendance.manage'))])
async def list_attendance(
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    work_on: date = Query(),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    await company_for_tenant(session, company_id, tenant_id)
    await branch_for_company(session, branch_id, company_id)
    return await list_day(session, company_id, branch_id, work_on)


@router.put("", response_model=AttendanceRead, dependencies=[Depends(require_access('attendance.manage'))])
async def mark_attendance(
    payload: AttendanceMark,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    employee = await session.get(Employee, payload.employee_id, options=(selectinload(Employee.login_user),))
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    return await mark_day(session, employee, payload.work_on, payload.status, payload.note)


@router.get("/me", response_model=AttendanceRead, dependencies=[Depends(require_access('attendance.self', 'attendance.manage'))])
async def my_attendance(
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    employee = await employee_for_user(session, user)
    branch = await session.get(Branch, employee.branch_id)
    work_on = work_date_for_branch(branch) if branch else date.today()
    rows = await list_day(session, employee.company_id, employee.branch_id, work_on)
    mine = next((row for row in rows if row["employee_id"] == employee.id), None)
    if mine is None:
        raise HTTPException(status_code=404, detail="No attendance row")
    return mine


@router.post("/clock-in", response_model=AttendanceRead, dependencies=[Depends(require_access('attendance.self', 'attendance.manage'))])
async def clock_in_self(
    payload: ClockPayload,
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    return await clock_in(session, user, payload.device_id)


@router.post("/clock-out", response_model=AttendanceRead, dependencies=[Depends(require_access('attendance.self', 'attendance.manage'))])
async def clock_out_self(
    payload: ClockPayload,
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    return await clock_out(session, user, payload.device_id)
