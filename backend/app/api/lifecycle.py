import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer

from app.api.org import (
    END_DATE_EMPLOYMENT_TYPES,
    blank_to_none,
    branch_for_company,
    next_employee_number,
    optional_department_for_company,
    optional_job_title_for_company,
    require_employment_period,
    require_employment_type,
)
from app.models import Employee, EmployeeLifecycleAttachment, EmployeeLifecycleEvent
from app.schemas.employee import (
    LifecycleActionCreate,
    LifecycleActionResult,
    LifecycleAttachmentRead,
    LifecycleEventRead,
)

CLIENT_EVENTS = {"SUSPENDED", "REINSTATED", "ROLE_CHANGED", "TERMINATED", "REHIRED", "EXTENDED"}
ALLOWED_FROM = {
    "SUSPENDED": {"ACTIVE"},
    "REINSTATED": {"SUSPENDED"},
    "ROLE_CHANGED": {"ACTIVE"},
    "TERMINATED": {"ACTIVE", "SUSPENDED"},
    "REHIRED": {"TERMINATED"},
    "EXTENDED": {"ACTIVE", "SUSPENDED"},
}
ROLE_REASONS = {"PROMOTION", "DEMOTION", "TITLE_CHANGE", "DEPARTMENT_CHANGE"}
REHIRE_MODES = {"SAME_RECORD", "NEW_RECORD"}
ATTACHABLE_EVENTS = {"SUSPENDED", "ROLE_CHANGED", "TERMINATED", "EXTENDED"}
ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
}
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024
MAX_ATTACHMENTS = 5
PAY_TREATMENTS = {"WITH_PAY", "WITHOUT_PAY", "PARTIAL"}
EXTENDABLE_TYPES = {"INTERN", "CONTRACT"}
EXTEND_REASONS = {"DAYS", "UNTIL_DATE"}


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def event_to_read(event: EmployeeLifecycleEvent, employee: Employee | None = None) -> LifecycleEventRead:
    person = employee
    return LifecycleEventRead(
        id=event.id,
        company_id=event.company_id,
        employee_id=event.employee_id,
        event_type=event.event_type,
        reason=event.reason,
        effective_on=event.effective_on,
        note=event.note,
        from_department_id=event.from_department_id,
        to_department_id=event.to_department_id,
        from_job_title_id=event.from_job_title_id,
        to_job_title_id=event.to_job_title_id,
        from_branch_id=event.from_branch_id,
        to_branch_id=event.to_branch_id,
        related_employee_id=event.related_employee_id,
        created_by=event.created_by,
        created_at=event.created_at,
        pay_treatment=event.pay_treatment,
        pay_deduction_percent=event.pay_deduction_percent,
        from_date_ended=event.from_date_ended,
        to_date_ended=event.to_date_ended,
        extension_days=event.extension_days,
        employment_type=event.employment_type or (person.employment_type if person else None),
        employee_number=person.employee_number if person else None,
        employee_name=(
            " ".join(part for part in [person.first_name, person.other_names, person.last_name] if part)
            if person
            else None
        ),
        attachments=[
            LifecycleAttachmentRead(
                id=item.id,
                filename=item.filename,
                content_type=item.content_type,
            )
            for item in event.__dict__.get("attachments") or []
        ],
    )


def _require_reason(value: str | None, label: str) -> str:
    reason = (value or "").strip()
    if not reason:
        raise _bad(f"{label} needs a reason")
    return reason[:80]


def _clear_suspension_pay(employee: Employee) -> None:
    employee.suspension_pay_treatment = None
    employee.suspension_pay_deduction_percent = None


def _extend_period(employee: Employee, payload: LifecycleActionCreate) -> tuple[str, date | None, date, int | None]:
    if employee.employment_type not in EXTENDABLE_TYPES:
        raise _bad("Only intern and contract records can be extended")
    reason = (payload.reason or "").upper().replace("-", "_").replace(" ", "_")
    if reason not in EXTEND_REASONS:
        raise _bad("Choose to extend by a number of days or until a specific date")
    previous = employee.date_ended
    if reason == "DAYS":
        days = payload.extension_days
        if days is None or days < 1:
            raise _bad("Enter how many days to extend")
        new_end = (previous or payload.effective_on) + timedelta(days=days)
    else:
        new_end = payload.date_ended
        if new_end is None:
            raise _bad("Pick the new end date")
        days = (new_end - (previous or payload.effective_on)).days
        if days < 1:
            days = None
    if previous is not None and new_end <= previous:
        raise _bad("The new end date must be after the current end date")
    if employee.date_joined is not None and new_end < employee.date_joined:
        raise _bad("End date must be on or after the start date")
    return reason, previous, new_end, days


