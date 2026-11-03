from app.api.access_control import require_access
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_db, get_tenant_id
from app.api.documents import list_company_documents
from app.api.org import company_for_tenant
from app.schemas.document import CompanyDocumentRead

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[CompanyDocumentRead], dependencies=[Depends(require_access('documents.view_all', 'documents.manage'))])
async def list_documents(
    company_id: uuid.UUID = Query(),
    employee_id: uuid.UUID | None = Query(default=None),
    category_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[CompanyDocumentRead]:
    await company_for_tenant(session, company_id, tenant_id)
    return await list_company_documents(
        session,
        company_id,
        employee_id=employee_id,
        category_id=category_id,
        q=q,
    )
