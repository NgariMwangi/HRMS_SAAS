import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.auth import TenantRead, TokenPairResponse, UserRead
from app.schemas.branch import BranchRead
from app.schemas.company import CompanyRead
from app.schemas.country import CountryRead
from app.schemas.department import DepartmentRead
from app.schemas.document import DocumentCategoryRead
from app.schemas.employee import EmployeeRead
from app.schemas.job_title import JobTitleRead
from app.schemas.leave import LeaveTypeRead


class PlatformAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    status: str


class PlatformTokenResponse(TokenPairResponse):
    admin: PlatformAdminRead


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(default=None, max_length=30)
    subscription_tier: str | None = Field(default=None, max_length=30)
    trial_ends_at: datetime | None = None


class StatusUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=30)


class CompanyAdminUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(default=None, max_length=30)


class BranchAdminUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(default=None, max_length=30)


class CountryAdminUpdate(BaseModel):
    is_active: bool


class AdminCompanyRead(CompanyRead):
    branches: list[BranchRead] = []


class TenantSummary(TenantRead):
    user_count: int
    company_count: int


class TenantDetail(TenantRead):
    users: list[UserRead]
    companies: list[AdminCompanyRead]


class UserAdminCreate(BaseModel):
    employee_id: uuid.UUID | None = None
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: str = Field(default="EMPLOYEE", max_length=30)
    status: str = Field(default="ACTIVE", max_length=30)


class UserAdminUpdate(BaseModel):
    employee_id: uuid.UUID | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)
    role: str | None = Field(default=None, max_length=30)
    status: str | None = Field(default=None, max_length=30)


class TenantWorkspace(BaseModel):
    tenant: TenantRead
    users: list[UserRead]
    companies: list[CompanyRead]
    branches: list[BranchRead]
    departments: list[DepartmentRead]
    job_titles: list[JobTitleRead]
    document_categories: list[DocumentCategoryRead]
    leave_types: list[LeaveTypeRead]
    employees: list[EmployeeRead]


class PlatformOverview(BaseModel):
    tenant_count: int
    active_tenant_count: int
    trial_count: int
    user_count: int
    company_count: int
    branch_count: int
    countries: list[CountryRead]