def _suspension_pay(payload: LifecycleActionCreate) -> tuple[str, Decimal]:
    treatment = (payload.pay_treatment or "").upper().replace("-", "_").replace(" ", "_")
    if treatment not in PAY_TREATMENTS:
        raise _bad("Suspension pay must be with pay, without pay, or a deducted percentage")
    if treatment == "WITH_PAY":
        return treatment, Decimal("0")
    if treatment == "WITHOUT_PAY":
        return treatment, Decimal("100")
    percent = payload.pay_deduction_percent
    if percent is None:
        raise _bad("Enter the percentage to deduct during this suspension")
    if percent <= 0 or percent >= 100:
        raise _bad("A deducted percentage must be more than 0 and less than 100")
    return treatment, percent.quantize(Decimal("0.01"))


def build_event(
    employee: Employee,
    event_type: str,
    *,
    reason: str | None,
    effective_on: date,
    note: str | None,
    created_by: uuid.UUID | None,
    from_department_id: uuid.UUID | None = None,
    to_department_id: uuid.UUID | None = None,
    from_job_title_id: uuid.UUID | None = None,
    to_job_title_id: uuid.UUID | None = None,
    from_branch_id: uuid.UUID | None = None,
    to_branch_id: uuid.UUID | None = None,
    related_employee_id: uuid.UUID | None = None,
    pay_treatment: str | None = None,
    pay_deduction_percent: Decimal | None = None,
    from_date_ended: date | None = None,
    to_date_ended: date | None = None,
    extension_days: int | None = None,
    employment_type: str | None = None,
) -> EmployeeLifecycleEvent:
    return EmployeeLifecycleEvent(
        company_id=employee.company_id,
        employee_id=employee.id,
        event_type=event_type,
        reason=reason,
        effective_on=effective_on,
        note=blank_to_none(note) if isinstance(note, str) else note,
        from_department_id=from_department_id,
        to_department_id=to_department_id,
        from_job_title_id=from_job_title_id,
        to_job_title_id=to_job_title_id,
        from_branch_id=from_branch_id,
        to_branch_id=to_branch_id,
        related_employee_id=related_employee_id,
        created_by=created_by,
        pay_treatment=pay_treatment,
        pay_deduction_percent=pay_deduction_percent,
        from_date_ended=from_date_ended,
        to_date_ended=to_date_ended,
        extension_days=extension_days,
        employment_type=employment_type,
    )


async def record_hired(
    session: AsyncSession,
    employee: Employee,
    created_by: uuid.UUID | None = None,
) -> EmployeeLifecycleEvent:
    event = build_event(
        employee,
        "HIRED",
        reason=None,
        effective_on=employee.date_joined or date.today(),
        note=None,
        created_by=created_by,
        to_department_id=employee.department_id,
        to_job_title_id=employee.job_title_id,
        to_branch_id=employee.branch_id,
        related_employee_id=employee.previous_employee_id,
    )
    session.add(event)
    await session.flush()
    return event


async def _prepare_role(
    session: AsyncSession,
    employee: Employee,
    payload: LifecycleActionCreate,
    required: bool,
) -> tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID | None]:
    department_id = employee.department_id
    job_title_id = employee.job_title_id
    branch_id = employee.branch_id
    if payload.department_id is not None:
        department_id = payload.department_id
        await optional_department_for_company(session, department_id, employee.company_id)
    if payload.job_title_id is not None:
        job_title_id = payload.job_title_id
        await optional_job_title_for_company(session, job_title_id, employee.company_id)
    if payload.branch_id is not None:
        branch_id = payload.branch_id
        await branch_for_company(session, branch_id, employee.company_id)
    if required:
        changed = (
            department_id != employee.department_id
            or job_title_id != employee.job_title_id
            or branch_id != employee.branch_id
        )
        if not changed:
            raise _bad("Role change must update the title, department, or branch")
    return department_id, job_title_id, branch_id


