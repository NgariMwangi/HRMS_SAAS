"""Financial employee fields are separate from general employee summaries."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access_control import require_access
from app.api.deps import get_current_admin, get_platform_db, get_tenant_db, get_tenant_id
from app.api.routes.benefits import _employee as _get_employee


async def _employee(session, employee_id, tenant_id):
    person = await _get_employee(session, employee_id, tenant_id)
    company = session.info.get("domain_company_id")
    if company is not None and str(company) != str(person.company_id):
        raise HTTPException(403, "This address is restricted to its company")
    return person


class PaySettings(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    bank_name: str | None = Field(default=None, max_length=100)
    bank_branch: str | None = Field(default=None, max_length=100)
    bank_account_number: str | None = Field(default=None, max_length=50)
    bank_code: str | None = Field(default=None, max_length=20)
    swift_code: str | None = Field(default=None, max_length=20)
    prorate_payroll: bool = True

    @field_validator("bank_name", "bank_branch", "bank_account_number", "bank_code", "swift_code", mode="before")
    @classmethod
    def clean_text(cls, value):
        return value.strip() or None if isinstance(value, str) else value


router = APIRouter(tags=["employee payroll settings"], dependencies=[Depends(require_access("payroll.manage"))])
platform_router = APIRouter(prefix="/platform/tenants/{tenant_id}", tags=["platform employee payroll settings"], dependencies=[Depends(get_current_admin)])


async def save(session, employee_id, tenant_id, payload):
    person = await _employee(session, employee_id, tenant_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(person, key, value)
    await session.flush()
    return PaySettings.model_validate(person)


@router.get("/employees/{employee_id}/pay-settings", response_model=PaySettings)
async def read(employee_id: uuid.UUID, tenant_id: uuid.UUID = Depends(get_tenant_id), session: AsyncSession = Depends(get_tenant_db)):
    return PaySettings.model_validate(await _employee(session, employee_id, tenant_id))


@router.patch("/employees/{employee_id}/pay-settings", response_model=PaySettings)
async def update(employee_id: uuid.UUID, payload: PaySettings, tenant_id: uuid.UUID = Depends(get_tenant_id), session: AsyncSession = Depends(get_tenant_db)):
    return await save(session, employee_id, tenant_id, payload)


@platform_router.get("/employees/{employee_id}/pay-settings", response_model=PaySettings)
async def platform_read(tenant_id: uuid.UUID, employee_id: uuid.UUID, session: AsyncSession = Depends(get_platform_db)):
    return PaySettings.model_validate(await _employee(session, employee_id, tenant_id))


@platform_router.patch("/employees/{employee_id}/pay-settings", response_model=PaySettings)
async def platform_update(tenant_id: uuid.UUID, employee_id: uuid.UUID, payload: PaySettings, session: AsyncSession = Depends(get_platform_db)):
    return await save(session, employee_id, tenant_id, payload)
