from app.api.access_control import require_access
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_db, get_tenant_id
from app.api.org import blank_to_none, company_for_tenant, require_status
from app.models import Company, Department, JobTitle
from app.schemas.job_title import JobTitleCreate, JobTitleRead, JobTitleUpdate

router = APIRouter(prefix="/job-titles", tags=["job-titles"])


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


async def _department_for_company(
    session: AsyncSession,
    department_id: uuid.UUID | None,
    company_id: uuid.UUID,
) -> Department | None:
    if department_id is None:
        return None
    department = await session.get(Department, department_id)
    if department is None or department.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="department_id does not belong to this company",
        )
    return department


@router.post("", response_model=JobTitleRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_access('organization.manage'))])
async def create_job_title(
    payload: JobTitleCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> JobTitle:
    await company_for_tenant(session, payload.company_id, tenant_id)
    await _department_for_company(session, payload.department_id, payload.company_id)
    title = JobTitle(**_normalize(payload.model_dump()))
    session.add(title)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job title name or code already exists for this company",
        ) from exc
    await session.refresh(title)
    return title


@router.get("", response_model=list[JobTitleRead])
async def list_job_titles(
    company_id: uuid.UUID | None = Query(default=None),
    department_id: uuid.UUID | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[JobTitle]:
    stmt = (
        select(JobTitle)
        .join(Company, JobTitle.company_id == Company.id)
        .where(Company.tenant_id == tenant_id)
        .order_by(JobTitle.name)
    )
    if company_id is not None:
        await company_for_tenant(session, company_id, tenant_id)
        stmt = stmt.where(JobTitle.company_id == company_id)
    if department_id is not None:
        stmt = stmt.where(JobTitle.department_id == department_id)
    result = await session.scalars(stmt)
    return list(result.all())


@router.get("/{job_title_id}", response_model=JobTitleRead)
async def get_job_title(
    job_title_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> JobTitle:
    title = await session.get(JobTitle, job_title_id)
    if title is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job title not found"
        )
    await company_for_tenant(session, title.company_id, tenant_id)
    return title


@router.patch("/{job_title_id}", response_model=JobTitleRead, dependencies=[Depends(require_access('organization.manage'))])
async def update_job_title(
    job_title_id: uuid.UUID,
    payload: JobTitleUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> JobTitle:
    title = await session.get(JobTitle, job_title_id)
    if title is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job title not found"
        )
    await company_for_tenant(session, title.company_id, tenant_id)
    updates = _normalize(payload.model_dump(exclude_unset=True))
    if "department_id" in updates:
        await _department_for_company(session, updates["department_id"], title.company_id)
    for field, value in updates.items():
        setattr(title, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job title name or code already exists for this company",
        ) from exc
    await session.refresh(title)
    return title
