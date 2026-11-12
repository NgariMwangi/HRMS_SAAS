from app.services.domains import ensure_automatic
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import delete, select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer

from app.api.deps import get_current_admin, get_platform_db
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
from app.api.routes.leave_types import require_day_basis, shape_leave_amounts
from app.api.org import (
    END_DATE_EMPLOYMENT_TYPES,
    blank_to_none,
    branch_for_company,
    company_for_tenant,
    ensure_document_categories,
    next_employee_number,
    optional_department_for_company,
    optional_job_title_for_company,
    require_employment_period,
    require_employment_type,
    require_status,
)
from app.core.security import hash_password
from app.models import (
    Branch,
    Company,
    Country,
    Currency,
    Department,
    DocumentCategory,
    Employee,
    EmployeeDocument,
    EmployeeNextOfKin,
    JobTitle,
    LeaveBalance,
    LeaveDecision,
    LeaveRequest,
    LeaveType,
    Tenant,
    User,
)
from app.schemas.auth import TenantRead, UserRead
from app.schemas.branch import BranchCreate, BranchRead, BranchUpdate
from app.schemas.company import CompanyCreate, CompanyRead, CompanyUpdate
from app.schemas.department import DepartmentCreate, DepartmentRead, DepartmentUpdate
from app.schemas.document import (
    CompanyDocumentRead,
    DocumentCategoryCreate,
    DocumentCategoryRead,
    DocumentCategoryUpdate,
)
from app.schemas.leave import LeaveTypeCreate, LeaveTypeRead, LeaveTypeUpdate
from app.schemas.employee import (
    EmployeeCreate,
    EmployeeRead,
    EmployeeUpdate,
    EmployeeCompanyTransfer,
    LifecycleActionCreate,
    LifecycleActionResult,
    LifecycleAttachmentRead,
    LifecycleEventRead,
    NextOfKinRead,
    NextOfKinReplace,
    SupervisorRead,
    SupervisorReplace,
)
from app.schemas.job_title import JobTitleCreate, JobTitleRead, JobTitleUpdate
from app.schemas.platform import TenantWorkspace, UserAdminCreate, UserAdminUpdate
from app.services.access import role_key_exists
from app.services.holidays import ensure_country_holidays
from app.services.organization import apply_country_defaults

router = APIRouter(prefix="/platform/tenants/{tenant_id}", tags=["platform-workspace"])

ALLOWED_ROLES = {"OWNER", "ADMIN", "HR", "MANAGER", "EMPLOYEE"}


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _employee_conflict(exc: IntegrityError) -> HTTPException:
    orig = str(getattr(exc, "orig", exc)).lower()
    if "uq_employee_id_number_open" in orig:
        return _conflict("An active employee already has this ID no.")
    if "uq_employee_nssf_no_open" in orig:
        return _conflict("An active employee already has this NSSF no.")
    if "uq_employee_shif_no_open" in orig:
        return _conflict("An active employee already has this SHIF no.")
    return _conflict("Employee number or email already exists for this company")


async def _tenant(
    tenant_id: uuid.UUID,
    session: AsyncSession,
) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


async def _country(session: AsyncSession, country_id: uuid.UUID) -> Country:
    country = await session.get(Country, country_id)
    if country is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown country_id")
    return country


async def _optional_currency(session: AsyncSession, currency_id: uuid.UUID | None) -> None:
    if currency_id is None:
        return
    currency = await session.get(Currency, currency_id)
    if currency is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown currency_id")


async def _require_role(session: AsyncSession, tenant_id: uuid.UUID, value: str) -> str:
    role = value.strip().upper()
    if role not in ALLOWED_ROLES and not await role_key_exists(session, tenant_id, role):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="role must be OWNER, ADMIN, HR, MANAGER, EMPLOYEE, or one of this workspace's custom roles",
        )
    return role


def _normalize_employee(data: dict) -> dict:
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
    if "email" in data and isinstance(data["email"], str):
        data["email"] = data["email"].strip().lower() or None
    if "personal_email" in data and isinstance(data["personal_email"], str):
        data["personal_email"] = data["personal_email"].strip().lower() or None
    for field in ("id_number", "pin_number", "nssf_no", "shif_no"):
        if field in data:
            data[field] = blank_to_none(data[field])
    return data


