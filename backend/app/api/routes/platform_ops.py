import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin, get_platform_db
from app.api.leave import (
    cancel_request,
    create_hr_request,
    decide_as_hr,
    leave_type_for_company,
    list_requests,
    load_request,
    request_to_read,
)
from app.api.lifecycle import event_to_read, list_company_events
from app.api.org import branch_for_company, company_for_tenant
from app.api.routes.leave_balances import _read as balance_read
from app.api.routes.public_holidays import holiday_country, require_kind, shaped
from app.core.security import hash_password
from app.models import (
    Company,
    Employee,
    EmployeeCompensation,
    LeaveBalance,
    LeaveType,
    PayrollPayslip,
    PayrollRun,
    PublicHoliday,
    Tenant,
    User,
)
from app.schemas.attendance import AttendanceMark, AttendanceRead, EmployeeLoginCreate
from app.schemas.auth import UserRead
from app.schemas.employee import EmployeeRead, LifecycleEventRead
from app.schemas.leave import (
    LeaveBalanceAdjust,
    LeaveBalanceRead,
    LeaveDecisionWrite,
    LeaveHrCreate,
    LeaveRequestRead,
    PublicHolidayCreate,
    PublicHolidayRead,
    PublicHolidayUpdate,
)
from app.schemas.payroll import (
    CompensationCreate,
    CompensationRead,
    CompensationUpdate,
    DeductionEnrol,
    DeductionEnrolCandidate,
    DeductionEnrolResult,
    DeductionTypeCreate,
    DeductionTypeRead,
    DeductionTypeWrite,
    BenefitTypeCreate,
    BenefitTypeRead,
    BenefitTypeWrite,
    EmployeeBenefitRead,
    EmployeeBenefitWrite,
    EmployeeDeductionRead,
    EmployeeDeductionWrite,
    PayrollRunCreate,
    PayrollRunRead,
    PayrollSettingsRead,
    PayrollSettingsUpdate,
)
from app.services.attendance import list_day, mark_day
from app.services.benefits import (
    add_benefit,
    delete_benefit,
    list_benefits,
    update_benefit,
)
from app.services.benefits import create_type as create_benefit_type
from app.services.benefits import delete_type as delete_benefit_type
from app.services.benefits import list_types as list_benefit_types
from app.services.benefits import type_for_tenant as benefit_type_for_tenant
from app.services.benefits import update_type as update_benefit_type
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
from app.services.leave_balances import as_of_for_year, balance_for
from app.services.payroll import (
    add_compensation,
    approve_run,
    create_run,
    list_compensation,
    load_run,
    run_to_read,
    save_settings,
    settings_for,
    update_compensation,
)

router = APIRouter(prefix="/platform/tenants/{tenant_id}", tags=["platform-ops"])

HR_ROLES = ("OWNER", "ADMIN", "HR")


async def _tenant(tenant_id: uuid.UUID, session: AsyncSession) -> Tenant:
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


async def _employee(session: AsyncSession, employee_id: uuid.UUID, tenant_id: uuid.UUID) -> Employee:
    employee = await session.get(Employee, employee_id, options=(selectinload(Employee.login_user),))
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    await company_for_tenant(session, employee.company_id, tenant_id)
    return employee


async def _acting_hr(session: AsyncSession, tenant_id: uuid.UUID) -> User:
    user = await session.scalar(
        select(User)
        .where(
            User.tenant_id == tenant_id,
            User.status == "ACTIVE",
            User.role.in_(HR_ROLES),
        )
        .order_by(
            case(
                (User.role == "OWNER", 0),
                (User.role == "ADMIN", 1),
                else_=2,
            )
        )
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This workspace has no active owner, admin, or HR user to record the action",
        )
    return user


