import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_platform_db
from app.models import PlatformAdmin
from app.schemas.payroll import (
    PayrollPackCreate,
    PayrollPackRead,
    PayrollPackSummary,
    PayrollPackUpdate,
)
from app.services.payroll import create_pack, list_packs, pack_to_read, pack_with_parts, publish_pack, update_pack

router = APIRouter(prefix="/platform", tags=["platform-payroll"])


@router.get("/payroll-packs", response_model=list[PayrollPackSummary])
async def list_platform_packs(
    country_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> list[dict]:
    return [pack_to_read(row) for row in await list_packs(session, country_id)]


@router.get("/payroll-packs/{pack_id}", response_model=PayrollPackRead)
async def get_platform_pack(
    pack_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> dict:
    pack = await pack_with_parts(session, pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Payroll pack not found")
    return pack_to_read(pack)


@router.post("/payroll-packs", response_model=PayrollPackRead, status_code=201)
async def create_platform_pack(
    payload: PayrollPackCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> dict:
    pack = await create_pack(session, payload.country_id, payload.effective_from, payload.copy_from_id)
    return pack_to_read(pack)


@router.put("/payroll-packs/{pack_id}", response_model=PayrollPackRead)
async def update_platform_pack(
    pack_id: uuid.UUID,
    payload: PayrollPackUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> dict:
    pack = await pack_with_parts(session, pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Payroll pack not found")
    return pack_to_read(await update_pack(session, pack, payload))


@router.post("/payroll-packs/{pack_id}/publish", response_model=PayrollPackRead)
async def publish_platform_pack(
    pack_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: PlatformAdmin = Depends(get_current_admin),
) -> dict:
    pack = await pack_with_parts(session, pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Payroll pack not found")
    return pack_to_read(await publish_pack(session, pack))
