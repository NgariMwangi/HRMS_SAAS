from app.services.domains import ensure_automatic
from app.api.access_control import require_access
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_db, get_tenant_id
from app.api.org import ensure_document_categories
from app.models import Company, Tenant
from app.schemas.company import CompanyCreate, CompanyRead, CompanyUpdate

router = APIRouter(prefix="/companies", tags=["companies"])

_ALLOWED_STATUS = {"ACTIVE", "INACTIVE"}


def _require_status(value: str) -> str:
    status_value = value.upper()
    if status_value not in _ALLOWED_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be ACTIVE or INACTIVE",
        )
    return status_value


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_access('organization.manage'))])
async def create_company(
    payload: CompanyCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Company:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown tenant_id"
        )
    data = payload.model_dump()
    data["status"] = _require_status(data["status"])
    company = Company(tenant_id=tenant_id, **data)
    session.add(company)
    await session.flush()
    await ensure_automatic(session, company)
    await ensure_document_categories(session, company.id)
    await session.refresh(company)
    return company


@router.get("", response_model=list[CompanyRead])
async def list_companies(
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[Company]:
    result = await session.scalars(
        select(Company).where(Company.tenant_id == tenant_id).order_by(Company.name)
    )
    return list(result.all())


@router.get("/{company_id}", response_model=CompanyRead)
async def get_company(
    company_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Company:
    company = await session.get(Company, company_id)
    if company is None or company.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        )
    return company


@router.patch("/{company_id}", response_model=CompanyRead, dependencies=[Depends(require_access('organization.manage'))])
async def update_company(
    company_id: uuid.UUID,
    payload: CompanyUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Company:
    company = await session.get(Company, company_id)
    if company is None or company.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        )
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates:
        updates["status"] = _require_status(updates["status"])
    for field, value in updates.items():
        setattr(company, field, value)
    await session.flush()
    await session.refresh(company)
    return company
