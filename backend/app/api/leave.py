import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.org import blank_to_none, company_for_tenant
from app.api.supervisors import list_supervisors
from app.models import Branch, Company, Employee, LeaveDecision, LeaveRequest, LeaveType, PublicHoliday, User
from app.services.leave_balances import as_of_for_year, balance_for
from app.services.access import has_permission, require_permission
from app.schemas.leave import LeaveDecisionRead, LeaveRequestRead
from app.services.leave_emails import queue as queue_emails

OPEN_STATUSES = {"PENDING_SUPERVISOR", "PENDING_HR", "APPROVED"}
HR_ACTIONS = {"APPROVE_NOW", "SEND_TO_SUPERVISOR"}
SELF_MODES = {"HR_ONLY", "SUPERVISOR_THEN_HR"}
DECISIONS = {"APPROVED", "REJECTED"}


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


async def require_hr(session: AsyncSession, user: User) -> None:
    await require_permission(session, user, "leave.manage")


async def require_actor(session: AsyncSession, user: User, employee_id: uuid.UUID) -> None:
    # HR can act on behalf of staff. Self-service actors must use their own identity.
    if user.employee_id != employee_id and not await has_permission(session, user, "leave.manage"):
        raise HTTPException(status_code=403, detail="Use your own employee identity")


def holiday_dates_in_range(holidays: list[PublicHoliday], start_on: date, end_on: date) -> set[date]:
    closed: set[date] = set()
    for row in holidays:
        if row.kind == "ONCE" and row.observed_on is not None:
            if start_on <= row.observed_on <= end_on:
                closed.add(row.observed_on)
            continue
        if row.kind == "YEARLY" and row.month and row.day:
            for year in range(start_on.year, end_on.year + 1):
                try:
                    observed = date(year, row.month, row.day)
                except ValueError:
                    continue
                if start_on <= observed <= end_on:
                    closed.add(observed)
    return closed


def count_leave_days(
    start_on: date,
    end_on: date,
    day_basis: str,
    closed: set[date] | None = None,
) -> Decimal:
    if end_on < start_on:
        raise _bad("End date cannot be before the start date")
    if day_basis == "CALENDAR":
        return Decimal((end_on - start_on).days + 1)
    skipped = closed or set()
    days = 0
    cursor = start_on
    while cursor <= end_on:
        if cursor.weekday() < 5 and cursor not in skipped:
            days += 1
        cursor += timedelta(days=1)
    if days == 0:
        raise _bad("This range has no working days")
    return Decimal(days)


async def closed_working_dates(
    session: AsyncSession, employee: Employee, start_on: date, end_on: date
) -> set[date]:
    branch = await session.get(Branch, employee.branch_id)
    country_id = branch.country_id if branch is not None else None
    rows = list(
        (
            await session.scalars(
                select(PublicHoliday).where(
                    PublicHoliday.company_id == employee.company_id,
                    or_(
                        PublicHoliday.country_id.is_(None),
                        PublicHoliday.country_id == country_id,
                    ),
                )
            )
        ).all()
    )
    return holiday_dates_in_range(rows, start_on, end_on)


async def _assert_enough_balance(
    session: AsyncSession,
    employee: Employee,
    leave_type: LeaveType,
    year: int,
    days: Decimal,
) -> None:
    held = await balance_for(session, employee, leave_type, year, as_of_for_year(year))
    if held.unlimited or held.remaining is None:
        return
    if days > held.remaining:
        raise _bad(
            f"This request needs {days} days. {held.remaining} day(s) remain for {leave_type.name} in {year}."
        )


def employee_name(row: Employee) -> str:
    return " ".join(part for part in (row.first_name, row.other_names, row.last_name) if part)


async def leave_type_for_company(
    session: AsyncSession, leave_type_id: uuid.UUID, company_id: uuid.UUID
) -> LeaveType:
    row = await session.get(LeaveType, leave_type_id)
    if row is None or row.company_id != company_id:
        raise _bad("Leave type does not belong to this company")
    return row


async def employee_in_company(
    session: AsyncSession, employee_id: uuid.UUID, company_id: uuid.UUID
) -> Employee:
    row = await session.get(Employee, employee_id)
    if row is None or row.company_id != company_id:
        raise _bad("Employee does not belong to this company")
    return row


async def _has_supervisors(session: AsyncSession, employee_id: uuid.UUID) -> bool:
    return bool(await list_supervisors(session, employee_id))


