from app.api.access_control import require_access
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_tenant_db, get_tenant_id
from app.api.org import branch_for_company, company_for_tenant
from app.models import Employee, EmployeeCompensation, PayrollPayslip, PayrollRun, User
from app.schemas.payroll import (
    CompensationCreate,
    CompensationRead,
    CompensationUpdate,
    PayrollRunCreate,
    PayrollRunRead,
    PayrollSettingsRead,
    PayrollSettingsUpdate,
)
from app.services.payroll import (
    add_compensation,
    approve_run,
    unapprove_run,
    update_compensation,
    create_run,
    payroll_skip_reason,
    list_compensation,
    load_run,
    run_to_read,
    save_settings,
    settings_for,
)

router = APIRouter(tags=["payroll"])


@router.get("/payroll/settings", response_model=PayrollSettingsRead, dependencies=[Depends(require_access('payroll.manage'))])
async def get_payroll_settings(
    company_id: uuid.UUID = Query(),
    branch_id: uuid.UUID | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    branch = None
    if branch_id is not None:
        branch = await branch_for_company(session, branch_id, company_id)
    return await settings_for(session, company_id, tenant_id, branch)


@router.put("/payroll/settings", response_model=PayrollSettingsRead, dependencies=[Depends(require_access('payroll.manage'))])
async def put_payroll_settings(
    payload: PayrollSettingsUpdate,
    company_id: uuid.UUID = Query(),
    branch_id: uuid.UUID | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    await save_settings(session, company_id, tenant_id, payload.frequency, payload.salary_structure)
    branch = None
    if branch_id is not None:
        branch = await branch_for_company(session, branch_id, company_id)
    return await settings_for(session, company_id, tenant_id, branch)


@router.get("/employees/{employee_id}/compensation", response_model=list[CompensationRead], dependencies=[Depends(require_access('payroll.manage'))])
async def get_employee_compensation(
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list:
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    return await list_compensation(session, employee)


@router.post("/employees/{employee_id}/compensation", response_model=CompensationRead, status_code=201, dependencies=[Depends(require_access('payroll.manage'))])
async def post_employee_compensation(
    employee_id: uuid.UUID,
    payload: CompensationCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> EmployeeCompensation:
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    return await add_compensation(session, employee, payload)


@router.patch("/employees/{employee_id}/compensation/{compensation_id}", response_model=CompensationRead, dependencies=[Depends(require_access('payroll.manage'))])
async def patch_employee_compensation(
    employee_id: uuid.UUID,
    compensation_id: uuid.UUID,
    payload: CompensationUpdate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> EmployeeCompensation:
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    return await update_compensation(session, employee, compensation_id, payload)


async def payroll_people(session, company_id, tenant_id, branch_id, period_end=None):
    await company_for_tenant(session, company_id, tenant_id)
    await branch_for_company(session, branch_id, company_id)
    query = select(Employee).where(Employee.company_id == company_id, Employee.branch_id == branch_id)
    if period_end is None:
        query = query.where(Employee.status == "ACTIVE")
    rows = (await session.scalars(query.order_by(Employee.last_name, Employee.first_name))).all()
    salaries = {}
    if period_end is not None and rows:
        # Match compensation_as_of, fetching the latest applicable salary and
        # its allowances for everyone together rather than one query per person.
        pay_rows = (await session.scalars(select(EmployeeCompensation).where(EmployeeCompensation.is_historical.is_(False))
            .options(selectinload(EmployeeCompensation.lines))
            .where(EmployeeCompensation.employee_id.in_([row.id for row in rows]),
                EmployeeCompensation.effective_from <= period_end)
            .distinct(EmployeeCompensation.employee_id)
            .order_by(EmployeeCompensation.employee_id, EmployeeCompensation.effective_from.desc()))).all()
        salaries = {pay.employee_id: pay for pay in pay_rows}
    result = []
    for row in rows:
        reason = payroll_skip_reason(row, salaries.get(row.id), period_end) if period_end is not None else None
        result.append({"id": row.id, "name": " ".join(filter(None, [row.first_name, row.other_names, row.last_name])),
            "employee_number": row.employee_number, "status": row.status,
            "eligible": reason is None, "skip_reason": reason})
    return result


@router.get("/payroll/employees", dependencies=[Depends(require_access('payroll.manage'))])
async def payroll_employees(company_id: uuid.UUID, branch_id: uuid.UUID,
    period_end: date | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id), session: AsyncSession = Depends(get_tenant_db)):
    return await payroll_people(session, company_id, tenant_id, branch_id, period_end)


@router.get("/payroll/runs", response_model=list[PayrollRunRead], dependencies=[Depends(require_access('payroll.manage'))])
async def list_payroll_runs(
    company_id: uuid.UUID = Query(),
    branch_id: uuid.UUID = Query(),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    await company_for_tenant(session, company_id, tenant_id)
    await branch_for_company(session, branch_id, company_id)
    rows = list(
        (
            await session.scalars(
                select(PayrollRun)
                .options(selectinload(PayrollRun.payslips).selectinload(PayrollPayslip.lines))
                .where(PayrollRun.company_id == company_id, PayrollRun.branch_id == branch_id)
                .order_by(PayrollRun.period_start.desc())
            )
        ).all()
    )
    return [await run_to_read(session, row) for row in rows]


@router.post("/payroll/runs", response_model=PayrollRunRead, status_code=201, dependencies=[Depends(require_access('payroll.manage'))])
async def post_payroll_run(
    payload: PayrollRunCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    run, skipped = await create_run(
        session, payload.company_id, tenant_id, payload.branch_id, payload.period_start, payload.period_end, payload.excluded_employee_ids
    )
    loaded = await load_run(session, run.id)
    assert loaded is not None
    return await run_to_read(session, loaded, skipped)


@router.get("/payroll/runs/{run_id}", response_model=PayrollRunRead, dependencies=[Depends(require_access('payroll.manage'))])
async def get_payroll_run(
    run_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    run = await load_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    await company_for_tenant(session, run.company_id, tenant_id)
    return await run_to_read(session, run)


@router.post("/payroll/runs/{run_id}/approve", response_model=PayrollRunRead, dependencies=[Depends(require_access('payroll.manage'))])
async def approve_payroll_run(
    run_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    run = await load_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    await company_for_tenant(session, run.company_id, tenant_id)
    approved = await approve_run(session, run)
    return await run_to_read(session, approved)


@router.post("/payroll/runs/{run_id}/unapprove", response_model=PayrollRunRead, dependencies=[Depends(require_access('payroll.manage'))])
async def unapprove_payroll_run(
    run_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    session: AsyncSession = Depends(get_tenant_db),
    user: User = Depends(get_current_user),
) -> dict:
    run = await load_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    await company_for_tenant(session, run.company_id, tenant_id)
    return await run_to_read(session, await unapprove_run(session, run))
