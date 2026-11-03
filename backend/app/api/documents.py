import uuid
from datetime import date, datetime

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.api.lifecycle import ALLOWED_ATTACHMENT_TYPES, MAX_ATTACHMENT_BYTES
from app.api.org import (
    blank_to_none,
    document_category_for_company,
    ensure_document_categories,
    lifecycle_category_for_company,
)
from app.models import (
    DocumentCategory,
    Employee,
    EmployeeDocument,
    EmployeeLifecycleAttachment,
    EmployeeLifecycleEvent,
)
from app.schemas.document import CompanyDocumentRead

MAX_EMPLOYEE_DOCUMENTS = 40


async def protect_performance_evidence(session: AsyncSession, document_id: uuid.UUID) -> None:
    from app.models.performance import GoalEvidence
    if await session.scalar(select(GoalEvidence.id).where(GoalEvidence.document_id == document_id)):
        raise HTTPException(409, "Performance evidence is append-only and cannot be deleted through employee documents")


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def lifecycle_event_label(event_type: str | None, reason: str | None, employment_type: str | None) -> str:
    if event_type == "HIRED":
        return "Employed"
    if event_type == "SUSPENDED":
        return "Suspended"
    if event_type == "REINSTATED":
        return "Unsuspended"
    if event_type == "TERMINATED":
        return "Terminated"
    if event_type == "EXTENDED":
        if employment_type == "INTERN":
            return "Internship extended"
        if employment_type == "CONTRACT":
            return "Contract extended"
        return "Extended"
    if event_type == "REHIRED":
        return "Rehired as new record" if reason == "NEW_RECORD" else "Rehired"
    if reason == "PROMOTION":
        return "Promoted"
    if reason == "DEMOTION":
        return "Demoted"
    if reason == "DEPARTMENT_CHANGE":
        return "Department changed"
    if reason == "TITLE_CHANGE":
        return "Job title changed"
    if event_type == "ROLE_CHANGED":
        return "Role changed"
    return event_type or "Lifecycle"


def _person_name(person: Employee) -> str:
    return " ".join(part for part in (person.first_name, person.other_names, person.last_name) if part)


def _upload_row(
    row: EmployeeDocument,
    person: Employee,
    category: DocumentCategory,
    *,
    size: int,
) -> CompanyDocumentRead:
    return CompanyDocumentRead(
        id=row.id,
        source="UPLOAD",
        company_id=row.company_id,
        employee_id=row.employee_id,
        employee_name=_person_name(person),
        employee_number=person.employee_number,
        category_id=category.id,
        category=category.name,
        locked=category.locked,
        filename=row.filename,
        content_type=row.content_type,
        size=size,
        issued_on=row.issued_on,
        expires_on=row.expires_on,
        note=row.note,
        created_at=row.created_at,
    )


def _lifecycle_row(
    row: EmployeeLifecycleAttachment,
    person: Employee,
    event: EmployeeLifecycleEvent,
    category: DocumentCategory,
    *,
    size: int,
) -> CompanyDocumentRead:
    return CompanyDocumentRead(
        id=row.id,
        source="LIFECYCLE",
        company_id=row.company_id,
        employee_id=row.employee_id,
        employee_name=_person_name(person),
        employee_number=person.employee_number,
        category_id=category.id,
        category=category.name,
        locked=True,
        filename=row.filename,
        content_type=row.content_type,
        size=size,
        event_id=row.event_id,
        event_type=event.event_type,
        event_label=lifecycle_event_label(event.event_type, event.reason, event.employment_type),
        created_at=row.created_at,
    )


def _matches_query(row: CompanyDocumentRead, term: str) -> bool:
    needle = term.lower()
    return any(
        (value or "").lower().find(needle) >= 0
        for value in (
            row.employee_name,
            row.employee_number,
            row.filename,
            row.category,
            row.event_label,
        )
    )