def _rehire_employment(
    employee: Employee,
    payload: LifecycleActionCreate,
    *,
    new_record: bool,
) -> tuple[str, date | None, date | None]:
    fallback_type = employee.employment_type if (not new_record or payload.copy_from_previous) else "FULL_TIME"
    employment_type = require_employment_type(payload.employment_type or fallback_type)
    if new_record:
        date_joined = payload.date_joined or payload.effective_on
    else:
        date_joined = payload.date_joined if payload.date_joined is not None else employee.date_joined
    if employment_type not in END_DATE_EMPLOYMENT_TYPES:
        return employment_type, date_joined, None
    require_employment_period(employment_type, date_joined, payload.date_ended)
    return employment_type, date_joined, payload.date_ended


async def _rehire_new_record(
    session: AsyncSession,
    employee: Employee,
    payload: LifecycleActionCreate,
    created_by: uuid.UUID | None,
) -> tuple[EmployeeLifecycleEvent, Employee]:
    copy = payload.copy_from_previous
    first_name = (payload.first_name or (employee.first_name if copy else "")).strip()
    last_name = (payload.last_name or (employee.last_name if copy else "")).strip()
    if not first_name or not last_name:
        raise _bad("A new employee record needs a first and last name")

    department_id = payload.department_id if payload.department_id is not None else (employee.department_id if copy else None)
    job_title_id = payload.job_title_id if payload.job_title_id is not None else (employee.job_title_id if copy else None)
    branch_id = payload.branch_id or employee.branch_id
    await branch_for_company(session, branch_id, employee.company_id)
    await optional_department_for_company(session, department_id, employee.company_id)
    await optional_job_title_for_company(session, job_title_id, employee.company_id)

    employment_type, date_joined, date_ended = _rehire_employment(employee, payload, new_record=True)

    email = payload.email
    if email is None and copy:
        email = employee.email
    if isinstance(email, str):
        email = email.strip().lower() or None
    personal_email = payload.personal_email
    if personal_email is None and copy:
        personal_email = employee.personal_email
    if isinstance(personal_email, str):
        personal_email = personal_email.strip().lower() or None

    if email and email == employee.email:
        employee.email = None
        await session.flush()

    number = blank_to_none(payload.employee_number) or await next_employee_number(session, employee.company_id)
    if number == employee.employee_number:
        raise _bad("A new record cannot reuse the same employee number")

    new_employee = Employee(
        company_id=employee.company_id,
        branch_id=branch_id,
        department_id=department_id,
        job_title_id=job_title_id,
        employee_number=number,
        first_name=first_name,
        other_names=blank_to_none(payload.other_names) if payload.other_names is not None else (employee.other_names if copy else None),
        last_name=last_name,
        date_of_birth=payload.date_of_birth if payload.date_of_birth is not None else (employee.date_of_birth if copy else None),
        email=email,
        personal_email=personal_email,
        phone=blank_to_none(payload.phone) if payload.phone is not None else (employee.phone if copy else None),
        other_phone=blank_to_none(payload.other_phone) if payload.other_phone is not None else (employee.other_phone if copy else None),
        id_number=employee.id_number if copy else None,
        nssf_no=employee.nssf_no if copy else None,
        shif_no=employee.shif_no if copy else None,
        employment_type=employment_type,
        date_joined=date_joined,
        date_ended=date_ended,
        status="ACTIVE",
        previous_employee_id=employee.id,
    )
    session.add(new_employee)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Employee number or email already exists for this company",
        ) from exc

    await record_hired(session, new_employee, created_by)
    marker = build_event(
        employee,
        "REHIRED",
        reason="NEW_RECORD",
        effective_on=payload.effective_on,
        note=payload.note,
        created_by=created_by,
        related_employee_id=new_employee.id,
        from_department_id=employee.department_id,
        to_department_id=new_employee.department_id,
        from_job_title_id=employee.job_title_id,
        to_job_title_id=new_employee.job_title_id,
        from_branch_id=employee.branch_id,
        to_branch_id=new_employee.branch_id,
    )
    session.add(marker)
    await session.flush()
    return marker, new_employee


