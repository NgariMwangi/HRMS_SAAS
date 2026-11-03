import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin, get_platform_db
from app.core.config import get_settings
from app.core.security import decode_refresh_token, issue_token_pair, verify_password
from app.db.session import get_session
from app.models import Branch, Company, Country, PlatformAdmin, Tenant, User
from app.schemas.auth import LoginRequest, RefreshRequest, TenantRead, TokenPairResponse, UserRead
from app.schemas.branch import BranchRead
from app.schemas.company import CompanyRead
from app.schemas.country import CountryRead
from app.schemas.platform import (
    BranchAdminUpdate,
    CompanyAdminUpdate,
    CountryAdminUpdate,
    PlatformAdminRead,
    PlatformOverview,
    PlatformTokenResponse,
    StatusUpdate,
    TenantDetail,
    TenantSummary,
    TenantUpdate,
)

router = APIRouter(prefix="/platform", tags=["platform"])

ALLOWED_TENANT_STATUS = {"ACTIVE", "SUSPENDED"}
ALLOWED_TIERS = {"TRIAL", "STARTER", "GROWTH", "ENTERPRISE"}
ALLOWED_RECORD_STATUS = {"ACTIVE", "INACTIVE"}


@router.post("/auth/login", response_model=PlatformTokenResponse)
async def platform_login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> PlatformTokenResponse:
    email = payload.email.lower()
    admin = await session.scalar(
        select(PlatformAdmin).where(PlatformAdmin.email == email)
    )
    if admin is None or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if admin.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )
    tokens = issue_token_pair(user_id=admin.id, email=admin.email, kind="platform")
    return PlatformTokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
        admin=admin,
    )


