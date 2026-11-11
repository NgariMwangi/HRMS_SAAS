"""Owner-only access to retained legacy fields and provenance."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_tenant_db
from app.api.org import company_for_tenant
from app.models import User
from app.models.legacy_import import LegacyImportRecord as Record

router = APIRouter(prefix="/legacy-import", tags=["imported history"])


async def scope(company_id: uuid.UUID, session: AsyncSession = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    if user.role != "OWNER":
        raise HTTPException(403, "Only the workspace owner can view imported source records")
    await company_for_tenant(session, company_id, user.tenant_id)
    domain = session.info.get("domain_company_id")
    if domain is not None and str(domain) != str(company_id):
        raise HTTPException(403, "This address is restricted to its company")
    company_filter = Record.company_id == company_id if domain else or_(Record.company_id == company_id, Record.company_id.is_(None))
    return session, [Record.tenant_id == user.tenant_id, company_filter]


@router.get("/tables")
async def tables(ctx=Depends(scope)):
    session, conditions = ctx
    rows = (await session.execute(select(Record.source_table, func.count()).where(*conditions).group_by(Record.source_table).order_by(Record.source_table))).all()
    return [dict(table=name, count=count) for name, count in rows]


@router.get("/records")
async def records(source_table: str = Query(max_length=80), offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100), ctx=Depends(scope)):
    session, conditions = ctx
    rows = (await session.scalars(select(Record).where(*conditions, Record.source_table == source_table)
        .order_by(Record.source_id).offset(offset).limit(limit))).all()
    return [dict(id=row.id, source_id=row.source_id, destination_table=row.destination_table,
        destination_ids=row.destination_ids, imported_at=row.imported_at, payload=row.payload) for row in rows]
