import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.services.branding import normalise_logo


class BrandingWrite(BaseModel):
    theme_color: str = Field(default="#4F46E5", pattern=r"^#[0-9A-Fa-f]{6}$")
    logo_data_url: str | None = Field(default=None, max_length=2_800_000)

    @field_validator("logo_data_url")
    @classmethod
    def logo(cls, value):
        return normalise_logo(value)


class CompanyCreate(BrandingWrite):
    name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    registration_number: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=255)
    status: str = Field(default="ACTIVE", max_length=30)


class CompanyUpdate(BaseModel):
    theme_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    logo_data_url: str | None = Field(default=None, max_length=2_800_000)

    @field_validator("theme_color")
    @classmethod
    def color(cls, value):
        if value is None:
            raise ValueError("Choose a theme color")
        return value.upper()

    @field_validator("logo_data_url")
    @classmethod
    def logo(cls, value):
        return normalise_logo(value)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    legal_name: str | None = Field(default=None, max_length=255)
    registration_number: str | None = Field(default=None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    website: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=30)


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    theme_color: str
    logo_data_url: str | None
    legal_name: str | None
    registration_number: str | None
    email: str | None
    phone: str | None
    website: str | None
    status: str
    created_at: datetime | None
    updated_at: datetime | None
