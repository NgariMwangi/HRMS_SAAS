from app.api.access_control import require_access
import uuid
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_tenant_db, get_tenant_id
from app.api.org import blank_to_none, company_for_tenant
from app.models import Company, LeaveRequest, LeaveType
from app.schemas.leave import LeaveTypeCreate, LeaveTypeRead, LeaveTypeUpdate

router = APIRouter(prefix="/leave-types", tags=["leave-types"])

DAY_BASES = {"CALENDAR", "WORKING"}
CENTS = Decimal("0.01")


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def require_day_basis(value: str) -> str:
    basis = value.strip().upper()
    if basis not in DAY_BASES:
        raise _bad("Count leave as calendar days or working days")
    return basis


def _qty(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def shape_leave_amounts(
    accrued: bool,
    days: Decimal | None,
    accrual_per_month: Decimal | None,
    *,
    rate_set: bool,
) -> tuple[Decimal, Decimal]:
    yearly = _qty(days or 0)
    if not accrued:
        return yearly, Decimal("0.00")
    if rate_set:
        if accrual_per_month is None or accrual_per_month <= 0:
            raise _bad("Enter how many days are earned each month")
        rate = _qty(accrual_per_month)
        return _qty(rate * 12), rate
    if yearly <= 0:
        raise _bad("Enter how many days are earned each month")
    return yearly, _qty(yearly / Decimal(12))


@router.get("", response_model=list[LeaveTypeRead])
async def list_leave_types(
    company_id: uuid.UUID | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[LeaveType]:
    if company_id is not None:
        await company_for_tenant(session, company_id, tenant_id)
        return list(
            (
                await session.scalars(
                    select(LeaveType)
                    .where(LeaveType.company_id == company_id)
                    .order_by(LeaveType.sort_order, LeaveType.name)
                )
            ).all()
        )
    companies = list((await session.scalars(select(Company.id).where(Company.tenant_id == tenant_id))).all())
    if not companies:
        return []
    return list(
        (
            await session.scalars(
                select(LeaveType)
                .where(LeaveType.company_id.in_(companies))
                .order_by(LeaveType.sort_order, LeaveType.name)
            )
        ).all()
    )


@router.post("", response_model=LeaveTypeRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_access('leave.manage'))])
async def create_leave_type(
    payload: LeaveTypeCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> LeaveType:
    await company_for_tenant(session, payload.company_id, tenant_id)
    name = payload.name.strip()
    if not name:
        raise _bad("Enter a leave type name")
    highest = await session.scalar(
        select(func.max(LeaveType.sort_order)).where(LeaveType.company_id == payload.company_id)
    )
    days, rate = shape_leave_amounts(
        payload.accrued,
        payload.days,
        payload.accrual_per_month,
        rate_set=payload.accrual_per_month is not None,
    )
    row = LeaveType(
        company_id=payload.company_id,
        name=name,
        days=days,
        accrued=payload.accrued,
        accrual_per_month=rate,
        day_basis=require_day_basis(payload.day_basis),
        sort_order=(highest or 0) + 10,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A leave type with this name already exists for this company",
        ) from exc
    await session.refresh(row)
    return row


@router.patch("/{leave_type_id}", response_model=LeaveTypeRead, dependencies=[Depends(require_access('leave.manage'))])
async def update_leave_type(
    leave_type_id: uuid.UUID,
    payload: LeaveTypeUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> LeaveType:
    row = await session.get(LeaveType, leave_type_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave type not found")
    await company_for_tenant(session, row.company_id, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        updates["name"] = blank_to_none(updates["name"].strip()) or row.name
    if "day_basis" in updates and updates["day_basis"] is not None:
        updates["day_basis"] = require_day_basis(updates["day_basis"])
    if "days" in updates or "accrued" in updates or "accrual_per_month" in updates:
        accrued = updates["accrued"] if "accrued" in updates else row.accrued
        days, rate = shape_leave_amounts(
            accrued,
            updates["days"] if "days" in updates else row.days,
            updates["accrual_per_month"] if "accrual_per_month" in updates else row.accrual_per_month,
            rate_set="accrual_per_month" in updates,
        )
        updates["accrued"] = accrued
        updates["days"] = days
        updates["accrual_per_month"] = rate
    for field, value in updates.items():
        setattr(row, field, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A leave type with this name already exists for this company",
        ) from exc
    await session.refresh(row)
    return row


@router.delete("/{leave_type_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_access('leave.manage'))])
async def delete_leave_type(
    leave_type_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
) -> None:
    row = await session.get(LeaveType, leave_type_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave type not found")
    await company_for_tenant(session, row.company_id, tenant_id)
    used = await session.scalar(
        select(LeaveRequest.id).where(LeaveRequest.leave_type_id == leave_type_id).limit(1)
    )
    if used is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Leave type is in use")
    await session.delete(row)
