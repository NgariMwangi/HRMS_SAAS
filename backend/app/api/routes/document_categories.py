from app.api.access_control import require_access
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_db, get_tenant_id
from app.api.org import blank_to_none, company_for_tenant, ensure_document_categories
from app.models import Company, DocumentCategory, EmployeeDocument
from app.schemas.document import DocumentCategoryCreate, DocumentCategoryRead, DocumentCategoryUpdate

router = APIRouter(prefix="/document-categories", tags=["document-categories"])


def _locked() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="The Lifecycle category cannot be edited",
    )


@router.get("", response_model=list[DocumentCategoryRead])
async def list_document_categories(
    company_id: uuid.UUID | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[DocumentCategory]:
    if company_id is not None:
        await company_for_tenant(session, company_id, tenant_id)
        return await ensure_document_categories(session, company_id)
    companies = list(
        (await session.scalars(select(Company.id).where(Company.tenant_id == tenant_id))).all()
    )
    rows: list[DocumentCategory] = []
    for company in companies:
        rows.extend(await ensure_document_categories(session, company))
    return rows


@router.post("", response_model=DocumentCategoryRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_access('documents.manage'))])
async def create_document_category(
    payload: DocumentCategoryCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> DocumentCategory:
    await company_for_tenant(session, payload.company_id, tenant_id)
    await ensure_document_categories(session, payload.company_id)
    highest = await session.scalar(
        select(func.max(DocumentCategory.sort_order)).where(DocumentCategory.company_id == payload.company_id)
    )
    row = DocumentCategory(
        company_id=payload.company_id,
        name=payload.name.strip(),
        locked=False,
        sort_order=(highest or 0) + 10,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A category with this name already exists for this company",
        ) from exc
    await session.refresh(row)
    return row


@router.patch("/{category_id}", response_model=DocumentCategoryRead, dependencies=[Depends(require_access('documents.manage'))])
async def update_document_category(
    category_id: uuid.UUID,
    payload: DocumentCategoryUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> DocumentCategory:
    row = await session.get(DocumentCategory, category_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document category not found")
    await company_for_tenant(session, row.company_id, tenant_id)
    if row.locked:
        raise _locked()
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        updates["name"] = blank_to_none(updates["name"].strip()) or row.name
    for field, value in updates.items():
        setattr(row, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A category with this name already exists for this company",
        ) from exc
    await session.refresh(row)
    return row


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_access('documents.manage'))])
async def delete_document_category(
    category_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> None:
    row = await session.get(DocumentCategory, category_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document category not found")
    await company_for_tenant(session, row.company_id, tenant_id)
    if row.locked:
        raise _locked()
    used = await session.scalar(
        select(EmployeeDocument.id).where(EmployeeDocument.category_id == category_id).limit(1)
    )
    if used is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category is in use")
    await session.delete(row)
