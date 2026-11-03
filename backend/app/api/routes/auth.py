from app.services.domain_scope import require_domain_account
from app.services.domains import ensure_automatic
from datetime import datetime, timedelta, timezone
import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.org import ensure_document_categories
from app.core.config import get_settings
from app.core.security import decode_refresh_token, hash_password, issue_token_pair, verify_password
from app.db.session import get_session
from app.models import Branch, Company, Country, Tenant, User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
    TokenResponse,
    UserRead,
)
from app.services.holidays import ensure_country_holidays
from app.services.organization import apply_country_defaults

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(
    *,
    user: User,
    tenant: Tenant,
    company: Company | None = None,
    branch: Branch | None = None,
) -> TokenResponse:
    tokens = issue_token_pair(
        user_id=user.id,
        tenant_id=tenant.id,
        email=user.email,
        kind="tenant",
    )
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
        user=user,
        tenant=tenant,
        company=company,
        branch=branch,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    email = payload.email.lower()
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    country = await session.get(Country, payload.country_id)
    if country is None or not country.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown or inactive country_id",
        )

    settings = get_settings()
    trial_ends_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        days=settings.trial_days
    )

    tenant = Tenant(
        name=payload.tenant_name,
        subscription_tier="TRIAL",
        status="ACTIVE",
        trial_ends_at=trial_ends_at,
    )
    session.add(tenant)
    await session.flush()

    await session.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": str(tenant.id)},
    )

    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.owner_full_name,
        role="OWNER",
        status="ACTIVE",
    )
    company = Company(
        tenant_id=tenant.id,
        name=payload.company_name,
        legal_name=payload.company_legal_name,
        email=email,
        status="ACTIVE",
    )
    session.add(user)
    session.add(company)
    await session.flush()
    await ensure_automatic(session, company)
    await ensure_document_categories(session, company.id)

    branch = Branch(
        company_id=company.id,
        country_id=country.id,
        name=payload.branch_name,
        code=payload.branch_code,
        status="ACTIVE",
    )
    apply_country_defaults(branch, country)
    session.add(branch)

    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create account",
        ) from exc
    await ensure_country_holidays(session, company.id, country)

    await session.refresh(tenant)
    await session.refresh(user)
    await session.refresh(company)
    await session.refresh(branch)
    return _token_response(user=user, tenant=tenant, company=company, branch=branch)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    email = payload.email.lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )
    tenant = await session.get(Tenant, user.tenant_id)
    if tenant is None or tenant.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is not active",
        )
    await require_domain_account(request, session, user)
    return _token_response(user=user, tenant=tenant)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(
    request: Request,
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
    if claims.get("kind", "tenant") != "tenant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant token required",
        )
    try:
        user_id = uuid.UUID(str(claims["sub"]))
        tenant_id = uuid.UUID(str(claims["tenant_id"]))
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await session.get(User, user_id)
    if user is None or user.status != "ACTIVE" or user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None or tenant.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is not active",
        )
    await require_domain_account(request, session, user)
    tokens = issue_token_pair(
        user_id=user.id,
        tenant_id=tenant.id,
        email=user.email,
        kind="tenant",
    )
    return TokenPairResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        refresh_expires_in=tokens.refresh_expires_in,
    )


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