async def _is_supervisor_of(
    session: AsyncSession, supervisor_id: uuid.UUID, employee_id: uuid.UUID
) -> bool:
    return any(row.id == supervisor_id for row in await list_supervisors(session, employee_id))


async def _assert_no_overlap(
    session: AsyncSession,
    employee_id: uuid.UUID,
    start_on: date,
    end_on: date,
    ignore_id: uuid.UUID | None = None,
) -> None:
    stmt = select(LeaveRequest.id).where(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status.in_(OPEN_STATUSES),
        LeaveRequest.start_on <= end_on,
        LeaveRequest.end_on >= start_on,
    )
    if ignore_id is not None:
        stmt = stmt.where(LeaveRequest.id != ignore_id)
    clash = await session.scalar(stmt)
    if clash is not None:
        raise _bad("This employee already has leave that overlaps those dates")


def _decision_read(row: LeaveDecision, actor_name: str | None) -> LeaveDecisionRead:
    return LeaveDecisionRead(
        id=row.id,
        step=row.step,
        decision=row.decision,
        note=row.note,
        actor_user_id=row.actor_user_id,
        actor_employee_id=row.actor_employee_id,
        actor_name=actor_name,
        created_at=row.created_at,
    )


async def request_to_read(session: AsyncSession, row: LeaveRequest) -> LeaveRequestRead:
    employee = row.employee if row.employee is not None else await session.get(Employee, row.employee_id)
    leave_type = row.leave_type if row.leave_type is not None else await session.get(LeaveType, row.leave_type_id)
    if employee is None or leave_type is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    requester: str | None = None
    if row.requested_by_user_id:
        user = await session.get(User, row.requested_by_user_id)
        requester = user.full_name if user else None
    if requester is None and row.requested_by_employee_id:
        actor = await session.get(Employee, row.requested_by_employee_id)
        requester = employee_name(actor) if actor else None
    decisions: list[LeaveDecisionRead] = []
    for item in row.decisions:
        name: str | None = None
        if item.actor_user_id:
            user = await session.get(User, item.actor_user_id)
            name = user.full_name if user else None
        if name is None and item.actor_employee_id:
            actor = await session.get(Employee, item.actor_employee_id)
            name = employee_name(actor) if actor else None
        decisions.append(_decision_read(item, name))
    return LeaveRequestRead(
        id=row.id,
        company_id=row.company_id,
        employee_id=row.employee_id,
        employee_name=employee_name(employee),
        employee_number=employee.employee_number,
        leave_type_id=row.leave_type_id,
        leave_type_name=leave_type.name,
        day_basis=leave_type.day_basis,
        start_on=row.start_on,
        end_on=row.end_on,
        days=row.days,
        reason=row.reason,
        requested_as=row.requested_as,
        approval_mode=row.approval_mode,
        status=row.status,
        requested_by_user_id=row.requested_by_user_id,
        requested_by_employee_id=row.requested_by_employee_id,
        requested_by_name=requester,
        decisions=decisions,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _reload(session: AsyncSession, request_id: uuid.UUID) -> LeaveRequest:
    row = await session.scalar(
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.decisions),
        )
        .where(LeaveRequest.id == request_id)
    )
    assert row is not None
    return row


