from app.api.access_control import employee_scope, require_access, require_employee_access
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer

from app.api.deps import get_current_user, get_tenant_db, get_tenant_id
from app.api.lifecycle import (
    add_event_attachments,
    apply_lifecycle_action,
    attachment_file,
    event_for_employee,
    event_to_read,
    list_employee_events,
    record_hired,
)
from app.api.documents import (
    add_employee_document,
    employee_document_file,
    list_company_documents,
    parse_optional_date,
)
from app.api.next_of_kin import list_next_of_kin, replace_next_of_kin
from app.api.supervisors import list_supervisors, replace_supervisors
from app.api.org import (
    END_DATE_EMPLOYMENT_TYPES,
    blank_to_none,
    branch_for_company,
    company_for_tenant,
    next_employee_number,
    optional_department_for_company,
    optional_job_title_for_company,
    require_employment_period,
    require_employment_type,
)
from app.core.security import hash_password
from app.models import Company, Employee, EmployeeDocument, EmployeeNextOfKin, User
from app.schemas.attendance import EmployeeLoginCreate
from app.schemas.auth import UserRead
from app.schemas.document import CompanyDocumentRead
from app.schemas.employee import (
    EmployeeSummaryRead,
    EmployeeCreate,
    EmployeeRead,
    EmployeeUpdate,
    LifecycleActionCreate,
    LifecycleActionResult,
    LifecycleAttachmentRead,
    LifecycleEventRead,
    NextOfKinRead,
    NextOfKinReplace,
    SupervisorRead,
    SupervisorReplace,
)

router = APIRouter(prefix="/employees", tags=["employees"])

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_BYTES = 10 * 1024 * 1024
_STATUTORY_FIELDS = ("id_number", "nssf_no", "shif_no")


def _employee_conflict(exc: IntegrityError) -> HTTPException:
    orig = str(getattr(exc, "orig", exc)).lower()
    if "uq_employee_id_number_open" in orig:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active employee already has this ID no.")
    if "uq_employee_nssf_no_open" in orig:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active employee already has this NSSF no.")
    if "uq_employee_shif_no_open" in orig:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An active employee already has this SHIF no.")
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Employee number or email already exists for this company",
    )


def _normalize(data: dict) -> dict:
    data.pop("status", None)
    data.pop("next_of_kin", None)
    data.pop("supervisor_ids", None)
    if "employment_type" in data and data["employment_type"] is not None:
        data["employment_type"] = require_employment_type(data["employment_type"])
    if "employee_number" in data:
        data["employee_number"] = blank_to_none(data["employee_number"])
    if "phone" in data:
        data["phone"] = blank_to_none(data["phone"])
    if "other_phone" in data:
        data["other_phone"] = blank_to_none(data["other_phone"])
    if "first_name" in data and data["first_name"] is not None:
        data["first_name"] = data["first_name"].strip()
    if "other_names" in data:
        data["other_names"] = blank_to_none(data["other_names"])
    if "last_name" in data and data["last_name"] is not None:
        data["last_name"] = data["last_name"].strip()
    for field in _STATUTORY_FIELDS:
        if field in data:
            data[field] = blank_to_none(data[field])
    if "email" in data and isinstance(data["email"], str):
        data["email"] = data["email"].strip().lower() or None
    if "personal_email" in data and isinstance(data["personal_email"], str):
        data["personal_email"] = data["personal_email"].strip().lower() or None
    return data


