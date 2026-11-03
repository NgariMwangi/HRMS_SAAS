from app.api.access_control import require_access
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_db, get_tenant_id
from app.models import Branch, Company, Country, Currency
from app.schemas.branch import BranchCreate, BranchRead, BranchUpdate
from app.services.holidays import ensure_country_holidays
from app.services.organization import apply_country_defaults

router = APIRouter(prefix="/branches", tags=["branches"])

_ALLOWED_STATUS = {"ACTIVE", "INACTIVE"}


def _require_status(value: str) -> str:
    status_value = value.upper()
    if status_value not in _ALLOWED_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be ACTIVE or INACTIVE",
        )
    return status_value


async def _company_for_tenant(
    session: AsyncSession,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Company:
    """Never trust a client-supplied company_id without this check."""
    company = await session.get(Company, company_id)
    if company is None or company.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="company_id does not belong to the current tenant",
        )
    return company


async def _active_country(session: AsyncSession, country_id: uuid.UUID) -> Country:
    country = await session.get(Country, country_id)
    if country is None or not country.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown or inactive country_id",
        )
    return country


async def _optional_currency(
    session: AsyncSession, currency_id: uuid.UUID | None
) -> Currency | None:
    if currency_id is None:
        return None
    currency = await session.get(Currency, currency_id)
    if currency is None or not currency.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown or inactive currency_id",
        )
    return currency


@router.post("", response_model=BranchRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_access('organization.manage'))])
async def create_branch(
    payload: BranchCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Branch:
    await _company_for_tenant(session, payload.company_id, tenant_id)
    country = await _active_country(session, payload.country_id)
    await _optional_currency(session, payload.currency_id)

    data = payload.model_dump()
    data["status"] = _require_status(data["status"])
    branch = Branch(**data)
    apply_country_defaults(branch, country)
    session.add(branch)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Branch code already exists for this company",
        ) from exc
    await ensure_country_holidays(session, branch.company_id, country)
    await session.refresh(branch)
    return branch


@router.get("", response_model=list[BranchRead])
async def list_branches(
    company_id: uuid.UUID | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[Branch]:
    stmt = (
        select(Branch)
        .join(Company, Branch.company_id == Company.id)
        .where(Company.tenant_id == tenant_id)
        .order_by(Branch.name)
    )
    if company_id is not None:
        await _company_for_tenant(session, company_id, tenant_id)
        stmt = stmt.where(Branch.company_id == company_id)
    result = await session.scalars(stmt)
    return list(result.all())


@router.get("/{branch_id}", response_model=BranchRead)
async def get_branch(
    branch_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Branch:
    branch = await session.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found"
        )
    await _company_for_tenant(session, branch.company_id, tenant_id)
    return branch


@router.patch("/{branch_id}", response_model=BranchRead, dependencies=[Depends(require_access('organization.manage'))])
async def update_branch(
    branch_id: uuid.UUID,
    payload: BranchUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> Branch:
    branch = await session.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found"
        )

    # Confirm the branch's company still belongs to this tenant.
    await _company_for_tenant(session, branch.company_id, tenant_id)

    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates:
        updates["status"] = _require_status(updates["status"])
    if "country_id" in updates:
        country = await _active_country(session, updates["country_id"])
    else:
        country = await _active_country(session, branch.country_id)
    if "currency_id" in updates:
        await _optional_currency(session, updates["currency_id"])

    for field, value in updates.items():
        setattr(branch, field, value)

    if "country_id" in updates:
        apply_country_defaults(branch, country)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Branch code already exists for this company",
        ) from exc
    if "country_id" in updates:
        await ensure_country_holidays(session, branch.company_id, country)
    await session.refresh(branch)
    return branch
