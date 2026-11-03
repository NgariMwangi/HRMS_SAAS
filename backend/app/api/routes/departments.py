from app.api.access_control import require_access
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_db, get_tenant_id
from app.api.org import blank_to_none, company_for_tenant, require_status
from app.models import Company, Department
from app.schemas.department import DepartmentCreate, DepartmentRead, DepartmentUpdate

router = APIRouter(prefix="/departments", tags=["departments"])


def _normalize(data: dict) -> dict:
    if "status" in data and data["status"] is not None:
        data["status"] = require_status(data["status"])
    if "code" in data:
        data["code"] = blank_to_none(data["code"])
    if "description" in data:
        data["description"] = blank_to_none(data["description"])
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    return data


@router.post("", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_access('organization.manage'))])
async def create_department(
    payload: DepartmentCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Department:
    await company_for_tenant(session, payload.company_id, tenant_id)
    department = Department(**_normalize(payload.model_dump()))
    session.add(department)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Department name or code already exists for this company",
        ) from exc
    await session.refresh(department)
    return department


@router.get("", response_model=list[DepartmentRead])
async def list_departments(
    company_id: uuid.UUID | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[Department]:
    stmt = (
        select(Department)
        .join(Company, Department.company_id == Company.id)
        .where(Company.tenant_id == tenant_id)
        .order_by(Department.name)
    )
    if company_id is not None:
        await company_for_tenant(session, company_id, tenant_id)
        stmt = stmt.where(Department.company_id == company_id)
    result = await session.scalars(stmt)
    return list(result.all())


@router.get("/{department_id}", response_model=DepartmentRead)
async def get_department(
    department_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Department:
    department = await session.get(Department, department_id)
    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Department not found"
        )
    await company_for_tenant(session, department.company_id, tenant_id)
    return department


@router.patch("/{department_id}", response_model=DepartmentRead, dependencies=[Depends(require_access('organization.manage'))])
async def update_department(
    department_id: uuid.UUID,
    payload: DepartmentUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Department:
    department = await session.get(Department, department_id)
    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Department not found"
        )
    await company_for_tenant(session, department.company_id, tenant_id)
    updates = _normalize(payload.model_dump(exclude_unset=True))
    for field, value in updates.items():
        setattr(department, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Department name or code already exists for this company",
        ) from exc
    await session.refresh(department)
    return department