@router.post("", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_access('people.manage'))])
async def create_employee(
    payload: EmployeeCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> Employee:
    await company_for_tenant(session, payload.company_id, tenant_id)
    await branch_for_company(session, payload.branch_id, payload.company_id)
    await optional_department_for_company(session, payload.department_id, payload.company_id)
    await optional_job_title_for_company(session, payload.job_title_id, payload.company_id)

    data = _normalize(payload.model_dump())
    if data["employment_type"] not in END_DATE_EMPLOYMENT_TYPES:
        data["date_ended"] = None
    require_employment_period(
        data["employment_type"], data.get("date_joined"), data.get("date_ended")
    )
    if not data.get("employee_number"):
        data["employee_number"] = await next_employee_number(session, payload.company_id)
    data["status"] = "ACTIVE"

    employee = Employee(**data)
    session.add(employee)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _employee_conflict(exc) from exc
    await record_hired(session, employee, user.id)
    await replace_next_of_kin(session, employee, payload.next_of_kin)
    await replace_supervisors(session, employee, payload.supervisor_ids)
    await session.refresh(employee)
    return employee


@router.get("", response_model=list[EmployeeRead], dependencies=[Depends(require_access('people.view_all', 'people.view_own', 'people.view_team', 'people.manage'))])
async def list_employees(
    company_id: uuid.UUID | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None),
    department_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[Employee]:
    stmt = (
        select(Employee)
        .options(selectinload(Employee.login_user))
        .join(Company, Employee.company_id == Company.id)
        .where(Company.tenant_id == tenant_id, await employee_scope(session, user))
        .order_by(Employee.last_name, Employee.first_name)
    )
    if company_id is not None:
        await company_for_tenant(session, company_id, tenant_id)
        stmt = stmt.where(Employee.company_id == company_id)
    if branch_id is not None:
        stmt = stmt.where(Employee.branch_id == branch_id)
    if department_id is not None:
        stmt = stmt.where(Employee.department_id == department_id)
    status_filter = (status or "").upper()
    if status_filter == "ALL":
        pass
    elif status_filter in {"ACTIVE", "SUSPENDED", "TERMINATED"}:
        stmt = stmt.where(Employee.status == status_filter)
    else:
        stmt = stmt.where(Employee.status.in_(("ACTIVE", "SUSPENDED")))
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Employee.first_name.ilike(term),
                Employee.other_names.ilike(term),
                Employee.last_name.ilike(term),
                Employee.email.ilike(term),
                Employee.personal_email.ilike(term),
                Employee.phone.ilike(term),
                Employee.other_phone.ilike(term),
                Employee.employee_number.ilike(term),
                Employee.id_number.ilike(term),
                Employee.nssf_no.ilike(term),
                Employee.shif_no.ilike(term),
            )
        )
    result = await session.scalars(stmt)
    return list(result.all())


@router.get("/{employee_id}", response_model=EmployeeRead, dependencies=[Depends(require_employee_access('people'))])
async def get_employee(
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Employee:
    employee = await session.get(Employee, employee_id, options=(selectinload(Employee.login_user),))
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )
    await company_for_tenant(session, employee.company_id, tenant_id)
    return employee


