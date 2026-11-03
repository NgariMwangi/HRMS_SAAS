from app.api.access_control import require_access
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_db, get_tenant_id
from app.api.org import company_for_tenant
from app.models import BenefitType, Employee, User
from app.schemas.payroll import (
    BenefitTypeCreate,
    BenefitTypeRead,
    BenefitTypeWrite,
    EmployeeBenefitRead,
    EmployeeBenefitWrite,
)
from app.services.benefits import (
    add_benefit,
    create_type,
    delete_benefit,
    delete_type,
    list_benefits,
    list_types,
    type_for_tenant,
    update_benefit,
    update_type,
)

router = APIRouter(tags=["benefits"])


async def _employee(session: AsyncSession, employee_id: uuid.UUID, tenant_id: uuid.UUID) -> Employee:
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    return employee


@router.get("/benefit-types", response_model=list[BenefitTypeRead], dependencies=[Depends(require_access('payroll.manage'))])
async def get_benefit_types(
    company_id: uuid.UUID = Query(),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[BenefitType]:
    return await list_types(session, company_id, tenant_id)


@router.post("/benefit-types", response_model=BenefitTypeRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_access('payroll.manage'))])
async def post_benefit_type(
    payload: BenefitTypeCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> BenefitType:
    return await create_type(session, tenant_id, payload)


@router.patch("/benefit-types/{type_id}", response_model=BenefitTypeRead, dependencies=[Depends(require_access('payroll.manage'))])
async def patch_benefit_type(
    type_id: uuid.UUID,
    payload: BenefitTypeWrite,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> BenefitType:
    row = await type_for_tenant(session, type_id, tenant_id)
    return await update_type(session, row, payload)


@router.delete("/benefit-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_access('payroll.manage'))])
async def remove_benefit_type(
    type_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> None:
    row = await type_for_tenant(session, type_id, tenant_id)
    await delete_type(session, row)


@router.get("/employees/{employee_id}/benefits", response_model=list[EmployeeBenefitRead], dependencies=[Depends(require_access('payroll.manage'))])
async def get_employee_benefits(
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    employee = await _employee(session, employee_id, tenant_id)
    return await list_benefits(session, employee)


@router.post(
    "/employees/{employee_id}/benefits",
    response_model=EmployeeBenefitRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access('payroll.manage'))])
async def post_employee_benefit(
    employee_id: uuid.UUID,
    payload: EmployeeBenefitWrite,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    employee = await _employee(session, employee_id, tenant_id)
    return await add_benefit(session, employee, payload)


@router.patch("/employees/{employee_id}/benefits/{benefit_id}", response_model=EmployeeBenefitRead, dependencies=[Depends(require_access('payroll.manage'))])
async def patch_employee_benefit(
    employee_id: uuid.UUID,
    benefit_id: uuid.UUID,
    payload: EmployeeBenefitWrite,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    employee = await _employee(session, employee_id, tenant_id)
    return await update_benefit(session, employee, benefit_id, payload)


@router.delete("/employees/{employee_id}/benefits/{benefit_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_access('payroll.manage'))])
async def remove_employee_benefit(
    employee_id: uuid.UUID,
    benefit_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> None:
    employee = await _employee(session, employee_id, tenant_id)
    await delete_benefit(session, employee, benefit_id)
