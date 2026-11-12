import uuid
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Branch, Company, Department, DocumentCategory, Employee, JobTitle

ALLOWED_EMPLOYMENT_TYPES = {"FULL_TIME", "CONTRACT", "INTERN", "PROBATION"}
PERIOD_EMPLOYMENT_TYPES = {"INTERN", "PROBATION"}
END_DATE_EMPLOYMENT_TYPES = {"INTERN", "PROBATION", "CONTRACT"}

ALLOWED_STATUS = {"ACTIVE", "INACTIVE"}
ALLOWED_EMPLOYEE_STATUS = {"ACTIVE", "SUSPENDED", "TERMINATED"}
LIFECYCLE_CATEGORY_KEY = "LIFECYCLE"
DEFAULT_DOCUMENT_CATEGORIES = (
    ("PERSONAL", "Personal", False, 10),
    ("ACADEMIC", "Academic", False, 20),
    ("WORK", "Work related", False, 30),
    ("PERFORMANCE", "Performance related", False, 40),
    (LIFECYCLE_CATEGORY_KEY, "Lifecycle", True, 50),
)


def require_status(value: str) -> str:
    status_value = value.upper()
    if status_value not in ALLOWED_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be ACTIVE or INACTIVE",
        )
    return status_value


def require_employee_status(value: str) -> str:
    status_value = value.upper()
    if status_value not in ALLOWED_EMPLOYEE_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be ACTIVE, SUSPENDED, or TERMINATED",
        )
    return status_value


async def next_employee_number(session: AsyncSession, company_id: uuid.UUID) -> str:
    numbers = list(
        (
            await session.scalars(
                select(Employee.employee_number).where(Employee.company_id == company_id)
            )
        ).all()
    )
    highest = 0
    for number in numbers:
        suffix = number.rsplit("-", 1)[-1]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"EMP-{highest + 1:04d}"


def blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def require_employment_type(value: str) -> str:
    type_value = value.upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "FULLTIME": "FULL_TIME",
        "FULL_TIME": "FULL_TIME",
        "CONTRACT": "CONTRACT",
        "INTERN": "INTERN",
        "PROBATION": "PROBATION",
    }
    normalized = aliases.get(type_value)
    if normalized is None or normalized not in ALLOWED_EMPLOYMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="employment_type must be FULL_TIME, CONTRACT, INTERN, or PROBATION",
        )
    return normalized


def require_employment_period(
    employment_type: str,
    date_joined: date | None,
    date_ended: date | None,
    *,
    allow_incomplete: bool = False,
) -> None:
    if employment_type in PERIOD_EMPLOYMENT_TYPES:
        if not allow_incomplete and (date_joined is None or date_ended is None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Intern and probation records need a start date and an end date",
            )
    elif employment_type != "CONTRACT":
        return
    if date_ended is not None and date_joined is not None and date_ended < date_joined:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End date must be on or after the start date",
        )


async def company_for_tenant(
    session: AsyncSession,
    company_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> Company:
    company = await session.get(Company, company_id)
    if company is None or company.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="company_id does not belong to the current tenant",
        )
    return company


async def branch_for_company(
    session: AsyncSession,
    branch_id: uuid.UUID,
    company_id: uuid.UUID,
) -> Branch:
    branch = await session.get(Branch, branch_id)
    if branch is None or branch.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="branch_id does not belong to this company",
        )
    return branch


async def optional_department_for_company(
    session: AsyncSession,
    department_id: uuid.UUID | None,
    company_id: uuid.UUID,
) -> Department | None:
    if department_id is None:
        return None
    department = await session.get(Department, department_id)
    if department is None or department.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="department_id does not belong to this company",
        )
    return department


async def optional_job_title_for_company(
    session: AsyncSession,
    job_title_id: uuid.UUID | None,
    company_id: uuid.UUID,
) -> JobTitle | None:
    if job_title_id is None:
        return None
    title = await session.get(JobTitle, job_title_id)
    if title is None or title.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="job_title_id does not belong to this company",
        )
    return title


async def ensure_document_categories(session: AsyncSession, company_id: uuid.UUID) -> list[DocumentCategory]:
    existing = list(
        (
            await session.scalars(
                select(DocumentCategory).where(DocumentCategory.company_id == company_id)
            )
        ).all()
    )
    needed = (
        DEFAULT_DOCUMENT_CATEGORIES
        if not existing
        else tuple(item for item in DEFAULT_DOCUMENT_CATEGORIES if item[0] == LIFECYCLE_CATEGORY_KEY)
    )
    have = {row.system_key for row in existing if row.system_key}
    added = False
    for key, name, locked, order in needed:
        if key in have:
            continue
        session.add(
            DocumentCategory(
                company_id=company_id,
                name=name,
                system_key=key,
                locked=locked,
                sort_order=order,
            )
        )
        added = True
    if added:
        await session.flush()
    return list(
        (
            await session.scalars(
                select(DocumentCategory)
                .where(DocumentCategory.company_id == company_id)
                .order_by(DocumentCategory.sort_order, DocumentCategory.name)
            )
        ).all()
    )


async def document_category_for_company(
    session: AsyncSession,
    category_id: uuid.UUID,
    company_id: uuid.UUID,
    *,
    for_upload: bool = False,
) -> DocumentCategory:
    row = await session.get(DocumentCategory, category_id)
    if row is None or row.company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="category_id does not belong to this company",
        )
    if for_upload and row.locked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lifecycle files are added from a lifecycle action",
        )
    return row


async def lifecycle_category_for_company(
    session: AsyncSession,
    company_id: uuid.UUID,
) -> DocumentCategory:
    await ensure_document_categories(session, company_id)
    row = await session.scalar(
        select(DocumentCategory).where(
            DocumentCategory.company_id == company_id,
            DocumentCategory.system_key == LIFECYCLE_CATEGORY_KEY,
        )
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Lifecycle category is missing",
        )
    return row