async def _owned_company(
    session: AsyncSession, company_id: uuid.UUID, tenant_id: uuid.UUID
) -> Company:
    return await company_for_tenant(session, company_id, tenant_id)


async def _company_in_tenant(
    session: AsyncSession, company_id: uuid.UUID, tenant_id: uuid.UUID
) -> Company:
    company = await session.get(Company, company_id)
    if company is None or company.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company


@router.get("/workspace", response_model=TenantWorkspace)
async def get_workspace(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> TenantWorkspace:
    tenant = await _tenant(tenant_id, session)
    users = list(
        (await session.scalars(select(User).where(User.tenant_id == tenant_id).order_by(User.full_name))).all()
    )
    companies = list(
        (await session.scalars(select(Company).where(Company.tenant_id == tenant_id).order_by(Company.name))).all()
    )
    company_ids = [row.id for row in companies]
    for company_id in company_ids:
        await ensure_document_categories(session, company_id)
    branches = (
        list(
            (
                await session.scalars(
                    select(Branch).where(Branch.company_id.in_(company_ids)).order_by(Branch.name)
                )
            ).all()
        )
        if company_ids
        else []
    )
    departments = (
        list(
            (
                await session.scalars(
                    select(Department).where(Department.company_id.in_(company_ids)).order_by(Department.name)
                )
            ).all()
        )
        if company_ids
        else []
    )
    job_titles = (
        list(
            (
                await session.scalars(
                    select(JobTitle).where(JobTitle.company_id.in_(company_ids)).order_by(JobTitle.name)
                )
            ).all()
        )
        if company_ids
        else []
    )
    document_categories = (
        list(
            (
                await session.scalars(
                    select(DocumentCategory)
                    .where(DocumentCategory.company_id.in_(company_ids))
                    .order_by(DocumentCategory.sort_order, DocumentCategory.name)
                )
            ).all()
        )
        if company_ids
        else []
    )
    leave_types = (
        list(
            (
                await session.scalars(
                    select(LeaveType)
                    .where(LeaveType.company_id.in_(company_ids))
                    .order_by(LeaveType.sort_order, LeaveType.name)
                )
            ).all()
        )
        if company_ids
        else []
    )
    employees = (
        list(
            (
                await session.scalars(
                    select(Employee)
                    .where(Employee.company_id.in_(company_ids))
                    .order_by(Employee.last_name, Employee.first_name)
                )
            ).all()
        )
        if company_ids
        else []
    )
    return TenantWorkspace(
        tenant=TenantRead.model_validate(tenant),
        users=users,
        companies=companies,
        branches=branches,
        departments=departments,
        job_titles=job_titles,
        document_categories=document_categories,
        leave_types=leave_types,
        employees=employees,
    )


@router.post("/companies", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
async def create_company(
    tenant_id: uuid.UUID,
    payload: CompanyCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Company:
    await _tenant(tenant_id, session)
    data = payload.model_dump()
    data["status"] = require_status(data["status"])
    company = Company(tenant_id=tenant_id, **data)
    session.add(company)
    await session.flush()
    await ensure_automatic(session, company)
    await ensure_document_categories(session, company.id)
    await session.refresh(company)
    return company


@router.patch("/companies/{company_id}", response_model=CompanyRead)
async def update_company(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Company:
    company = await _company_in_tenant(session, company_id, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is not None:
        updates["status"] = require_status(updates["status"])
    for field, value in updates.items():
        setattr(company, field, value)
    await session.flush()
    await session.refresh(company)
    return company


@router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    await _company_in_tenant(session, company_id, tenant_id)
    await session.execute(delete(EmployeeDocument).where(EmployeeDocument.company_id == company_id))
    await session.execute(delete(DocumentCategory).where(DocumentCategory.company_id == company_id))
    await session.execute(delete(LeaveDecision).where(LeaveDecision.company_id == company_id))
    await session.execute(delete(LeaveRequest).where(LeaveRequest.company_id == company_id))
    await session.execute(delete(LeaveBalance).where(LeaveBalance.company_id == company_id))
    await session.execute(delete(LeaveType).where(LeaveType.company_id == company_id))
    await session.execute(delete(Employee).where(Employee.company_id == company_id))
    await session.execute(delete(JobTitle).where(JobTitle.company_id == company_id))
    await session.execute(delete(Department).where(Department.company_id == company_id))
    await session.execute(delete(Branch).where(Branch.company_id == company_id))
    await session.execute(delete(Company).where(Company.id == company_id))


@router.post("/branches", response_model=BranchRead, status_code=status.HTTP_201_CREATED)
async def create_branch(
    tenant_id: uuid.UUID,
    payload: BranchCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Branch:
    await _owned_company(session, payload.company_id, tenant_id)
    country = await _country(session, payload.country_id)
    await _optional_currency(session, payload.currency_id)
    data = payload.model_dump()
    data["status"] = require_status(data["status"])
    branch = Branch(**data)
    apply_country_defaults(branch, country)
    session.add(branch)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict("Branch code already exists for this company") from exc
    await ensure_country_holidays(session, branch.company_id, country)
    await session.refresh(branch)
    return branch


@router.patch("/branches/{branch_id}", response_model=BranchRead)
async def update_branch(
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    payload: BranchUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Branch:
    branch = await session.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    await _owned_company(session, branch.company_id, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is not None:
        updates["status"] = require_status(updates["status"])
    country = None
    if "country_id" in updates and updates["country_id"] is not None:
        country = await _country(session, updates["country_id"])
    if "currency_id" in updates:
        await _optional_currency(session, updates["currency_id"])
    for field, value in updates.items():
        setattr(branch, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict("Branch code already exists for this company") from exc
    if country is not None:
        await ensure_country_holidays(session, branch.company_id, country)
    await session.refresh(branch)
    return branch


@router.delete("/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_branch(
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    branch = await session.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    await _owned_company(session, branch.company_id, tenant_id)
    await session.execute(delete(Employee).where(Employee.branch_id == branch_id))
    await session.execute(delete(Branch).where(Branch.id == branch_id))


@router.post("/departments", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
async def create_department(
    tenant_id: uuid.UUID,
    payload: DepartmentCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Department:
    await _owned_company(session, payload.company_id, tenant_id)
    data = payload.model_dump()
    data["status"] = require_status(data["status"])
    data["code"] = blank_to_none(data.get("code"))
    data["description"] = blank_to_none(data.get("description"))
    department = Department(**data)
    session.add(department)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict("Department name or code already exists for this company") from exc
    await session.refresh(department)
    return department


@router.patch("/departments/{department_id}", response_model=DepartmentRead)
async def update_department(
    tenant_id: uuid.UUID,
    department_id: uuid.UUID,
    payload: DepartmentUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Department:
    department = await session.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    await _owned_company(session, department.company_id, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is not None:
        updates["status"] = require_status(updates["status"])
    if "code" in updates:
        updates["code"] = blank_to_none(updates["code"])
    if "description" in updates:
        updates["description"] = blank_to_none(updates["description"])
    for field, value in updates.items():
        setattr(department, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict("Department name or code already exists for this company") from exc
    await session.refresh(department)
    return department


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    tenant_id: uuid.UUID,
    department_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    department = await session.get(Department, department_id)
    if department is None:
        raise HTTPException(status_code=404, detail="Department not found")
    await _owned_company(session, department.company_id, tenant_id)
    await session.execute(
        update(Employee).where(Employee.department_id == department_id).values(department_id=None)
    )
    await session.execute(
        update(JobTitle).where(JobTitle.department_id == department_id).values(department_id=None)
    )
    await session.execute(delete(Department).where(Department.id == department_id))


@router.post("/job-titles", response_model=JobTitleRead, status_code=status.HTTP_201_CREATED)
async def create_job_title(
    tenant_id: uuid.UUID,
    payload: JobTitleCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> JobTitle:
    await _owned_company(session, payload.company_id, tenant_id)
    await optional_department_for_company(session, payload.department_id, payload.company_id)
    data = payload.model_dump()
    data["status"] = require_status(data["status"])
    data["code"] = blank_to_none(data.get("code"))
    data["description"] = blank_to_none(data.get("description"))
    title = JobTitle(**data)
    session.add(title)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict("Job title name or code already exists for this company") from exc
    await session.refresh(title)
    return title


@router.patch("/job-titles/{job_title_id}", response_model=JobTitleRead)
async def update_job_title(
    tenant_id: uuid.UUID,
    job_title_id: uuid.UUID,
    payload: JobTitleUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> JobTitle:
    title = await session.get(JobTitle, job_title_id)
    if title is None:
        raise HTTPException(status_code=404, detail="Job title not found")
    await _owned_company(session, title.company_id, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is not None:
        updates["status"] = require_status(updates["status"])
    if "code" in updates:
        updates["code"] = blank_to_none(updates["code"])
    if "description" in updates:
        updates["description"] = blank_to_none(updates["description"])
    if "department_id" in updates:
        await optional_department_for_company(session, updates["department_id"], title.company_id)
    for field, value in updates.items():
        setattr(title, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict("Job title name or code already exists for this company") from exc
    await session.refresh(title)
    return title


@router.delete("/job-titles/{job_title_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_title(
    tenant_id: uuid.UUID,
    job_title_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    title = await session.get(JobTitle, job_title_id)
    if title is None:
        raise HTTPException(status_code=404, detail="Job title not found")
    await _owned_company(session, title.company_id, tenant_id)
    await session.execute(
        update(Employee).where(Employee.job_title_id == job_title_id).values(job_title_id=None)
    )
    await session.execute(delete(JobTitle).where(JobTitle.id == job_title_id))


@router.post("/employees", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
async def create_employee(
    tenant_id: uuid.UUID,
    payload: EmployeeCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Employee:
    await _owned_company(session, payload.company_id, tenant_id)
    await branch_for_company(session, payload.branch_id, payload.company_id)
    await optional_department_for_company(session, payload.department_id, payload.company_id)
    await optional_job_title_for_company(session, payload.job_title_id, payload.company_id)
    data = _normalize_employee(payload.model_dump())
    if data["employment_type"] not in END_DATE_EMPLOYMENT_TYPES:
        data["date_ended"] = None
    require_employment_period(data["employment_type"], data.get("date_joined"), data.get("date_ended"))
    if not data.get("employee_number"):
        data["employee_number"] = await next_employee_number(session, payload.company_id)
    data["status"] = "ACTIVE"
    employee = Employee(**data)
    session.add(employee)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _employee_conflict(exc) from exc
    await record_hired(session, employee)
    await replace_next_of_kin(session, employee, payload.next_of_kin)
    await replace_supervisors(session, employee, payload.supervisor_ids)
    await session.refresh(employee)
    return employee


async def _employee_in_tenant(
    session: AsyncSession, employee_id: uuid.UUID, tenant_id: uuid.UUID
) -> Employee:
    employee = await session.get(Employee, employee_id, options=(selectinload(Employee.login_user),))
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await _owned_company(session, employee.company_id, tenant_id)
    return employee


@router.get("/employees/{employee_id}", response_model=EmployeeRead)
async def get_employee(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Employee:
    return await _employee_in_tenant(session, employee_id, tenant_id)


@router.get("/employees/{employee_id}/next-of-kin", response_model=list[NextOfKinRead])
async def get_employee_next_of_kin(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[EmployeeNextOfKin]:
    employee = await _employee_in_tenant(session, employee_id, tenant_id)
    return await list_next_of_kin(session, employee.id)


@router.put("/employees/{employee_id}/next-of-kin", response_model=list[NextOfKinRead])
async def put_employee_next_of_kin(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: NextOfKinReplace,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[EmployeeNextOfKin]:
    employee = await _employee_in_tenant(session, employee_id, tenant_id)
    return await replace_next_of_kin(session, employee, payload.items)


@router.get("/employees/{employee_id}/supervisors", response_model=list[SupervisorRead])
async def get_employee_supervisors(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[Employee]:
    employee = await _employee_in_tenant(session, employee_id, tenant_id)
    return await list_supervisors(session, employee.id)


@router.put("/employees/{employee_id}/supervisors", response_model=list[SupervisorRead])
async def put_employee_supervisors(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: SupervisorReplace,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[Employee]:
    employee = await _employee_in_tenant(session, employee_id, tenant_id)
    return await replace_supervisors(session, employee, payload.supervisor_ids)


@router.get("/documents", response_model=list[CompanyDocumentRead])
async def list_tenant_documents(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID = Query(),
    employee_id: uuid.UUID | None = Query(default=None),
    category_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[CompanyDocumentRead]:
    await _owned_company(session, company_id, tenant_id)
    return await list_company_documents(
        session,
        company_id,
        employee_id=employee_id,
        category_id=category_id,
        q=q,
    )


@router.post("/document-categories", response_model=DocumentCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_document_category(
    tenant_id: uuid.UUID,
    payload: DocumentCategoryCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> DocumentCategory:
    await _owned_company(session, payload.company_id, tenant_id)
    await ensure_document_categories(session, payload.company_id)
    highest = await session.scalar(
        select(DocumentCategory.sort_order)
        .where(DocumentCategory.company_id == payload.company_id)
        .order_by(DocumentCategory.sort_order.desc())
        .limit(1)
    )
    row = DocumentCategory(
        company_id=payload.company_id,
        name=payload.name.strip(),
        locked=False,
        sort_order=(highest or 0) + 10,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict("A category with this name already exists for this company") from exc
    await session.refresh(row)
    return row


@router.patch("/document-categories/{category_id}", response_model=DocumentCategoryRead)
async def update_document_category(
    tenant_id: uuid.UUID,
    category_id: uuid.UUID,
    payload: DocumentCategoryUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> DocumentCategory:
    row = await session.get(DocumentCategory, category_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Document category not found")
    await _owned_company(session, row.company_id, tenant_id)
    if row.locked:
        raise HTTPException(status_code=400, detail="The Lifecycle category cannot be edited")
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()
    for field, value in updates.items():
        setattr(row, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict("A category with this name already exists for this company") from exc
    await session.refresh(row)
    return row


@router.delete("/document-categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document_category(
    tenant_id: uuid.UUID,
    category_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    row = await session.get(DocumentCategory, category_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Document category not found")
    await _owned_company(session, row.company_id, tenant_id)
    if row.locked:
        raise HTTPException(status_code=400, detail="The Lifecycle category cannot be edited")
    used = await session.scalar(
        select(EmployeeDocument.id).where(EmployeeDocument.category_id == category_id).limit(1)
    )
    if used is not None:
        raise HTTPException(status_code=409, detail="Category is in use")
    await session.delete(row)


@router.post("/leave-types", response_model=LeaveTypeRead, status_code=status.HTTP_201_CREATED)
async def create_leave_type(
    tenant_id: uuid.UUID,
    payload: LeaveTypeCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> LeaveType:
    await _owned_company(session, payload.company_id, tenant_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Enter a leave type name")
    highest = await session.scalar(
        select(LeaveType.sort_order)
        .where(LeaveType.company_id == payload.company_id)
        .order_by(LeaveType.sort_order.desc())
        .limit(1)
    )
    days, rate = shape_leave_amounts(
        payload.accrued,
        payload.days,
        payload.accrual_per_month,
        rate_set=payload.accrual_per_month is not None,
    )
    row = LeaveType(
        company_id=payload.company_id,
        name=name,
        days=days,
        accrued=payload.accrued,
        accrual_per_month=rate,
        day_basis=require_day_basis(payload.day_basis),
        sort_order=(highest or 0) + 10,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict("A leave type with this name already exists for this company") from exc
    await session.refresh(row)
    return row


@router.patch("/leave-types/{leave_type_id}", response_model=LeaveTypeRead)
async def update_leave_type(
    tenant_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    payload: LeaveTypeUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> LeaveType:
    row = await session.get(LeaveType, leave_type_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Leave type not found")
    await _owned_company(session, row.company_id, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()
    if "day_basis" in updates and updates["day_basis"] is not None:
        updates["day_basis"] = require_day_basis(updates["day_basis"])
    if "days" in updates or "accrued" in updates or "accrual_per_month" in updates:
        accrued = updates["accrued"] if "accrued" in updates else row.accrued
        days, rate = shape_leave_amounts(
            accrued,
            updates["days"] if "days" in updates else row.days,
            updates["accrual_per_month"] if "accrual_per_month" in updates else row.accrual_per_month,
            rate_set="accrual_per_month" in updates,
        )
        updates["accrued"] = accrued
        updates["days"] = days
        updates["accrual_per_month"] = rate
    for field, value in updates.items():
        setattr(row, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict("A leave type with this name already exists for this company") from exc
    await session.refresh(row)
    return row


@router.delete("/leave-types/{leave_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_leave_type(
    tenant_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    row = await session.get(LeaveType, leave_type_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Leave type not found")
    await _owned_company(session, row.company_id, tenant_id)
    await session.delete(row)


@router.get("/employees/{employee_id}/documents", response_model=list[CompanyDocumentRead])
async def get_employee_documents(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[CompanyDocumentRead]:
    employee = await _employee_in_tenant(session, employee_id, tenant_id)
    return await list_company_documents(
        session, employee.company_id, employee_id=employee.id
    )


@router.post("/employees/{employee_id}/documents", response_model=CompanyDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_employee_document(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    category_id: uuid.UUID = Form(),
    issued_on: str | None = Form(default=None),
    expires_on: str | None = Form(default=None),
    note: str | None = Form(default=None),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> CompanyDocumentRead:
    employee = await _employee_in_tenant(session, employee_id, tenant_id)
    return await add_employee_document(
        session,
        employee,
        upload=file,
        category_id=category_id,
        issued_on=parse_optional_date(issued_on),
        expires_on=parse_optional_date(expires_on),
        note=note,
        uploaded_by=None,
    )


@router.get("/employees/{employee_id}/documents/{document_id}")
async def download_employee_document(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Response:
    await _employee_in_tenant(session, employee_id, tenant_id)
    row = await employee_document_file(session, employee_id, document_id)
    return Response(
        content=row.file_bytes,
        media_type=row.content_type,
        headers={"Content-Disposition": f'attachment; filename="{row.filename.replace(chr(34), "")}"'},
    )


@router.delete("/employees/{employee_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee_document(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    await _employee_in_tenant(session, employee_id, tenant_id)
    row = await session.get(EmployeeDocument, document_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=404, detail="Document not found")
    from app.api.documents import protect_performance_evidence
    await protect_performance_evidence(session, document_id)
    await session.delete(row)
    await session.flush()


@router.get("/employees/{employee_id}/lifecycle", response_model=list[LifecycleEventRead])
async def get_employee_lifecycle(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[LifecycleEventRead]:
    employee = await _employee_in_tenant(session, employee_id, tenant_id)
    rows = await list_employee_events(session, employee.id)
    return [event_to_read(event, person) for event, person in rows]


@router.post("/employees/{employee_id}/lifecycle", response_model=LifecycleActionResult)
async def post_employee_lifecycle(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: LifecycleActionCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> LifecycleActionResult:
    employee = await _employee_in_tenant(session, employee_id, tenant_id)
    return await apply_lifecycle_action(session, employee, payload, None)


@router.post("/employees/{employee_id}/lifecycle/{event_id}/attachments", response_model=list[LifecycleAttachmentRead])
async def upload_lifecycle_attachments(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    event_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[LifecycleAttachmentRead]:
    await _employee_in_tenant(session, employee_id, tenant_id)
    event = await event_for_employee(session, event_id, employee_id)
    rows = await add_event_attachments(session, event, files)
    return [
        LifecycleAttachmentRead(id=row.id, filename=row.filename, content_type=row.content_type)
        for row in rows
    ]


@router.get("/employees/{employee_id}/lifecycle/{event_id}/attachments/{attachment_id}")
async def download_lifecycle_attachment(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    event_id: uuid.UUID,
    attachment_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Response:
    await _employee_in_tenant(session, employee_id, tenant_id)
    row = await attachment_file(session, event_id, employee_id, attachment_id)
    return Response(
        content=row.file_bytes,
        media_type=row.content_type,
        headers={"Content-Disposition": f'attachment; filename="{row.filename.replace(chr(34), "")}"'},
    )


@router.get("/employees/{employee_id}/photo")
async def get_employee_photo(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Response:
    employee = await session.scalar(
        select(Employee)
        .options(undefer(Employee.photo_bytes))
        .where(Employee.id == employee_id)
    )
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await _owned_company(session, employee.company_id, tenant_id)
    if not employee.photo_bytes:
        raise HTTPException(status_code=404, detail="Passport photo not found")
    return Response(
        content=employee.photo_bytes,
        media_type=employee.photo_content_type or "application/octet-stream",
    )


@router.post("/employees/{employee_id}/transfer-company", response_model=EmployeeRead)
async def transfer_company(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: EmployeeCompanyTransfer,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
):
    from app.services.employee_transfers import transfer_employee
    employee = await transfer_employee(session, employee_id, tenant_id, payload)
    return await session.get(Employee, employee.id, options=(selectinload(Employee.login_user),), populate_existing=True)


@router.patch("/employees/{employee_id}", response_model=EmployeeRead)
async def update_employee(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Employee:
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await _owned_company(session, employee.company_id, tenant_id)
    updates = _normalize_employee(payload.model_dump(exclude_unset=True))
    employment_type = updates.get("employment_type", employee.employment_type)
    if employment_type not in END_DATE_EMPLOYMENT_TYPES and (
        "employment_type" in updates or "date_ended" in updates
    ):
        updates["date_ended"] = None
    require_employment_period(
        employment_type,
        updates["date_joined"] if "date_joined" in updates else employee.date_joined,
        updates["date_ended"] if "date_ended" in updates else employee.date_ended,
        allow_incomplete=employee.employment_type in {"INTERN", "PROBATION"}
            and (employee.date_joined is None or employee.date_ended is None),
    )
    if "branch_id" in updates and updates["branch_id"] is not None:
        await branch_for_company(session, updates["branch_id"], employee.company_id)
    if "department_id" in updates:
        await optional_department_for_company(session, updates["department_id"], employee.company_id)
    if "job_title_id" in updates:
        await optional_job_title_for_company(session, updates["job_title_id"], employee.company_id)
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
    return employee


@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await _owned_company(session, employee.company_id, tenant_id)
    await session.delete(employee)


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    tenant_id: uuid.UUID,
    payload: UserAdminCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> User:
    await _tenant(tenant_id, session)
    if payload.employee_id:
        employee = await session.get(Employee, payload.employee_id)
        if employee is None:
            raise HTTPException(404, "Employee not found")
        await _owned_company(session, employee.company_id, tenant_id)
        linked = await session.scalar(select(User.id).where(User.tenant_id == tenant_id, User.employee_id == payload.employee_id))
        if linked:
            raise _conflict("This employee already has a login")
    user = User(
        tenant_id=tenant_id,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=await _require_role(session, tenant_id, payload.role),
        status=require_status(payload.status),
        employee_id=payload.employee_id,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict("An account with this email already exists") from exc
    await session.refresh(user)
    return user


async def protect_last_owner(session, tenant_id, user, next_role=None, next_status=None, deleting=False):
    await session.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    await session.refresh(user)
    removing = deleting or (next_role is not None and next_role.strip().upper() != "OWNER") or (next_status is not None and next_status.strip().upper() != "ACTIVE")
    if user.role == "OWNER" and user.status == "ACTIVE" and removing:
        count = await session.scalar(select(func.count()).select_from(User).where(User.tenant_id == tenant_id, User.role == "OWNER", User.status == "ACTIVE"))
        if (count or 0) <= 1:
            raise HTTPException(400, "The workspace needs at least one active owner")


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: UserAdminUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> User:
    user = await session.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="User not found")
    updates = payload.model_dump(exclude_unset=True)
    await protect_last_owner(session, tenant_id, user, updates.get("role"), updates.get("status"))
    if updates.get("employee_id"):
        employee = await session.get(Employee, updates["employee_id"])
        if employee is None:
            raise HTTPException(404, "Employee not found")
        await _owned_company(session, employee.company_id, tenant_id)
        linked = await session.scalar(select(User.id).where(User.tenant_id == tenant_id, User.employee_id == updates["employee_id"], User.id != user.id))
        if linked:
            raise _conflict("This employee already has a login")
    if "password" in updates:
        user.password_hash = hash_password(updates.pop("password"))
    if "email" in updates and updates["email"] is not None:
        updates["email"] = updates["email"].lower()
    if "role" in updates and updates["role"] is not None:
        updates["role"] = await _require_role(session, tenant_id, updates["role"])
    if "status" in updates and updates["status"] is not None:
        updates["status"] = require_status(updates["status"])
    if "full_name" in updates and updates["full_name"] is not None:
        updates["full_name"] = updates["full_name"].strip()
    for field, value in updates.items():
        setattr(user, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise _conflict("An account with this email already exists") from exc
    await session.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    user = await session.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="User not found")
    await protect_last_owner(session, tenant_id, user, deleting=True)
    await session.delete(user)
