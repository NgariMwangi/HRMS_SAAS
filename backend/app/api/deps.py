"""
Request dependencies.

Tenant routes take tenant_id from a tenant JWT, then SET LOCAL
app.current_tenant_id so RLS can filter rows.

Platform-owner routes set app.is_platform_admin = 'true' so RLS
allows access across every tenant.
"""

import uuid
from collections.abc import AsyncIterator

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_session_maker
from app.models import PlatformAdmin, User
from app.services.domain_scope import require_domain_account

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_token_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        return decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid or expired token") from exc


async def get_tenant_payload(payload: dict = Depends(get_token_payload)) -> dict:
    if payload.get("kind", "tenant") != "tenant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant token required",
        )
    return payload


async def get_tenant_id(payload: dict = Depends(get_tenant_payload)) -> uuid.UUID:
    try:
        return uuid.UUID(str(payload["tenant_id"]))
    except (KeyError, ValueError) as exc:
        raise _unauthorized("Invalid token") from exc


async def get_tenant_db(
    request: Request,
    payload: dict = Depends(get_tenant_payload),
) -> AsyncIterator[AsyncSession]:
    try:
        tenant_id = uuid.UUID(str(payload["tenant_id"]))
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise _unauthorized("Invalid token") from exc

    context = getattr(request.state, "company_domain", None)
    if context and context["tenant_id"] != tenant_id:
        raise HTTPException(403, "This address is restricted to its company")
    if context and request.query_params.get("company_id") not in {None, "", str(context["company_id"])}:
        raise HTTPException(403, "This address is restricted to its company")

    maker = get_session_maker()
    async with maker() as session:
        try:
            await session.execute(
                text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            user = await session.get(User, user_id)
            if user is None or user.status != "ACTIVE" or user.tenant_id != tenant_id:
                raise _unauthorized("Invalid token")
            await require_domain_account(request, session, user)
            if context:
                session.info["domain_company_id"] = context["company_id"]
                await session.execute(text("SELECT set_config('app.domain_company_id', :cid, true)"), {"cid": str(context["company_id"])})
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    payload: dict = Depends(get_tenant_payload),
    session: AsyncSession = Depends(get_tenant_db),
) -> User:
    user = await session.get(User, uuid.UUID(str(payload["sub"])))
    if user is None:
        raise _unauthorized("Invalid token")
    return user


async def get_platform_payload(payload: dict = Depends(get_token_payload)) -> dict:
    if payload.get("kind") != "platform":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin token required",
        )
    return payload


async def get_platform_db(
    payload: dict = Depends(get_platform_payload),
) -> AsyncIterator[AsyncSession]:
    try:
        admin_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise _unauthorized("Invalid token") from exc

    maker = get_session_maker()
    async with maker() as session:
        try:
            await session.execute(
                text("SELECT set_config('app.is_platform_admin', 'true', true)")
            )
            admin = await session.get(PlatformAdmin, admin_id)
            if admin is None or admin.status != "ACTIVE":
                raise _unauthorized("Invalid token")
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_admin(
    payload: dict = Depends(get_platform_payload),
    session: AsyncSession = Depends(get_platform_db),
) -> PlatformAdmin:
    admin = await session.get(PlatformAdmin, uuid.UUID(str(payload["sub"])))
    if admin is None:
        raise _unauthorized("Invalid token")
    return admin
