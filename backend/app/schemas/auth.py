import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.branch import BranchRead
from app.schemas.company import CompanyRead


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    subscription_tier: str
    status: str
    trial_ends_at: datetime | None
    created_at: datetime | None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str
    role: str
    status: str
    employee_id: uuid.UUID | None = None


class RegisterRequest(BaseModel):
    owner_full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    tenant_name: str = Field(min_length=1, max_length=255)
    company_name: str = Field(min_length=1, max_length=255)
    company_legal_name: str | None = Field(default=None, max_length=255)
    country_id: uuid.UUID
    branch_name: str = Field(default="Head Office", min_length=1, max_length=255)
    branch_code: str = Field(default="HQ", min_length=1, max_length=50)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int


class TokenResponse(TokenPairResponse):
    user: UserRead
    tenant: TenantRead
    company: CompanyRead | None = None
    branch: BranchRead | None = None