async def apply_lifecycle_action(
    session: AsyncSession,
    employee: Employee,
    payload: LifecycleActionCreate,
    created_by: uuid.UUID | None,
) -> LifecycleActionResult:
    event_type = payload.event_type.upper().replace("-", "_").replace(" ", "_")
    if event_type not in CLIENT_EVENTS:
        raise _bad("event_type must be SUSPENDED, REINSTATED, ROLE_CHANGED, TERMINATED, REHIRED, or EXTENDED")
    if employee.status not in ALLOWED_FROM[event_type]:
        raise _bad(f"Cannot apply {event_type} while the employee is {employee.status}")

    new_employee: Employee | None = None
    if event_type == "SUSPENDED":
        reason = _require_reason(payload.reason, "Suspension")
        pay_treatment, pay_percent = _suspension_pay(payload)
        employee.status = "SUSPENDED"
        employee.suspension_pay_treatment = pay_treatment
        employee.suspension_pay_deduction_percent = pay_percent
        event = build_event(
            employee,
            event_type,
            reason=reason,
            effective_on=payload.effective_on,
            note=payload.note,
            created_by=created_by,
            pay_treatment=pay_treatment,
            pay_deduction_percent=pay_percent,
        )
    elif event_type == "REINSTATED":
        reason = _require_reason(payload.reason, "Reinstatement")
        employee.status = "ACTIVE"
        _clear_suspension_pay(employee)
        event = build_event(
            employee,
            event_type,
            reason=reason,
            effective_on=payload.effective_on,
            note=payload.note,
            created_by=created_by,
        )
    elif event_type == "TERMINATED":
        reason = _require_reason(payload.reason, "Termination")
        employee.status = "TERMINATED"
        employee.date_ended = payload.effective_on
        _clear_suspension_pay(employee)
        event = build_event(
            employee,
            event_type,
            reason=reason,
            effective_on=payload.effective_on,
            note=payload.note,
            created_by=created_by,
        )
    elif event_type == "ROLE_CHANGED":
        reason = (payload.reason or "").upper().replace("-", "_").replace(" ", "_")
        if reason not in ROLE_REASONS:
            raise _bad("Role change reason must be PROMOTION, DEMOTION, TITLE_CHANGE, or DEPARTMENT_CHANGE")
        department_id, job_title_id, branch_id = await _prepare_role(session, employee, payload, True)
        event = build_event(
            employee,
            event_type,
            reason=reason,
            effective_on=payload.effective_on,
            note=payload.note,
            created_by=created_by,
            from_department_id=employee.department_id,
            to_department_id=department_id,
            from_job_title_id=employee.job_title_id,
            to_job_title_id=job_title_id,
            from_branch_id=employee.branch_id,
            to_branch_id=branch_id,
        )
        employee.department_id = department_id
        employee.job_title_id = job_title_id
        employee.branch_id = branch_id
    elif event_type == "EXTENDED":
        reason, previous_end, new_end, days = _extend_period(employee, payload)
        event = build_event(
            employee,
            event_type,
            reason=reason,
            effective_on=payload.effective_on,
            note=payload.note,
            created_by=created_by,
            from_date_ended=previous_end,
            to_date_ended=new_end,
            extension_days=days,
            employment_type=employee.employment_type,
        )
        employee.date_ended = new_end
    else:
        mode = (payload.rehire_mode or "SAME_RECORD").upper().replace("-", "_")
        if mode not in REHIRE_MODES:
            raise _bad("rehire_mode must be SAME_RECORD or NEW_RECORD")
        if mode == "NEW_RECORD":
            event, new_employee = await _rehire_new_record(session, employee, payload, created_by)
        else:
            department_id, job_title_id, branch_id = await _prepare_role(session, employee, payload, False)
            employment_type, date_joined, date_ended = _rehire_employment(employee, payload, new_record=False)
            employee.status = "ACTIVE"
            employee.employment_type = employment_type
            employee.date_joined = date_joined
            employee.date_ended = date_ended
            _clear_suspension_pay(employee)
            event = build_event(
                employee,
                event_type,
                reason="SAME_RECORD",
                effective_on=payload.effective_on,
                note=payload.note,
                created_by=created_by,
                from_department_id=employee.department_id,
                to_department_id=department_id,
                from_job_title_id=employee.job_title_id,
                to_job_title_id=job_title_id,
                from_branch_id=employee.branch_id,
                to_branch_id=branch_id,
            )
            employee.department_id = department_id
            employee.job_title_id = job_title_id
            employee.branch_id = branch_id

    if new_employee is None:
        session.add(event)
        await session.flush()
    await session.refresh(employee)
    if new_employee is not None:
        await session.refresh(new_employee)
    return LifecycleActionResult(
        event=event_to_read(event, employee),
        employee=employee,
        new_employee=new_employee,
    )