@router.post("/auth/refresh", response_model=TokenPairResponse)
async def platform_refresh(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPairResponse:
    try:
        claims = decode_refresh_token(payload.refresh_token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if claims.get("kind") != "platform":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin token required",
        )
    try:
        admin_id = uuid.UUID(str(claims["sub"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    admin = await session.get(PlatformAdmin, admin_id)
    if admin is None or admin.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    tokens = issue_token_pair(user_id=admin.id, email=admin.email, kind="platform")
    return TokenPairResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
    )


@router.get("/me", response_model=PlatformAdminRead)
async def platform_me(admin: PlatformAdmin = Depends(get_current_admin)) -> PlatformAdmin:
    return admin


@router.get("/overview", response_model=PlatformOverview)
async def platform_overview(
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> PlatformOverview:
    tenant_count = await session.scalar(select(func.count()).select_from(Tenant)) or 0
    active_tenant_count = await session.scalar(
        select(func.count()).select_from(Tenant).where(Tenant.status == "ACTIVE")
    ) or 0
    trial_count = await session.scalar(
        select(func.count())
        .select_from(Tenant)
        .where(Tenant.subscription_tier == "TRIAL")
    ) or 0
    user_count = await session.scalar(select(func.count()).select_from(User)) or 0
    company_count = await session.scalar(select(func.count()).select_from(Company)) or 0
    branch_count = await session.scalar(select(func.count()).select_from(Branch)) or 0
    countries = list(
        (
            await session.scalars(
                select(Country)
                .options(selectinload(Country.default_currency))
                .order_by(Country.name)
            )
        ).all()
    )
    return PlatformOverview(
        tenant_count=tenant_count,
        active_tenant_count=active_tenant_count,
        trial_count=trial_count,
        user_count=user_count,
        company_count=company_count,
        branch_count=branch_count,
        countries=countries,
    )


@router.get("/tenants", response_model=list[TenantSummary])
async def list_tenants(
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> list[TenantSummary]:
    tenants = list(
        (await session.scalars(select(Tenant).order_by(Tenant.created_at.desc()))).all()
    )
    summaries: list[TenantSummary] = []
    for tenant in tenants:
        user_count = await session.scalar(
            select(func.count()).select_from(User).where(User.tenant_id == tenant.id)
        ) or 0
        company_count = await session.scalar(
            select(func.count())
            .select_from(Company)
            .where(Company.tenant_id == tenant.id)
        ) or 0
        summaries.append(
            TenantSummary(
                **TenantRead.model_validate(tenant).model_dump(),
                user_count=user_count,
                company_count=company_count,
            )
        )
    return summaries


@router.get("/tenants/{tenant_id}", response_model=TenantDetail)
async def get_tenant(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> Tenant:
    tenant = await session.scalar(
        select(Tenant)
        .options(
            selectinload(Tenant.users),
            selectinload(Tenant.companies).selectinload(Company.branches),
        )
        .where(Tenant.id == tenant_id)
    )
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


@router.patch("/tenants/{tenant_id}", response_model=TenantDetail)
async def update_tenant(
    tenant_id: uuid.UUID,
    payload: TenantUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in ALLOWED_TENANT_STATUS:
        raise HTTPException(status_code=400, detail="Invalid tenant status")
    if "subscription_tier" in updates and updates["subscription_tier"] not in ALLOWED_TIERS:
        raise HTTPException(status_code=400, detail="Invalid subscription tier")
    for field, value in updates.items():
        setattr(tenant, field, value)
    await session.flush()
    return await _reload_tenant(session, tenant_id)


@router.post("/tenants/{tenant_id}/extend-trial", response_model=TenantDetail)
async def extend_trial(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    settings = get_settings()
    baseline = tenant.trial_ends_at or datetime.now(timezone.utc).replace(tzinfo=None)
    if baseline < datetime.now(timezone.utc).replace(tzinfo=None):
        baseline = datetime.now(timezone.utc).replace(tzinfo=None)
    tenant.trial_ends_at = baseline + timedelta(days=settings.trial_days)
    tenant.subscription_tier = "TRIAL"
    tenant.status = "ACTIVE"
    await session.flush()
    return await _reload_tenant(session, tenant_id)


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user_status(
    user_id: uuid.UUID,
    payload: StatusUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> User:
    if payload.status not in ALLOWED_RECORD_STATUS:
        raise HTTPException(status_code=400, detail="Invalid user status")
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = payload.status
    await session.flush()
    await session.refresh(user)
    return user


@router.patch("/companies/{company_id}", response_model=CompanyRead)
async def update_company(
    company_id: uuid.UUID,
    payload: CompanyAdminUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> Company:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in ALLOWED_RECORD_STATUS:
        raise HTTPException(status_code=400, detail="Invalid company status")
    for field, value in updates.items():
        setattr(company, field, value)
    await session.flush()
    await session.refresh(company)
    return company


@router.patch("/branches/{branch_id}", response_model=BranchRead)
async def update_branch(
    branch_id: uuid.UUID,
    payload: BranchAdminUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> Branch:
    branch = await session.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=404, detail="Branch not found")
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in ALLOWED_RECORD_STATUS:
        raise HTTPException(status_code=400, detail="Invalid branch status")
    for field, value in updates.items():
        setattr(branch, field, value)
    await session.flush()
    await session.refresh(branch)
    return branch


@router.get("/countries", response_model=list[CountryRead])
async def list_all_countries(
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> list[Country]:
    result = await session.scalars(
        select(Country)
        .options(selectinload(Country.default_currency))
        .order_by(Country.name)
    )
    return list(result.all())


@router.patch("/countries/{country_id}", response_model=CountryRead)
async def update_country(
    country_id: uuid.UUID,
    payload: CountryAdminUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> Country:
    country = await session.get(Country, country_id)
    if country is None:
        raise HTTPException(status_code=404, detail="Country not found")
    country.is_active = payload.is_active
    await session.flush()
    loaded = await session.scalar(
        select(Country)
        .options(selectinload(Country.default_currency))
        .where(Country.id == country_id)
    )
    assert loaded is not None
    return loaded


async def _reload_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = await session.scalar(
        select(Tenant)
        .options(
            selectinload(Tenant.users),
            selectinload(Tenant.companies).selectinload(Company.branches),
        )
        .where(Tenant.id == tenant_id)
    )
    assert tenant is not None
    return tenant
