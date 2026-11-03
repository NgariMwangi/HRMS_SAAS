from app.api.access_control import employee_scope, require_access
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_db, get_tenant_id
from app.api.leave import (
    cancel_request,
    create_hr_request,
    create_self_request,
    create_supervisor_request,
    decide_as_hr,
    decide_as_supervisor,
    list_requests,
    load_request,
    request_to_read,
)
from app.models import Employee, User
from sqlalchemy import select
from app.api.org import company_for_tenant
from app.schemas.leave import (
    LeaveEmployeeRead,
    LeaveDecisionWrite,
    LeaveHrCreate,
    LeaveRequestRead,
    LeaveSelfCreate,
    LeaveSupervisorCreate,
)

router = APIRouter(prefix="/leave-requests", tags=["leave-requests"])


@router.get("/people", response_model=list[LeaveEmployeeRead], dependencies=[Depends(require_access('leave.view_all', 'leave.view_own', 'leave.view_team', 'leave.manage'))])
async def leave_people(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[Employee]:
    await company_for_tenant(session, company_id, user.tenant_id)
    return list((await session.scalars(select(Employee).where(
        Employee.company_id == company_id, await employee_scope(session, user, "leave"),
        Employee.status.in_(("ACTIVE", "SUSPENDED")),
    ).order_by(Employee.last_name, Employee.first_name))).all())


@router.get("", response_model=list[LeaveRequestRead], dependencies=[Depends(require_access('leave.view_all', 'leave.view_own', 'leave.view_team', 'leave.manage'))])
async def list_leave_requests(
    company_id: uuid.UUID | None = Query(default=None),
    employee_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[LeaveRequestRead]:
    rows = await list_requests(session, tenant_id, company_id, employee_id, status, employee_filter=await employee_scope(session, user, "leave"))
    return [await request_to_read(session, row) for row in rows]


@router.get("/{request_id}", response_model=LeaveRequestRead, dependencies=[Depends(require_access('leave.view_all', 'leave.view_own', 'leave.view_team', 'leave.manage'))])
async def get_leave_request(
    request_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> LeaveRequestRead:
    row = await load_request(session, request_id, tenant_id)
    visible = await session.scalar(select(Employee.id).where(Employee.id == row.employee_id, await employee_scope(session, user, "leave")))
    if visible is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return await request_to_read(session, row)


@router.post("/hr", response_model=LeaveRequestRead, status_code=201, dependencies=[Depends(require_access('leave.manage'))])
async def hr_apply_leave(
    payload: LeaveHrCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> LeaveRequestRead:
    row = await create_hr_request(
        session,
        tenant_id,
        user,
        payload.employee_id,
        payload.leave_type_id,
        payload.start_on,
        payload.end_on,
        payload.reason,
        payload.hr_action,
    )
    return await request_to_read(session, row)


@router.post("/self", response_model=LeaveRequestRead, status_code=201, dependencies=[Depends(require_access('leave.view_own', 'leave.manage'))])
async def employee_apply_leave(
    payload: LeaveSelfCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> LeaveRequestRead:
    row = await create_self_request(
        session,
        tenant_id,
        user,
        payload.employee_id,
        payload.leave_type_id,
        payload.start_on,
        payload.end_on,
        payload.reason,
        payload.approval_mode,
    )
    return await request_to_read(session, row)


@router.post("/supervisor", response_model=LeaveRequestRead, status_code=201, dependencies=[Depends(require_access('leave.view_team', 'leave.manage'))])
async def supervisor_apply_leave(
    payload: LeaveSupervisorCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> LeaveRequestRead:
    row = await create_supervisor_request(
        session,
        tenant_id,
        user,
        payload.supervisor_employee_id,
        payload.employee_id,
        payload.leave_type_id,
        payload.start_on,
        payload.end_on,
        payload.reason,
    )
    return await request_to_read(session, row)


@router.post("/{request_id}/supervisor-decision", response_model=LeaveRequestRead, dependencies=[Depends(require_access('leave.view_team', 'leave.manage'))])
async def supervisor_decide_leave(
    request_id: uuid.UUID,
    payload: LeaveDecisionWrite,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> LeaveRequestRead:
    if payload.supervisor_employee_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="supervisor_employee_id is required",
        )
    row = await load_request(session, request_id, tenant_id)
    row = await decide_as_supervisor(
        session, row, user, payload.supervisor_employee_id, payload.decision, payload.note
    )
    return await request_to_read(session, row)


@router.post("/{request_id}/hr-decision", response_model=LeaveRequestRead, dependencies=[Depends(require_access('leave.manage'))])
async def hr_decide_leave(
    request_id: uuid.UUID,
    payload: LeaveDecisionWrite,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> LeaveRequestRead:
    row = await load_request(session, request_id, tenant_id)
    row = await decide_as_hr(session, row, user, payload.decision, payload.note)
    return await request_to_read(session, row)


@router.post("/{request_id}/cancel", response_model=LeaveRequestRead, dependencies=[Depends(require_access('leave.manage'))])
async def cancel_leave_request(
    request_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> LeaveRequestRead:
    row = await load_request(session, request_id, tenant_id)
    row = await cancel_request(session, row, user)
    return await request_to_read(session, row)