@router.get("/lifecycle", response_model=list[LifecycleEventRead])
async def list_lifecycle(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID = Query(),
    event_type: str | None = Query(default=None),
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[LifecycleEventRead]:
    await _tenant(tenant_id, session)
    await company_for_tenant(session, company_id, tenant_id)
    rows = await list_company_events(session, company_id, event_type, q)
    return [event_to_read(event, person) for event, person in rows]


@router.get("/leave-requests", response_model=list[LeaveRequestRead])
async def list_leave_requests(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID | None = Query(default=None),
    employee_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[LeaveRequestRead]:
    await _tenant(tenant_id, session)
    rows = await list_requests(session, tenant_id, company_id, employee_id, status)
    return [await request_to_read(session, row) for row in rows]


@router.post("/leave-requests/hr", response_model=LeaveRequestRead, status_code=201)
async def hr_apply_leave(
    tenant_id: uuid.UUID,
    payload: LeaveHrCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> LeaveRequestRead:
    await _tenant(tenant_id, session)
    actor = await _acting_hr(session, tenant_id)
    row = await create_hr_request(
        session,
        tenant_id,
        actor,
        payload.employee_id,
        payload.leave_type_id,
        payload.start_on,
        payload.end_on,
        payload.reason,
        payload.hr_action,
    )
    return await request_to_read(session, row)


@router.post("/leave-requests/{request_id}/hr-decision", response_model=LeaveRequestRead)
async def hr_decide_leave(
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: LeaveDecisionWrite,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> LeaveRequestRead:
    await _tenant(tenant_id, session)
    actor = await _acting_hr(session, tenant_id)
    row = await load_request(session, request_id, tenant_id)
    row = await decide_as_hr(session, row, actor, payload.decision, payload.note)
    return await request_to_read(session, row)


@router.post("/leave-requests/{request_id}/cancel", response_model=LeaveRequestRead)
async def cancel_leave_request(
    tenant_id: uuid.UUID,
    request_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> LeaveRequestRead:
    await _tenant(tenant_id, session)
    actor = await _acting_hr(session, tenant_id)
    row = await load_request(session, request_id, tenant_id)
    row = await cancel_request(session, row, actor)
    return await request_to_read(session, row)


@router.get("/leave-balances", response_model=list[LeaveBalanceRead])
async def list_leave_balances(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID | None = Query(default=None),
    employee_id: uuid.UUID | None = Query(default=None),
    leave_type_id: uuid.UUID | None = Query(default=None),
    year: int | None = Query(default=None, ge=2000, le=2100),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[LeaveBalanceRead]:
    await _tenant(tenant_id, session)
    chosen_year = year or date.today().year
    as_of = as_of_for_year(chosen_year)
    if company_id is not None:
        await company_for_tenant(session, company_id, tenant_id)
        company_ids = [company_id]
    else:
        company_ids = list((await session.scalars(select(Company.id).where(Company.tenant_id == tenant_id))).all())
    if not company_ids:
        return []

    people_stmt = select(Employee).where(Employee.company_id.in_(company_ids)).order_by(Employee.first_name, Employee.last_name)
    if employee_id is not None:
        people_stmt = people_stmt.where(Employee.id == employee_id)
    else:
        people_stmt = people_stmt.where(Employee.status.in_(("ACTIVE", "SUSPENDED")))
    people = list((await session.scalars(people_stmt)).all())
    if employee_id is not None and not people:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if employee_id is not None:
        await company_for_tenant(session, people[0].company_id, tenant_id)

    types_stmt = select(LeaveType).where(LeaveType.company_id.in_(company_ids)).order_by(LeaveType.sort_order, LeaveType.name)
    if leave_type_id is not None:
        types_stmt = types_stmt.where(LeaveType.id == leave_type_id)
    types = list((await session.scalars(types_stmt)).all())
    if not people or not types:
        return []

    out: list[LeaveBalanceRead] = []
    for person in people:
        for leave_type in types:
            if leave_type.company_id != person.company_id:
                continue
            out.append(balance_read(await balance_for(session, person, leave_type, chosen_year, as_of)))
    return out


@router.patch("/leave-balances", response_model=LeaveBalanceRead)
async def adjust_leave_balance(
    tenant_id: uuid.UUID,
    payload: LeaveBalanceAdjust,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> LeaveBalanceRead:
    employee = await _employee(session, payload.employee_id, tenant_id)
    leave_type = await leave_type_for_company(session, payload.leave_type_id, employee.company_id)
    row = await session.scalar(
        select(LeaveBalance).where(
            LeaveBalance.employee_id == employee.id,
            LeaveBalance.leave_type_id == leave_type.id,
            LeaveBalance.year == payload.year,
        )
    )
    extra = Decimal(payload.extra_days)
    if row is None:
        if extra != 0:
            session.add(
                LeaveBalance(
                    company_id=employee.company_id,
                    employee_id=employee.id,
                    leave_type_id=leave_type.id,
                    year=payload.year,
                    extra_days=extra,
                )
            )
            await session.flush()
    else:
        row.extra_days = extra
        await session.flush()
    return balance_read(await balance_for(session, employee, leave_type, payload.year, as_of_for_year(payload.year)))


@router.get("/public-holidays", response_model=list[PublicHolidayRead])
async def list_public_holidays(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[PublicHoliday]:
    await _tenant(tenant_id, session)
    if company_id is not None:
        await company_for_tenant(session, company_id, tenant_id)
        stmt = select(PublicHoliday).where(PublicHoliday.company_id == company_id)
        if branch_id is not None:
            branch = await branch_for_company(session, branch_id, company_id)
            stmt = stmt.where(
                or_(PublicHoliday.country_id.is_(None), PublicHoliday.country_id == branch.country_id)
            )
        return list(
            (
                await session.scalars(
                    stmt.order_by(
                        PublicHoliday.kind.desc(),
                        PublicHoliday.month,
                        PublicHoliday.day,
                        PublicHoliday.observed_on,
                        PublicHoliday.name,
                    )
                )
            ).all()
        )
    companies = list((await session.scalars(select(Company.id).where(Company.tenant_id == tenant_id))).all())
    if not companies:
        return []
    return list(
        (
            await session.scalars(
                select(PublicHoliday)
                .where(PublicHoliday.company_id.in_(companies))
                .order_by(
                    PublicHoliday.kind.desc(),
                    PublicHoliday.month,
                    PublicHoliday.day,
                    PublicHoliday.observed_on,
                    PublicHoliday.name,
                )
            )
        ).all()
    )


@router.post("/public-holidays", response_model=PublicHolidayRead, status_code=status.HTTP_201_CREATED)
async def create_public_holiday(
    tenant_id: uuid.UUID,
    payload: PublicHolidayCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> PublicHoliday:
    await company_for_tenant(session, payload.company_id, tenant_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Enter a holiday name")
    kind = require_kind(payload.kind)
    month, day, observed_on = shaped(kind, payload.month, payload.day, payload.observed_on)
    country_id = await holiday_country(
        session,
        company_id=payload.company_id,
        branch_id=payload.branch_id,
        country_id=payload.country_id,
    )
    row = PublicHoliday(
        company_id=payload.company_id,
        country_id=country_id,
        name=name,
        kind=kind,
        month=month,
        day=day,
        observed_on=observed_on,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This holiday already exists for this company",
        ) from exc
    await session.refresh(row)
    return row


@router.patch("/public-holidays/{holiday_id}", response_model=PublicHolidayRead)
async def update_public_holiday(
    tenant_id: uuid.UUID,
    holiday_id: uuid.UUID,
    payload: PublicHolidayUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> PublicHoliday:
    row = await session.get(PublicHoliday, holiday_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holiday not found")
    await company_for_tenant(session, row.company_id, tenant_id)
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip() or row.name
    kind = require_kind(updates["kind"]) if updates.get("kind") else row.kind
    month = updates["month"] if "month" in updates else row.month
    day = updates["day"] if "day" in updates else row.day
    observed_on = updates["observed_on"] if "observed_on" in updates else row.observed_on
    month, day, observed_on = shaped(kind, month, day, observed_on)
    row.name = updates.get("name", row.name)
    row.kind = kind
    row.month = month
    row.day = day
    row.observed_on = observed_on
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This holiday already exists for this company",
        ) from exc
    await session.refresh(row)
    return row


@router.delete("/public-holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_public_holiday(
    tenant_id: uuid.UUID,
    holiday_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    row = await session.get(PublicHoliday, holiday_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holiday not found")
    await company_for_tenant(session, row.company_id, tenant_id)
    await session.delete(row)


@router.get("/attendance", response_model=list[AttendanceRead])
async def list_attendance(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    branch_id: uuid.UUID,
    work_on: date = Query(),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[dict]:
    await company_for_tenant(session, company_id, tenant_id)
    await branch_for_company(session, branch_id, company_id)
    return await list_day(session, company_id, branch_id, work_on)


@router.put("/attendance", response_model=AttendanceRead)
async def mark_attendance(
    tenant_id: uuid.UUID,
    payload: AttendanceMark,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> dict:
    employee = await _employee(session, payload.employee_id, tenant_id)
    return await mark_day(session, employee, payload.work_on, payload.status, payload.note)


@router.get("/payroll/settings", response_model=PayrollSettingsRead)
async def get_payroll_settings(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID = Query(),
    branch_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> dict:
    await company_for_tenant(session, company_id, tenant_id)
    branch = None
    if branch_id is not None:
        branch = await branch_for_company(session, branch_id, company_id)
    return await settings_for(session, company_id, tenant_id, branch)


@router.put("/payroll/settings", response_model=PayrollSettingsRead)
async def put_payroll_settings(
    tenant_id: uuid.UUID,
    payload: PayrollSettingsUpdate,
    company_id: uuid.UUID = Query(),
    branch_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> dict:
    await save_settings(session, company_id, tenant_id, payload.frequency, payload.salary_structure)
    branch = None
    if branch_id is not None:
        branch = await branch_for_company(session, branch_id, company_id)
    return await settings_for(session, company_id, tenant_id, branch)


@router.get("/employees/{employee_id}/compensation", response_model=list[CompensationRead])
async def get_employee_compensation(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list:
    employee = await _employee(session, employee_id, tenant_id)
    return await list_compensation(session, employee)


@router.post("/employees/{employee_id}/compensation", response_model=CompensationRead, status_code=201)
async def post_employee_compensation(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: CompensationCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> EmployeeCompensation:
    employee = await _employee(session, employee_id, tenant_id)
    return await add_compensation(session, employee, payload)


@router.patch("/employees/{employee_id}/compensation/{compensation_id}", response_model=CompensationRead)
async def patch_employee_compensation(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    compensation_id: uuid.UUID,
    payload: CompensationUpdate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> EmployeeCompensation:
    employee = await _employee(session, employee_id, tenant_id)
    return await update_compensation(session, employee, compensation_id, payload)


@router.get("/deduction-types", response_model=list[DeductionTypeRead])
async def get_deduction_types(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list:
    return await list_types(session, company_id, tenant_id)


@router.post("/deduction-types", response_model=DeductionTypeRead, status_code=201)
async def post_deduction_type(
    tenant_id: uuid.UUID,
    payload: DeductionTypeCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> object:
    return await create_type(session, tenant_id, payload)


@router.patch("/deduction-types/{type_id}", response_model=DeductionTypeRead)
async def patch_deduction_type(
    tenant_id: uuid.UUID,
    type_id: uuid.UUID,
    payload: DeductionTypeWrite,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> object:
    row = await type_for_tenant(session, type_id, tenant_id)
    return await update_type(session, row, payload)


@router.delete("/deduction-types/{type_id}", status_code=204)
async def remove_deduction_type(
    tenant_id: uuid.UUID,
    type_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    row = await type_for_tenant(session, type_id, tenant_id)
    await delete_type(session, row)


@router.get("/deduction-types/{type_id}/enrol", response_model=list[DeductionEnrolCandidate])
async def get_deduction_enrol_candidates(
    tenant_id: uuid.UUID,
    type_id: uuid.UUID,
    branch_id: uuid.UUID | None = Query(default=None),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[dict]:
    row = await type_for_tenant(session, type_id, tenant_id)
    return await enrol_candidates(session, row, branch_id)


@router.post("/deduction-types/{type_id}/enrol", response_model=DeductionEnrolResult)
async def post_deduction_enrol(
    tenant_id: uuid.UUID,
    type_id: uuid.UUID,
    payload: DeductionEnrol,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> dict:
    row = await type_for_tenant(session, type_id, tenant_id)
    return await enrol_employees(session, row, payload)


@router.get("/employees/{employee_id}/deductions", response_model=list[EmployeeDeductionRead])
async def get_employee_deductions(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[dict]:
    employee = await _employee(session, employee_id, tenant_id)
    return await list_employee_deductions(session, employee)


@router.post("/employees/{employee_id}/deductions", response_model=EmployeeDeductionRead, status_code=201)
async def post_employee_deduction(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: EmployeeDeductionWrite,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> dict:
    employee = await _employee(session, employee_id, tenant_id)
    return await add_employee_deduction(session, employee, payload)


@router.patch("/employees/{employee_id}/deductions/{deduction_id}", response_model=EmployeeDeductionRead)
async def patch_employee_deduction(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    deduction_id: uuid.UUID,
    payload: EmployeeDeductionWrite,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> dict:
    employee = await _employee(session, employee_id, tenant_id)
    return await update_employee_deduction(session, employee, deduction_id, payload)


@router.delete("/employees/{employee_id}/deductions/{deduction_id}", status_code=204)
async def remove_employee_deduction(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    deduction_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    employee = await _employee(session, employee_id, tenant_id)
    await delete_employee_deduction(session, employee, deduction_id)


@router.get("/benefit-types", response_model=list[BenefitTypeRead])
async def get_benefit_types(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list:
    return await list_benefit_types(session, company_id, tenant_id)


@router.post("/benefit-types", response_model=BenefitTypeRead, status_code=201)
async def post_benefit_type(
    tenant_id: uuid.UUID,
    payload: BenefitTypeCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> object:
    return await create_benefit_type(session, tenant_id, payload)


@router.patch("/benefit-types/{type_id}", response_model=BenefitTypeRead)
async def patch_benefit_type(
    tenant_id: uuid.UUID,
    type_id: uuid.UUID,
    payload: BenefitTypeWrite,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> object:
    row = await benefit_type_for_tenant(session, type_id, tenant_id)
    return await update_benefit_type(session, row, payload)


@router.delete("/benefit-types/{type_id}", status_code=204)
async def remove_benefit_type(
    tenant_id: uuid.UUID,
    type_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    row = await benefit_type_for_tenant(session, type_id, tenant_id)
    await delete_benefit_type(session, row)


@router.get("/employees/{employee_id}/benefits", response_model=list[EmployeeBenefitRead])
async def get_employee_benefits(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> list[dict]:
    employee = await _employee(session, employee_id, tenant_id)
    return await list_benefits(session, employee)


@router.post("/employees/{employee_id}/benefits", response_model=EmployeeBenefitRead, status_code=201)
async def post_employee_benefit(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: EmployeeBenefitWrite,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> dict:
    employee = await _employee(session, employee_id, tenant_id)
    return await add_benefit(session, employee, payload)


@router.patch("/employees/{employee_id}/benefits/{benefit_id}", response_model=EmployeeBenefitRead)
async def patch_employee_benefit(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    benefit_id: uuid.UUID,
    payload: EmployeeBenefitWrite,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> dict:
    employee = await _employee(session, employee_id, tenant_id)
    return await update_benefit(session, employee, benefit_id, payload)


@router.delete("/employees/{employee_id}/benefits/{benefit_id}", status_code=204)
async def remove_employee_benefit(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    benefit_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> None:
    employee = await _employee(session, employee_id, tenant_id)
    await delete_benefit(session, employee, benefit_id)


@router.get("/payroll/runs", response_model=list[PayrollRunRead])
async def list_payroll_runs(
    tenant_id: uuid.UUID,
    company_id: uuid.UUID = Query(),
    branch_id: uuid.UUID = Query(),
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
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


@router.post("/payroll/runs", response_model=PayrollRunRead, status_code=201)
async def post_payroll_run(
    tenant_id: uuid.UUID,
    payload: PayrollRunCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> dict:
    await company_for_tenant(session, payload.company_id, tenant_id)
    run, skipped = await create_run(
        session, payload.company_id, tenant_id, payload.branch_id, payload.period_start, payload.period_end
    )
    loaded = await load_run(session, run.id)
    assert loaded is not None
    return await run_to_read(session, loaded, skipped)


@router.get("/payroll/runs/{run_id}", response_model=PayrollRunRead)
async def get_payroll_run(
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> dict:
    run = await load_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    await company_for_tenant(session, run.company_id, tenant_id)
    return await run_to_read(session, run)


@router.post("/payroll/runs/{run_id}/approve", response_model=PayrollRunRead)
async def approve_payroll_run(
    tenant_id: uuid.UUID,
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> dict:
    run = await load_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    await company_for_tenant(session, run.company_id, tenant_id)
    approved = await approve_run(session, run)
    return await run_to_read(session, approved)


@router.post("/employees/{employee_id}/login", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_employee_login(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: EmployeeLoginCreate,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> User:
    employee = await _employee(session, employee_id, tenant_id)
    if employee.login_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This employee already has a login")
    login = User(
        tenant_id=tenant_id,
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        full_name=(payload.full_name or f"{employee.first_name} {employee.last_name}").strip(),
        role="EMPLOYEE",
        status="ACTIVE",
        employee_id=employee.id,
    )
    session.add(login)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        ) from exc
    await session.refresh(login)
    return login


@router.post("/employees/{employee_id}/clock-device/reset", response_model=EmployeeRead)
async def reset_clock_device(
    tenant_id: uuid.UUID,
    employee_id: uuid.UUID,
    session: AsyncSession = Depends(get_platform_db),
    _: object = Depends(get_current_admin),
) -> Employee:
    employee = await _employee(session, employee_id, tenant_id)
    employee.clock_device_id = None
    await session.flush()
    return await session.get(
        Employee,
        employee.id,
        options=(selectinload(Employee.login_user),),
        populate_existing=True,
    )