async def load_request(
    session: AsyncSession, request_id: uuid.UUID, tenant_id: uuid.UUID
) -> LeaveRequest:
    row = await session.scalar(
        select(LeaveRequest)
        .options(
            selectinload(LeaveRequest.employee),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.decisions),
        )
        .where(LeaveRequest.id == request_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    await company_for_tenant(session, row.company_id, tenant_id)
    return row


async def list_requests(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID | None,
    employee_id: uuid.UUID | None,
    status_filter: str | None,
    *,
    employee_filter=None,
) -> list[LeaveRequest]:
    stmt = (
        select(LeaveRequest)
        .join(Company, Company.id == LeaveRequest.company_id)
        .where(Company.tenant_id == tenant_id)
        .options(
            selectinload(LeaveRequest.employee),
            selectinload(LeaveRequest.leave_type),
            selectinload(LeaveRequest.decisions),
        )
        .order_by(LeaveRequest.created_at.desc())
    )
    if company_id is not None:
        await company_for_tenant(session, company_id, tenant_id)
        stmt = stmt.where(LeaveRequest.company_id == company_id)
    if employee_id is not None:
        employee = await session.get(Employee, employee_id)
        if employee is None:
            raise HTTPException(status_code=404, detail="Employee not found")
        await company_for_tenant(session, employee.company_id, tenant_id)
        stmt = stmt.where(LeaveRequest.employee_id == employee_id)
    if status_filter:
        stmt = stmt.where(LeaveRequest.status == status_filter.upper())
    if employee_filter is not None:
        stmt = stmt.where(LeaveRequest.employee_id.in_(select(Employee.id).where(employee_filter)))
    return list((await session.scalars(stmt)).all())


async def _create_request(
    session: AsyncSession,
    *,
    employee: Employee,
    leave_type: LeaveType,
    start_on: date,
    end_on: date,
    reason: str | None,
    requested_as: str,
    approval_mode: str,
    status_value: str,
    user: User | None,
    actor_employee_id: uuid.UUID | None,
    duration: str = "FULL_DAY",
) -> LeaveRequest:
    if employee.status == "TERMINATED":
        raise _bad("Leave cannot be applied for a terminated employee. Use their current record.")
    closed = (
        await closed_working_dates(session, employee, start_on, end_on)
        if leave_type.day_basis != "CALENDAR"
        else set()
    )
    days = count_leave_days(start_on, end_on, leave_type.day_basis, closed)
    fractions = {"FULL_DAY": Decimal("1"), "HALF_DAY": Decimal("0.5"), "QUARTER_DAY": Decimal("0.25")}
    if duration not in fractions:
        raise _bad("Choose full day, half day or quarter day")
    if duration != "FULL_DAY":
        if start_on != end_on:
            raise _bad("Half-day and quarter-day leave must be for a single date")
        days = fractions[duration]
    await _assert_enough_balance(session, employee, leave_type, start_on.year, days)
    await _assert_no_overlap(session, employee.id, start_on, end_on)
    row = LeaveRequest(
        company_id=employee.company_id,
        employee_id=employee.id,
        leave_type_id=leave_type.id,
        start_on=start_on,
        end_on=end_on,
        days=days,
        reason=blank_to_none(reason or ""),
        requested_as=requested_as,
        approval_mode=approval_mode,
        status=status_value,
        requested_by_user_id=user.id if user else None,
        requested_by_employee_id=actor_employee_id,
    )
    session.add(row)
    await session.flush()
    return row


async def _add_decision(
    session: AsyncSession,
    request: LeaveRequest,
    *,
    step: str,
    decision: str,
    note: str | None,
    user: User | None,
    actor_employee_id: uuid.UUID | None,
) -> None:
    session.add(
        LeaveDecision(
            company_id=request.company_id,
            leave_request_id=request.id,
            step=step,
            decision=decision,
            note=blank_to_none(note or ""),
            actor_user_id=user.id if user else None,
            actor_employee_id=actor_employee_id,
        )
    )
    await session.flush()


async def create_hr_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user: User,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    start_on: date,
    end_on: date,
    reason: str | None,
    hr_action: str,
    duration: str = "FULL_DAY",
) -> LeaveRequest:
    await require_hr(session, user)
    action = hr_action.strip().upper()
    if action not in HR_ACTIONS:
        raise _bad("Choose approve now or send to the supervisor")
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    leave_type = await leave_type_for_company(session, leave_type_id, employee.company_id)
    if action == "SEND_TO_SUPERVISOR" and not await _has_supervisors(session, employee.id):
        raise _bad("This employee has no supervisor to approve the request")
    status_value = "APPROVED" if action == "APPROVE_NOW" else "PENDING_SUPERVISOR"
    approval_mode = "HR_ONLY" if action == "APPROVE_NOW" else "SUPERVISOR_THEN_HR"
    row = await _create_request(
        session,
        employee=employee,
        leave_type=leave_type,
        duration=duration,
        start_on=start_on,
        end_on=end_on,
        reason=reason,
        requested_as="HR",
        approval_mode=approval_mode,
        status_value=status_value,
        user=user,
        actor_employee_id=None,
    )
    if action == "APPROVE_NOW":
        await _add_decision(session, row, step="HR", decision="APPROVED", note=None, user=user, actor_employee_id=None)
    await queue_emails(session, row, "APPLIED")
    if action == "APPROVE_NOW":
        await queue_emails(session, row, "HR_DECISION", decision="APPROVED")
    return await _reload(session, row.id)


