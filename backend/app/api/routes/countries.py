from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models import Country
from app.schemas.country import CountryRead

router = APIRouter(prefix="/countries", tags=["countries"])


@router.get("", response_model=list[CountryRead])
async def list_countries(
    session: AsyncSession = Depends(get_session),
) -> list[Country]:
    result = await session.scalars(
        select(Country)
        .options(selectinload(Country.default_currency))
        .where(Country.is_active.is_(True))
        .order_by(Country.name)
    )
    return list(result.all())
