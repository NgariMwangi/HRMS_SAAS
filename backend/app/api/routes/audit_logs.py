from app.api.access_control import require_access
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user, get_platform_db, get_tenant_db
from app.models import AuditLog, PlatformAdmin, User
from app.schemas.audit import AuditLogRead

router = APIRouter(tags=["audit"])


def _list_stmt(outcome: str | None, limit: int):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if outcome in {"SUCCESS", "FAILED"}:
        stmt = stmt.where(AuditLog.outcome == outcome)
    return stmt


@router.get("/audit-logs", response_model=list[AuditLogRead], dependencies=[Depends(require_access('audit.view'))])
@router.get("/auth/audit-logs", response_model=list[AuditLogRead], dependencies=[Depends(require_access('audit.view'))])
async def list_tenant_audit_logs(
    outcome: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[AuditLog]:
    stmt = _list_stmt(outcome, limit).where(AuditLog.tenant_id == user.tenant_id)
    rows = await session.scalars(stmt)
    return list(rows)


@router.get("/platform/audit-logs", response_model=list[AuditLogRead])
async def list_platform_audit_logs(
    outcome: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    _admin: PlatformAdmin = Depends(get_current_admin),
    session: AsyncSession = Depends(get_platform_db),
) -> list[AuditLog]:
    rows = await session.scalars(_list_stmt(outcome, limit))
    return list(rows)