@router.post("/{employee_id}/login", response_model=UserRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_access('people.manage'))])
async def create_employee_login(
    employee_id: uuid.UUID,
    payload: EmployeeLoginCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> User:
    employee = await session.get(Employee, employee_id, options=(selectinload(Employee.login_user),))
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    if employee.login_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This employee already has a login")
    login = User(
        tenant_id=tenant_id,
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        full_name=(payload.full_name or f"{employee.first_name} {employee.last_name}").strip(),
        role="EMPLOYEE",
        status="ACTIVE",
        employee_id=employee.id,
    )
    session.add(login)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    await session.refresh(login)
    return login


@router.post("/{employee_id}/clock-device/reset", response_model=EmployeeRead, dependencies=[Depends(require_access('attendance.manage'))])
async def reset_clock_device(
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> Employee:
    employee = await session.get(Employee, employee_id, options=(selectinload(Employee.login_user),))
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    employee.clock_device_id = None
    await session.flush()
    return await session.get(
        Employee,
        employee.id,
        options=(selectinload(Employee.login_user),),
        populate_existing=True,
    )


@router.patch("/{employee_id}", response_model=EmployeeRead, dependencies=[Depends(require_access('people.manage'))])
async def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Employee:
    employee = await session.get(Employee, employee_id, options=(selectinload(Employee.login_user),))
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )
    await company_for_tenant(session, employee.company_id, tenant_id)
    updates = _normalize(payload.model_dump(exclude_unset=True))
    employment_type = updates.get("employment_type", employee.employment_type)
    if employment_type not in END_DATE_EMPLOYMENT_TYPES and (
        "employment_type" in updates or "date_ended" in updates
    ):
        updates["date_ended"] = None
    require_employment_period(
        employment_type,
        updates["date_joined"] if "date_joined" in updates else employee.date_joined,
        updates["date_ended"] if "date_ended" in updates else employee.date_ended,
    )
    if "branch_id" in updates and updates["branch_id"] is not None:
        await branch_for_company(session, updates["branch_id"], employee.company_id)
    if "department_id" in updates:
        await optional_department_for_company(
            session, updates["department_id"], employee.company_id
        )
    if "job_title_id" in updates:
        await optional_job_title_for_company(
            session, updates["job_title_id"], employee.company_id
        )
    for field, value in updates.items():
        setattr(employee, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _employee_conflict(exc) from exc
    if "next_of_kin" in payload.model_fields_set:
        await replace_next_of_kin(session, employee, payload.next_of_kin)
    if "supervisor_ids" in payload.model_fields_set:
        await replace_supervisors(session, employee, payload.supervisor_ids)
    await session.refresh(employee)
    return await session.get(
        Employee,
        employee.id,
        options=(selectinload(Employee.login_user),),
        populate_existing=True,
    )


@router.get("/{employee_id}/supervisors", response_model=list[SupervisorRead], dependencies=[Depends(require_employee_access('people', 'leave'))])
async def get_employee_supervisors(
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[Employee]:
    employee = await _visible_employee(session, employee_id, tenant_id)
    return await list_supervisors(session, employee.id)


@router.put("/{employee_id}/supervisors", response_model=list[SupervisorRead], dependencies=[Depends(require_access('people.manage'))])
async def put_employee_supervisors(
    employee_id: uuid.UUID,
    payload: SupervisorReplace,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[Employee]:
    employee = await _visible_employee(session, employee_id, tenant_id)
    return await replace_supervisors(session, employee, payload.supervisor_ids)


@router.get("/{employee_id}/next-of-kin", response_model=list[NextOfKinRead], dependencies=[Depends(require_employee_access('people'))])
async def get_employee_next_of_kin(
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[EmployeeNextOfKin]:
    employee = await _visible_employee(session, employee_id, tenant_id)
    return await list_next_of_kin(session, employee.id)


@router.put("/{employee_id}/next-of-kin", response_model=list[NextOfKinRead], dependencies=[Depends(require_access('people.manage'))])
async def put_employee_next_of_kin(
    employee_id: uuid.UUID,
    payload: NextOfKinReplace,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[EmployeeNextOfKin]:
    employee = await _visible_employee(session, employee_id, tenant_id)
    return await replace_next_of_kin(session, employee, payload.items)


@router.get("/{employee_id}/documents", response_model=list[CompanyDocumentRead], dependencies=[Depends(require_employee_access('documents'))])
async def get_employee_documents(
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[CompanyDocumentRead]:
    employee = await _visible_employee(session, employee_id, tenant_id)
    return await list_company_documents(
        session, employee.company_id, employee_id=employee.id
    )


@router.post("/{employee_id}/documents", response_model=CompanyDocumentRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_access('documents.manage'))])
async def upload_employee_document(
    employee_id: uuid.UUID,
    category_id: uuid.UUID = Form(),
    issued_on: str | None = Form(default=None),
    expires_on: str | None = Form(default=None),
    note: str | None = Form(default=None),
    file: UploadFile = File(...),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> CompanyDocumentRead:
    employee = await _visible_employee(session, employee_id, tenant_id)
    return await add_employee_document(
        session,
        employee,
        upload=file,
        category_id=category_id,
        issued_on=parse_optional_date(issued_on),
        expires_on=parse_optional_date(expires_on),
        note=note,
        uploaded_by=user.id,
    )


@router.get("/{employee_id}/documents/{document_id}", dependencies=[Depends(require_employee_access('documents'))])
async def download_employee_document(
    employee_id: uuid.UUID,
    document_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> Response:
    await _visible_employee(session, employee_id, tenant_id)
    from app.models.performance import GoalEvidence, PerformanceGoal
    from app.services.performance import appraisal_context
    link = await session.scalar(select(GoalEvidence).where(GoalEvidence.document_id == document_id, GoalEvidence.tenant_id == tenant_id))
    if link:
        goal = await session.get(PerformanceGoal, link.goal_id)
        await appraisal_context(session, user, goal.appraisal_id)
    row = await employee_document_file(session, employee_id, document_id)
    return Response(
        content=row.file_bytes,
        media_type=row.content_type,
        headers={"Content-Disposition": f'attachment; filename="{row.filename.replace(chr(34), "")}"'},
    )


@router.delete("/{employee_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_access('documents.manage'))])
async def delete_employee_document(
    employee_id: uuid.UUID,
    document_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> None:
    await _visible_employee(session, employee_id, tenant_id)
    row = await session.get(EmployeeDocument, document_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    from app.api.documents import protect_performance_evidence
    await protect_performance_evidence(session, document_id)
    await session.delete(row)
    await session.flush()


@router.get("/{employee_id}/lifecycle", response_model=list[LifecycleEventRead], dependencies=[Depends(require_employee_access('lifecycle'))])
async def get_employee_lifecycle(
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[LifecycleEventRead]:
    employee = await _visible_employee(session, employee_id, tenant_id)
    rows = await list_employee_events(session, employee.id)
    return [event_to_read(event, person) for event, person in rows]


@router.post("/{employee_id}/lifecycle", response_model=LifecycleActionResult, dependencies=[Depends(require_access('lifecycle.manage'))])
async def post_employee_lifecycle(
    employee_id: uuid.UUID,
    payload: LifecycleActionCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> LifecycleActionResult:
    employee = await _visible_employee(session, employee_id, tenant_id)
    return await apply_lifecycle_action(session, employee, payload, user.id)


@router.post("/{employee_id}/lifecycle/{event_id}/attachments", response_model=list[LifecycleAttachmentRead], dependencies=[Depends(require_access('lifecycle.manage'))])
async def upload_lifecycle_attachments(
    employee_id: uuid.UUID,
    event_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[LifecycleAttachmentRead]:
    await _visible_employee(session, employee_id, tenant_id)
    event = await event_for_employee(session, event_id, employee_id)
    rows = await add_event_attachments(session, event, files)
    return [
        LifecycleAttachmentRead(id=row.id, filename=row.filename, content_type=row.content_type)
        for row in rows
    ]


@router.get("/{employee_id}/lifecycle/{event_id}/attachments/{attachment_id}", dependencies=[Depends(require_employee_access('lifecycle'))])
async def download_lifecycle_attachment(
    employee_id: uuid.UUID,
    event_id: uuid.UUID,
    attachment_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Response:
    await _visible_employee(session, employee_id, tenant_id)
    row = await attachment_file(session, event_id, employee_id, attachment_id)
    return Response(
        content=row.file_bytes,
        media_type=row.content_type,
        headers={"Content-Disposition": f'attachment; filename="{row.filename.replace(chr(34), "")}"'},
    )


async def _visible_employee(
    session: AsyncSession,
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Employee:
    employee = await session.get(Employee, employee_id, options=(selectinload(Employee.login_user),))
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )
    await company_for_tenant(session, employee.company_id, tenant_id)
    return employee


@router.get("/{employee_id}/summary", response_model=EmployeeSummaryRead)
async def employee_summary(
    employee_id: uuid.UUID,
    area: Literal["documents", "payroll"],
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> Employee:
    employee = await session.scalar(select(Employee).where(
        Employee.id == employee_id, await employee_scope(session, user, area),
        Employee.company_id.in_(select(Company.id).where(Company.tenant_id == user.tenant_id)),
    ))
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return employee


@router.put("/{employee_id}/photo", response_model=EmployeeRead, dependencies=[Depends(require_access('people.manage'))])
async def upload_employee_photo(
    employee_id: uuid.UUID,
    file: UploadFile = File(...),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Employee:
    employee = await _visible_employee(session, employee_id, tenant_id)
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_PHOTO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passport photo must be a JPEG, PNG, or WebP image",
        )
    data = await file.read()
    if not data or len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passport photo must be 10 MB or smaller",
        )
    employee.photo_bytes = data
    employee.photo_content_type = content_type
    await session.flush()
    return await session.get(
        Employee,
        employee.id,
        options=(selectinload(Employee.login_user),),
        populate_existing=True,
    )


@router.get("/{employee_id}/photo", dependencies=[Depends(require_employee_access('people'))])
async def get_employee_photo(
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Response:
    employee = await session.scalar(
        select(Employee)
        .options(undefer(Employee.photo_bytes))
        .where(Employee.id == employee_id)
    )
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
        )
    await company_for_tenant(session, employee.company_id, tenant_id)
    if not employee.photo_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Passport photo not found"
        )
    return Response(
        content=employee.photo_bytes,
        media_type=employee.photo_content_type or "application/octet-stream",
    )


@router.delete("/{employee_id}/photo", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_access('people.manage'))])
async def delete_employee_photo(
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> None:
    employee = await _visible_employee(session, employee_id, tenant_id)
    employee.photo_bytes = None
    employee.photo_content_type = None
    await session.flush()