async def list_employee_events(
    session: AsyncSession,
    employee_id: uuid.UUID,
) -> list[tuple[EmployeeLifecycleEvent, Employee]]:
    rows = (
        await session.execute(
            select(EmployeeLifecycleEvent, Employee)
            .options(selectinload(EmployeeLifecycleEvent.attachments))
            .join(Employee, Employee.id == EmployeeLifecycleEvent.employee_id)
            .where(EmployeeLifecycleEvent.employee_id == employee_id)
            .order_by(EmployeeLifecycleEvent.effective_on.desc(), EmployeeLifecycleEvent.created_at.desc())
        )
    ).all()
    return [(event, person) for event, person in rows]


async def list_company_events(
    session: AsyncSession,
    company_id: uuid.UUID,
    event_type: str | None = None,
    q: str | None = None,
) -> list[tuple[EmployeeLifecycleEvent, Employee]]:
    stmt = (
        select(EmployeeLifecycleEvent, Employee)
        .options(selectinload(EmployeeLifecycleEvent.attachments))
        .join(Employee, Employee.id == EmployeeLifecycleEvent.employee_id)
        .where(EmployeeLifecycleEvent.company_id == company_id)
        .order_by(EmployeeLifecycleEvent.effective_on.desc(), EmployeeLifecycleEvent.created_at.desc())
    )
    if event_type:
        stmt = stmt.where(EmployeeLifecycleEvent.event_type == event_type.upper())
    if q and q.strip():
        term = f"%{q.strip()}%"
        full_name = func.concat_ws(" ", Employee.first_name, Employee.other_names, Employee.last_name)
        stmt = stmt.where(
            or_(
                Employee.first_name.ilike(term),
                Employee.other_names.ilike(term),
                Employee.last_name.ilike(term),
                full_name.ilike(term),
                Employee.employee_number.ilike(term),
            )
        )
    rows = (await session.execute(stmt)).all()
    return [(event, person) for event, person in rows]


async def event_for_employee(
    session: AsyncSession,
    event_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> EmployeeLifecycleEvent:
    event = await session.scalar(
        select(EmployeeLifecycleEvent)
        .options(selectinload(EmployeeLifecycleEvent.attachments))
        .where(
            EmployeeLifecycleEvent.id == event_id,
            EmployeeLifecycleEvent.employee_id == employee_id,
        )
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lifecycle event not found")
    return event


async def add_event_attachments(
    session: AsyncSession,
    event: EmployeeLifecycleEvent,
    files: list[UploadFile],
) -> list[EmployeeLifecycleAttachment]:
    if event.event_type not in ATTACHABLE_EVENTS:
        raise _bad("Documents can only be attached to suspend, role change, terminate, or extend")
    incoming = [item for item in files if item.filename]
    if not incoming:
        raise _bad("Attach at least one document")
    existing = len(event.attachments)
    if existing + len(incoming) > MAX_ATTACHMENTS:
        raise _bad(f"At most {MAX_ATTACHMENTS} documents can be attached to one action")

    saved: list[EmployeeLifecycleAttachment] = []
    for upload in incoming:
        content_type = (upload.content_type or "").lower()
        if content_type not in ALLOWED_ATTACHMENT_TYPES:
            raise _bad("Documents must be PDF, Word, image, or text files")
        data = await upload.read()
        if not data or len(data) > MAX_ATTACHMENT_BYTES:
            raise _bad("Each document must be 50 MB or smaller")
        filename = (upload.filename or "document").rsplit("/", 1)[-1][:255]
        row = EmployeeLifecycleAttachment(
            company_id=event.company_id,
            employee_id=event.employee_id,
            event_id=event.id,
            filename=filename,
            content_type=content_type,
            file_bytes=data,
        )
        session.add(row)
        saved.append(row)
    await session.flush()
    for row in saved:
        await session.refresh(row)
    return saved


async def attachment_file(
    session: AsyncSession,
    event_id: uuid.UUID,
    employee_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> EmployeeLifecycleAttachment:
    row = await session.scalar(
        select(EmployeeLifecycleAttachment)
        .options(undefer(EmployeeLifecycleAttachment.file_bytes))
        .where(
            EmployeeLifecycleAttachment.id == attachment_id,
            EmployeeLifecycleAttachment.event_id == event_id,
            EmployeeLifecycleAttachment.employee_id == employee_id,
        )
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return row
