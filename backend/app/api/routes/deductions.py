from app.api.access_control import require_access
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_tenant_db, get_tenant_id
from app.api.org import company_for_tenant
from app.models import DeductionType, Employee, User
from app.schemas.payroll import (
    DeductionEnrol,
    DeductionEnrolCandidate,
    DeductionEnrolResult,
    DeductionTypeCreate,
    DeductionTypeRead,
    DeductionTypeWrite,
    EmployeeDeductionRead,
    EmployeeDeductionWrite,
)
from app.services.deductions import (
    add_employee_deduction,
    create_type,
    delete_employee_deduction,
    delete_type,
    enrol_candidates,
    enrol_employees,
    list_employee_deductions,
    list_types,
    type_for_tenant,
    update_employee_deduction,
    update_type,
)

router = APIRouter(tags=["deductions"])


async def _employee(session: AsyncSession, employee_id: uuid.UUID, tenant_id: uuid.UUID) -> Employee:
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    return employee


@router.get("/deduction-types", response_model=list[DeductionTypeRead], dependencies=[Depends(require_access('payroll.manage'))])
async def get_deduction_types(
    company_id: uuid.UUID = Query(),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[DeductionType]:
    return await list_types(session, company_id, tenant_id)


@router.post("/deduction-types", response_model=DeductionTypeRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_access('payroll.manage'))])
async def post_deduction_type(
    payload: DeductionTypeCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> DeductionType:
    return await create_type(session, tenant_id, payload)


@router.patch("/deduction-types/{type_id}", response_model=DeductionTypeRead, dependencies=[Depends(require_access('payroll.manage'))])
async def patch_deduction_type(
    type_id: uuid.UUID,
    payload: DeductionTypeWrite,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> DeductionType:
    row = await type_for_tenant(session, type_id, tenant_id)
    return await update_type(session, row, payload)


@router.delete("/deduction-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_access('payroll.manage'))])
async def remove_deduction_type(
    type_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> None:
    row = await type_for_tenant(session, type_id, tenant_id)
    await delete_type(session, row)


@router.get("/deduction-types/{type_id}/enrol", response_model=list[DeductionEnrolCandidate], dependencies=[Depends(require_access('payroll.manage'))])
async def get_deduction_enrol_candidates(
    type_id: uuid.UUID,
    branch_id: uuid.UUID | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    row = await type_for_tenant(session, type_id, tenant_id)
    return await enrol_candidates(session, row, branch_id)


@router.post("/deduction-types/{type_id}/enrol", response_model=DeductionEnrolResult, dependencies=[Depends(require_access('payroll.manage'))])
async def post_deduction_enrol(
    type_id: uuid.UUID,
    payload: DeductionEnrol,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    row = await type_for_tenant(session, type_id, tenant_id)
    return await enrol_employees(session, row, payload)


@router.get("/employees/{employee_id}/deductions", response_model=list[EmployeeDeductionRead], dependencies=[Depends(require_access('payroll.manage'))])
async def get_employee_deductions(
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    employee = await _employee(session, employee_id, tenant_id)
    return await list_employee_deductions(session, employee)


@router.post(
    "/employees/{employee_id}/deductions",
    response_model=EmployeeDeductionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_access('payroll.manage'))])
async def post_employee_deduction(
    employee_id: uuid.UUID,
    payload: EmployeeDeductionWrite,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    employee = await _employee(session, employee_id, tenant_id)
    return await add_employee_deduction(session, employee, payload)


@router.patch("/employees/{employee_id}/deductions/{deduction_id}", response_model=EmployeeDeductionRead, dependencies=[Depends(require_access('payroll.manage'))])
async def patch_employee_deduction(
    employee_id: uuid.UUID,
    deduction_id: uuid.UUID,
    payload: EmployeeDeductionWrite,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    employee = await _employee(session, employee_id, tenant_id)
    return await update_employee_deduction(session, employee, deduction_id, payload)


@router.delete("/employees/{employee_id}/deductions/{deduction_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_access('payroll.manage'))])
async def remove_employee_deduction(
    employee_id: uuid.UUID,
    deduction_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> None:
    employee = await _employee(session, employee_id, tenant_id)
    await delete_employee_deduction(session, employee, deduction_id)
