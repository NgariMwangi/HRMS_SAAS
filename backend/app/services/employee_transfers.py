"""Move employment to another company without relabelling historical business records."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import delete, select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import undefer
from app.models import (Company, Employee, EmployeeNextOfKin, EmployeeSupervisor, LeaveRequest,
                        PayrollPayslip, PayrollRun, User)
from app.models.workforce_payments import OvertimeRequest
from app.api.org import branch_for_company, company_for_tenant, next_employee_number
from app.api.lifecycle import build_event


async def transfer_employee(session, employee_id, tenant_id, payload, actor_id=None):
    source = await session.get(Employee, employee_id)
    if source is None:
        raise HTTPException(404, "Employee not found")
    old_company = await company_for_tenant(session, source.company_id, tenant_id)
    destination = await company_for_tenant(session, payload.company_id, tenant_id)
    if destination.id == old_company.id:
        raise HTTPException(400, "Choose another company; use the branch selector for a branch change")
    if session.info.get("domain_company_id") is not None:
        raise HTTPException(403, "Use the shared workspace address to transfer between companies")
    # Use the same company lock order as payroll/employee-number allocation.
    await session.scalars(select(Company).where(Company.id.in_([old_company.id, destination.id])).order_by(Company.id).with_for_update().execution_options(populate_existing=True))
    if destination.status != "ACTIVE":
        raise HTTPException(400, "The destination company is inactive")
    employee = await session.scalar(select(Employee).options(undefer(Employee.photo_bytes)).where(Employee.id == employee_id).with_for_update().execution_options(populate_existing=True))
    if employee.company_id != old_company.id or employee.status not in {"ACTIVE", "SUSPENDED"}:
        raise HTTPException(409, "Only a current employee can be transferred; this record may already have been transferred")
    branch = await branch_for_company(session, payload.branch_id, destination.id)
    if branch.status != "ACTIVE":
        raise HTTPException(400, "Choose an active destination branch")
    today = datetime.now(ZoneInfo("Africa/Nairobi")).date()
    effective = payload.effective_on or today
    if effective > today or (employee.date_joined and effective < employee.date_joined):
        raise HTTPException(400, "Transfer date must be between the employee's start date and today")
    if employee.employment_type in {"INTERN", "PROBATION", "CONTRACT"} and employee.date_ended and employee.date_ended < effective:
        raise HTTPException(400, "Update the employment end date before transferring this employee")
    pending = await session.scalar(select(LeaveRequest.id).where(LeaveRequest.employee_id == employee.id,
        LeaveRequest.status.in_(("PENDING_HR", "PENDING_SUPERVISOR"))).limit(1))
    if pending:
        raise HTTPException(409, "Approve, decline, or cancel pending leave applications before transferring")
    future_leave = await session.scalar(select(LeaveRequest.id).where(LeaveRequest.employee_id == employee.id,
        LeaveRequest.status == "APPROVED", LeaveRequest.end_on >= effective).limit(1))
    if future_leave:
        raise HTTPException(409, "Approved leave overlaps the transfer date. Choose a transfer date after that leave ends")
    payroll = await session.scalar(select(PayrollRun.id).join(PayrollPayslip, PayrollPayslip.run_id == PayrollRun.id).where(
        PayrollPayslip.employee_id == employee.id, or_(PayrollRun.status == "DRAFT", PayrollRun.period_end >= effective)).limit(1))
    if payroll:
        raise HTTPException(409, "Complete draft payrolls first, and choose a transfer date after the last payroll period covering this employee")
    overtime = await session.scalar(select(OvertimeRequest.id).where(OvertimeRequest.employee_id == employee.id, OvertimeRequest.status == "PENDING").limit(1))
    if overtime:
        raise HTTPException(409, "Review pending overtime requests before transferring")
    fields = ["first_name", "other_names", "last_name", "date_of_birth", "id_number", "pin_number", "nssf_no", "shif_no",
              "email", "personal_email", "phone", "other_phone", "employment_type", "photo_bytes", "photo_content_type",
              "bank_name", "bank_branch", "bank_account_number", "bank_code", "swift_code", "prorate_payroll",
              "suspension_pay_treatment", "suspension_pay_deduction_percent"]
    new_employee = Employee(**{field: getattr(employee, field) for field in fields}, company_id=destination.id,
        branch_id=branch.id, employee_number=await next_employee_number(session, destination.id), department_id=None, job_title_id=None,
        date_joined=effective, date_ended=employee.date_ended, status=employee.status, previous_employee_id=employee.id)
    session.add(new_employee)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "The destination company already has a record with this employee's email or statutory identifiers") from exc
    # The same account/password now signs in to the new employment record.
    logins = (await session.scalars(select(User).where(User.employee_id == employee.id, User.tenant_id == tenant_id).with_for_update())).all()
    for login in logins:
        login.employee_id = new_employee.id
    contacts = (await session.scalars(select(EmployeeNextOfKin).where(EmployeeNextOfKin.employee_id == employee.id))).all()
    for contact in contacts:
        session.add(EmployeeNextOfKin(company_id=destination.id, employee_id=new_employee.id,
            **{field: getattr(contact, field) for field in ["name", "relationship", "phone", "other_phone", "email", "address", "sort_order"]}))
    employee.status = "TERMINATED"
    employee.date_ended = max(employee.date_joined or effective - timedelta(days=1), effective - timedelta(days=1))
    # Reporting duties do not follow a supervisor to a different company.
    await session.execute(delete(EmployeeSupervisor).where(EmployeeSupervisor.supervisor_id == employee.id))
    note = f"Company transfer: {old_company.name} to {destination.name}. Historical payroll and leave remain in the original company."
    if payload.note:
        note += f" {payload.note}"
    session.add(build_event(employee, "TRANSFERRED", reason="OUT", effective_on=effective, note=note,
        created_by=actor_id, related_employee_id=new_employee.id, from_branch_id=employee.branch_id))
    session.add(build_event(new_employee, "TRANSFERRED", reason="IN", effective_on=effective, note=note,
        created_by=actor_id, related_employee_id=employee.id, to_branch_id=new_employee.branch_id))
    await session.flush()
    return new_employee
