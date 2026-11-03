from app.api.access_control import require_access
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_db, get_tenant_id
from app.api.lifecycle import event_to_read, list_company_events
from app.api.org import company_for_tenant
from app.schemas.employee import LifecycleEventRead

router = APIRouter(prefix="/lifecycle", tags=["lifecycle"])


@router.get("", response_model=list[LifecycleEventRead], dependencies=[Depends(require_access('lifecycle.view_all', 'lifecycle.manage'))])
async def list_lifecycle(
    company_id: uuid.UUID = Query(),
    event_type: str | None = Query(default=None),
    q: str | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[LifecycleEventRead]:
    await company_for_tenant(session, company_id, tenant_id)
    rows = await list_company_events(session, company_id, event_type, q)
    return [event_to_read(event, person) for event, person in rows]