async def create_self_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user: User,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    start_on: date,
    end_on: date,
    reason: str | None,
    approval_mode: str,
    duration: str = "FULL_DAY",
) -> LeaveRequest:
    await require_actor(session, user, employee_id)
    mode = approval_mode.strip().upper()
    if mode == "AUTO":
        mode = "SUPERVISOR_THEN_HR" if await _has_supervisors(session, employee_id) else "HR_ONLY"
    if mode not in SELF_MODES:
        raise _bad("Choose supervisor then HR, or HR alone")
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    leave_type = await leave_type_for_company(session, leave_type_id, employee.company_id)
    if mode == "SUPERVISOR_THEN_HR" and not await _has_supervisors(session, employee.id):
        raise _bad("This employee has no supervisor. Use HR-only approval, or add a supervisor first")
    status_value = "PENDING_HR" if mode == "HR_ONLY" else "PENDING_SUPERVISOR"
    row = await _create_request(
        session,
        employee=employee,
        leave_type=leave_type,
        duration=duration,
        start_on=start_on,
        end_on=end_on,
        reason=reason,
        requested_as="EMPLOYEE",
        approval_mode=mode,
        status_value=status_value,
        user=user,
        actor_employee_id=employee.id,
    )
    await queue_emails(session, row, "APPLIED")
    return await _reload(session, row.id)


async def create_supervisor_request(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user: User,
    supervisor_employee_id: uuid.UUID,
    employee_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    start_on: date,
    end_on: date,
    reason: str | None,
    duration: str = "FULL_DAY",
) -> LeaveRequest:
    await require_actor(session, user, supervisor_employee_id)
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    supervisor = await employee_in_company(session, supervisor_employee_id, employee.company_id)
    if not await _is_supervisor_of(session, supervisor.id, employee.id):
        raise _bad("Only a supervisor of this employee can apply leave for them")
    leave_type = await leave_type_for_company(session, leave_type_id, employee.company_id)
    row = await _create_request(
        session,
        employee=employee,
        leave_type=leave_type,
        duration=duration,
        start_on=start_on,
        end_on=end_on,
        reason=reason,
        requested_as="SUPERVISOR",
        approval_mode="HR_ONLY",
        status_value="PENDING_HR",
        user=user,
        actor_employee_id=supervisor.id,
    )
    await queue_emails(session, row, "APPLIED")
    return await _reload(session, row.id)


async def decide_as_supervisor(
    session: AsyncSession,
    request: LeaveRequest,
    user: User,
    supervisor_employee_id: uuid.UUID,
    decision: str,
    note: str | None,
) -> LeaveRequest:
    await require_actor(session, user, supervisor_employee_id)
    choice = decision.strip().upper()
    if choice not in DECISIONS:
        raise _bad("Approve or reject the request")
    if request.status != "PENDING_SUPERVISOR":
        raise _bad("This request is not waiting for a supervisor")
    if not await _is_supervisor_of(session, supervisor_employee_id, request.employee_id):
        raise _bad("Only a supervisor of this employee can decide here")
    await employee_in_company(session, supervisor_employee_id, request.company_id)
    await _add_decision(
        session,
        request,
        step="SUPERVISOR",
        decision=choice,
        note=note,
        user=user,
        actor_employee_id=supervisor_employee_id,
    )
    # Both recommendations go to HR/the workspace owner for the final response.
    request.status = "PENDING_HR"
    await queue_emails(session, request, "SUPERVISOR_DECISION", decision=choice,
        actor_employee_id=supervisor_employee_id, note=note)
    await session.flush()
    return await _reload(session, request.id)


async def decide_as_hr(
    session: AsyncSession,
    request: LeaveRequest,
    user: User,
    decision: str,
    note: str | None,
) -> LeaveRequest:
    await require_hr(session, user)
    choice = decision.strip().upper()
    if choice not in DECISIONS:
        raise _bad("Approve or reject the request")
    if request.status not in {"PENDING_HR", "PENDING_SUPERVISOR"}:
        raise _bad("This request is no longer waiting for HR")
    await _add_decision(session, request, step="HR", decision=choice, note=note, user=user, actor_employee_id=None)
    request.status = "APPROVED" if choice == "APPROVED" else "REJECTED"
    await queue_emails(session, request, "HR_DECISION", decision=choice, note=note)
    await session.flush()
    return await _reload(session, request.id)


async def cancel_request(session: AsyncSession, request: LeaveRequest, user: User) -> LeaveRequest:
    await require_hr(session, user)
    if request.status not in {"PENDING_HR", "PENDING_SUPERVISOR"}:
        raise _bad("Only a pending request can be cancelled")
    request.status = "CANCELLED"
    await session.flush()
    return await _reload(session, request.id)
