from app.api.access_control import require_access
import calendar
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_db, get_tenant_id
from app.api.org import branch_for_company, company_for_tenant
from app.models import Company, Country, PublicHoliday
from app.schemas.leave import PublicHolidayCreate, PublicHolidayRead, PublicHolidayUpdate

router = APIRouter(prefix="/public-holidays", tags=["public-holidays"])

KINDS = {"YEARLY", "ONCE"}


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def require_kind(value: str) -> str:
    kind = value.strip().upper()
    if kind not in KINDS:
        raise _bad("Use a yearly holiday or a one-off date")
    return kind


def shaped(
    kind: str,
    month: int | None,
    day: int | None,
    observed_on: date | None,
) -> tuple[int | None, int | None, date | None]:
    if kind == "YEARLY":
        if month is None or day is None:
            raise _bad("Yearly holidays need a month and day")
        last = calendar.monthrange(2024, month)[1]
        if day > last:
            raise _bad("That day does not exist in this month")
        return month, day, None
    if observed_on is None:
        raise _bad("One-off holidays need a date")
    return None, None, observed_on


async def holiday_country(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    branch_id: uuid.UUID | None,
    country_id: uuid.UUID | None,
) -> uuid.UUID | None:
    if branch_id is not None:
        branch = await branch_for_company(session, branch_id, company_id)
        return branch.country_id
    if country_id is None:
        return None
    country = await session.get(Country, country_id)
    if country is None:
        raise _bad("Unknown country")
    return country.id


@router.get("", response_model=list[PublicHolidayRead])
async def list_public_holidays(
    company_id: uuid.UUID | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[PublicHoliday]:
    if company_id is not None:
        await company_for_tenant(session, company_id, tenant_id)
        stmt = select(PublicHoliday).where(PublicHoliday.company_id == company_id)
        if branch_id is not None:
            branch = await branch_for_company(session, branch_id, company_id)
            stmt = stmt.where(
                or_(PublicHoliday.country_id.is_(None), PublicHoliday.country_id == branch.country_id)
            )
        return list(
            (
                await session.scalars(
                    stmt.order_by(PublicHoliday.kind.desc(), PublicHoliday.month, PublicHoliday.day, PublicHoliday.observed_on, PublicHoliday.name)
                )
            ).all()
        )
    companies = list((await session.scalars(select(Company.id).where(Company.tenant_id == tenant_id))).all())
    if not companies:
        return []
    return list(
        (
            await session.scalars(
                select(PublicHoliday)
                .where(PublicHoliday.company_id.in_(companies))
                .order_by(PublicHoliday.kind.desc(), PublicHoliday.month, PublicHoliday.day, PublicHoliday.observed_on, PublicHoliday.name)
            )
        ).all()
    )


@router.post("", response_model=PublicHolidayRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_access('leave.manage'))])
async def create_public_holiday(
    payload: PublicHolidayCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> PublicHoliday:
    await company_for_tenant(session, payload.company_id, tenant_id)
    name = payload.name.strip()
    if not name:
        raise _bad("Enter a holiday name")
    kind = require_kind(payload.kind)
    month, day, observed_on = shaped(kind, payload.month, payload.day, payload.observed_on)
    country_id = await holiday_country(
        session,
        company_id=payload.company_id,
        branch_id=payload.branch_id,
        country_id=payload.country_id,
    )
    row = PublicHoliday(
        company_id=payload.company_id,
        country_id=country_id,
        name=name,
        kind=kind,
        month=month,
        day=day,
        observed_on=observed_on,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This holiday already exists for this company",
        ) from exc
    await session.refresh(row)
    return row


@router.patch("/{holiday_id}", response_model=PublicHolidayRead, dependencies=[Depends(require_access('leave.manage'))])
async def update_public_holiday(
    holiday_id: uuid.UUID,
    payload: PublicHolidayUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> PublicHoliday:
    row = await session.get(PublicHoliday, holiday_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holiday not found")
    await company_for_tenant(session, row.company_id, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip() or row.name
    kind = require_kind(updates["kind"]) if updates.get("kind") else row.kind
    month = updates["month"] if "month" in updates else row.month
    day = updates["day"] if "day" in updates else row.day
    observed_on = updates["observed_on"] if "observed_on" in updates else row.observed_on
    month, day, observed_on = shaped(kind, month, day, observed_on)
    row.name = updates.get("name", row.name)
    row.kind = kind
    row.month = month
    row.day = day
    row.observed_on = observed_on
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This holiday already exists for this company",
        ) from exc
    await session.refresh(row)
    return row


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_access('leave.manage'))])
async def delete_public_holiday(
    holiday_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> None:
    row = await session.get(PublicHoliday, holiday_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holiday not found")
    await company_for_tenant(session, row.company_id, tenant_id)
    await session.delete(row)
