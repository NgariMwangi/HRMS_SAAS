from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import AttendanceRecord, Branch, Employee, LeaveRequest, User

MARK_STATUSES = {"PRESENT", "LATE", "ABSENT"}
OPEN_LEAVE = "APPROVED"


def _bad(detail: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def require_device_id(value: str) -> str:
    device_id = value.strip()
    if len(device_id) < 8 or len(device_id) > 64:
        raise _bad("device_id is required")
    return device_id


def work_date_for_branch(branch: Branch, when: datetime | None = None) -> date:
    instant = when or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    name = (branch.timezone or "UTC").strip() or "UTC"
    try:
        zone = ZoneInfo(name)
    except ZoneInfoNotFoundError:
        zone = timezone.utc
    return instant.astimezone(zone).date()


def to_read(employee: Employee, work_on: date, record: AttendanceRecord | None, on_leave: bool) -> dict:
    status_value = "ON_LEAVE" if on_leave else (record.status if record else "UNMARKED")
    return {
        "employee_id": employee.id,
        "employee_name": " ".join(part for part in (employee.first_name, employee.other_names, employee.last_name) if part),
        "employee_number": employee.employee_number,
        "company_id": employee.company_id,
        "branch_id": employee.branch_id,
        "work_on": work_on,
        "status": status_value,
        "source": None if on_leave else (record.source if record else None),
        "checked_in_at": None if on_leave else (record.checked_in_at if record else None),
        "checked_out_at": None if on_leave else (record.checked_out_at if record else None),
        "note": None if on_leave else (record.note if record else None),
        "on_leave": on_leave,
        "has_clock_device": bool(employee.clock_device_id),
        "clock_login_email": employee.clock_login_email,
        "record_id": None if on_leave else (record.id if record else None),
    }


async def employee_for_user(session: AsyncSession, user: User) -> Employee:
    if user.employee_id is None:
        raise _bad("This login is not linked to an employee record", status.HTTP_403_FORBIDDEN)
    employee = await session.get(Employee, user.employee_id, options=(selectinload(Employee.login_user),))
    if employee is None or employee.status != "ACTIVE":
        raise _bad("Employee clock-in is not available", status.HTTP_403_FORBIDDEN)
    return employee


async def on_leave_ids(session: AsyncSession, employee_ids: list, work_on: date) -> set:
    if not employee_ids:
        return set()
    rows = await session.scalars(
        select(LeaveRequest.employee_id).where(
            LeaveRequest.employee_id.in_(employee_ids),
            LeaveRequest.status == OPEN_LEAVE,
            LeaveRequest.start_on <= work_on,
            LeaveRequest.end_on >= work_on,
        )
    )
    return set(rows.all())


async def assert_device_allowed(session: AsyncSession, employee: Employee, device_id: str, work_on: date) -> None:
    if employee.clock_device_id and employee.clock_device_id != device_id:
        raise _bad(
            "This account is bound to another device. Ask HR to unlock it.",
            status.HTTP_403_FORBIDDEN,
        )
    taken = await session.scalar(
        select(AttendanceRecord.id).where(
            AttendanceRecord.device_id == device_id,
            AttendanceRecord.work_on == work_on,
            AttendanceRecord.employee_id != employee.id,
        )
    )
    if taken is not None:
        raise _bad(
            "This device already clocked in for someone else today.",
            status.HTTP_403_FORBIDDEN,
        )


async def clock_in(session: AsyncSession, user: User, device_id: str) -> dict:
    employee = await employee_for_user(session, user)
    branch = await session.get(Branch, employee.branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    work_on = work_date_for_branch(branch)
    if employee.id in await on_leave_ids(session, [employee.id], work_on):
        raise _bad("Cannot clock in while on approved leave")
    device_id = require_device_id(device_id)
    await assert_device_allowed(session, employee, device_id, work_on)
    record = await session.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.work_on == work_on,
        )
    )
    if record is not None and record.checked_in_at is not None:
        raise _bad("Already clocked in today")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if record is None:
        record = AttendanceRecord(
            company_id=employee.company_id,
            branch_id=employee.branch_id,
            employee_id=employee.id,
            work_on=work_on,
            status="PRESENT",
            source="SELF",
            checked_in_at=now,
            device_id=device_id,
        )
        session.add(record)
    else:
        record.status = "PRESENT"
        record.source = "SELF"
        record.checked_in_at = now
        record.device_id = device_id
        record.checked_out_at = None
    if not employee.clock_device_id:
        employee.clock_device_id = device_id
    await session.flush()
    return to_read(employee, work_on, record, False)


async def clock_out(session: AsyncSession, user: User, device_id: str) -> dict:
    employee = await employee_for_user(session, user)
    branch = await session.get(Branch, employee.branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    work_on = work_date_for_branch(branch)
    device_id = require_device_id(device_id)
    await assert_device_allowed(session, employee, device_id, work_on)
    record = await session.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.work_on == work_on,
        )
    )
    if record is None or record.checked_in_at is None:
        raise _bad("Clock in first")
    if record.checked_out_at is not None:
        raise _bad("Already clocked out today")
    record.checked_out_at = datetime.now(timezone.utc).replace(tzinfo=None)
    record.device_id = device_id
    await session.flush()
    return to_read(employee, work_on, record, False)


async def list_day(
    session: AsyncSession,
    company_id,
    branch_id,
    work_on: date,
) -> list[dict]:
    people = list(
        (
            await session.scalars(
                select(Employee)
                .options(selectinload(Employee.login_user))
                .where(
                    Employee.company_id == company_id,
                    Employee.branch_id == branch_id,
                    Employee.status == "ACTIVE",
                )
                .order_by(Employee.first_name, Employee.last_name)
            )
        ).all()
    )
    records = {
        row.employee_id: row
        for row in (
            await session.scalars(
                select(AttendanceRecord).where(
                    AttendanceRecord.branch_id == branch_id,
                    AttendanceRecord.work_on == work_on,
                )
            )
        ).all()
    }
    leave_ids = await on_leave_ids(session, [row.id for row in people], work_on)
    return [to_read(person, work_on, records.get(person.id), person.id in leave_ids) for person in people]


async def mark_day(session: AsyncSession, employee: Employee, work_on: date, status_value: str, note: str | None) -> dict:
    status_value = status_value.upper()
    if status_value not in MARK_STATUSES:
        raise _bad("status must be PRESENT, LATE, or ABSENT")
    if employee.id in await on_leave_ids(session, [employee.id], work_on):
        raise _bad("This person is on approved leave")
    record = await session.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.work_on == work_on,
        )
    )
    if record is None:
        record = AttendanceRecord(
            company_id=employee.company_id,
            branch_id=employee.branch_id,
            employee_id=employee.id,
            work_on=work_on,
            status=status_value,
            source="HR",
            note=note,
        )
        if status_value == "ABSENT":
            record.checked_in_at = None
            record.checked_out_at = None
        session.add(record)
    else:
        record.status = status_value
        record.source = "HR"
        record.note = note
        if status_value == "ABSENT":
            record.checked_in_at = None
            record.checked_out_at = None
    await session.flush()
    return to_read(employee, work_on, record, False)