async def list_company_documents(
    session: AsyncSession,
    company_id: uuid.UUID,
    *,
    employee_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    q: str | None = None,
) -> list[CompanyDocumentRead]:
    await ensure_document_categories(session, company_id)
    lifecycle = await lifecycle_category_for_company(session, company_id)
    chosen = None
    if category_id is not None:
        chosen = await document_category_for_company(session, category_id, company_id)
    rows: list[CompanyDocumentRead] = []

    include_uploads = chosen is None or not chosen.locked
    include_lifecycle = chosen is None or chosen.locked

    if include_uploads:
        stmt = (
            select(EmployeeDocument, Employee, DocumentCategory)
            .join(Employee, EmployeeDocument.employee_id == Employee.id)
            .join(DocumentCategory, EmployeeDocument.category_id == DocumentCategory.id)
            .where(EmployeeDocument.company_id == company_id)
        )
        if employee_id is not None:
            stmt = stmt.where(EmployeeDocument.employee_id == employee_id)
        if chosen is not None:
            stmt = stmt.where(EmployeeDocument.category_id == chosen.id)
        stmt = stmt.add_columns(func.octet_length(EmployeeDocument.file_bytes))
        for document, person, category, nbytes in (await session.execute(stmt)).all():
            rows.append(_upload_row(document, person, category, size=int(nbytes or 0)))

    if include_lifecycle:
        stmt = (
            select(EmployeeLifecycleAttachment, Employee, EmployeeLifecycleEvent)
            .join(Employee, EmployeeLifecycleAttachment.employee_id == Employee.id)
            .join(EmployeeLifecycleEvent, EmployeeLifecycleAttachment.event_id == EmployeeLifecycleEvent.id)
            .where(EmployeeLifecycleAttachment.company_id == company_id)
        )
        if employee_id is not None:
            stmt = stmt.where(EmployeeLifecycleAttachment.employee_id == employee_id)
        stmt = stmt.add_columns(func.octet_length(EmployeeLifecycleAttachment.file_bytes))
        for document, person, event, nbytes in (await session.execute(stmt)).all():
            rows.append(_lifecycle_row(document, person, event, lifecycle, size=int(nbytes or 0)))

    if q and q.strip():
        term = q.strip()
        rows = [row for row in rows if _matches_query(row, term)]
    rows.sort(key=lambda row: row.created_at or datetime.min, reverse=True)
    return rows


def parse_optional_date(value: str | None) -> date | None:
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise _bad("Use YYYY-MM-DD for document dates") from exc


async def add_employee_document(
    session: AsyncSession,
    employee: Employee,
    *,
    upload: UploadFile,
    category_id: uuid.UUID,
    issued_on: date | None,
    expires_on: date | None,
    note: str | None,
    uploaded_by: uuid.UUID | None,
) -> CompanyDocumentRead:
    category = await document_category_for_company(
        session, category_id, employee.company_id, for_upload=True
    )
    if issued_on and expires_on and expires_on < issued_on:
        raise _bad("Expiry date must be on or after the issued date")
    content_type = (upload.content_type or "").lower()
    if content_type not in ALLOWED_ATTACHMENT_TYPES:
        raise _bad("Documents must be PDF, Word, image, or text files")
    data = await upload.read()
    if not data or len(data) > MAX_ATTACHMENT_BYTES:
        raise _bad("Each document must be 50 MB or smaller")
    existing = await session.scalar(
        select(func.count()).select_from(EmployeeDocument).where(
            EmployeeDocument.employee_id == employee.id
        )
    )
    if (existing or 0) >= MAX_EMPLOYEE_DOCUMENTS:
        raise _bad(f"At most {MAX_EMPLOYEE_DOCUMENTS} uploaded documents per employee")
    row = EmployeeDocument(
        company_id=employee.company_id,
        employee_id=employee.id,
        category_id=category.id,
        filename=(upload.filename or "document").rsplit("/", 1)[-1][:255],
        content_type=content_type,
        file_bytes=data,
        issued_on=issued_on,
        expires_on=expires_on,
        note=blank_to_none(note or ""),
        uploaded_by=uploaded_by,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return _upload_row(row, employee, category, size=len(data))


async def employee_document_file(
    session: AsyncSession,
    employee_id: uuid.UUID,
    document_id: uuid.UUID,
) -> EmployeeDocument:
    row = await session.scalar(
        select(EmployeeDocument)
        .options(undefer(EmployeeDocument.file_bytes))
        .where(EmployeeDocument.id == document_id, EmployeeDocument.employee_id == employee_id)
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return row
