import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CurrencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    symbol: str | None
    decimal_places: int
    is_active: bool


class CountryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    default_currency_id: uuid.UUID | None
    default_timezone: str | None
    is_active: bool
    created_at: datetime | None
    updated_at: datetime | None
    default_currency: CurrencyRead | None = None
