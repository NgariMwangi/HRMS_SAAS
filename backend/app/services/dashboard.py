"""Permission-filtered dashboard summaries. Never return salary or bank account details."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models import (Branch, Company, Country, Currency, Employee, EmployeeSupervisor,
                        EmployeeLifecycleEvent, LeaveRequest, LeaveDecision, LeaveType,
                        EmployeeCompensation, PayrollRun, PayrollPayslip)
from app.models.legacy_import import LegacyImportRecord
from app.models.workforce_payments import OvertimeRequest
from app.api.access_control import employee_scope
from app.api.leave import closed_working_dates
from app.services.access import permissions_for
from app.services.employee_alerts import employee_alerts


async def dashboard_summary(session, user, company_id, month):
    if company_id is None and user.role != "OWNER":
        raise HTTPException(403, "Only the workspace owner can view all companies")
    today = datetime.now(ZoneInfo("Africa/Nairobi")).date()
    try:
        period = date.fromisoformat(f"{month}-01") if month else today.replace(day=1)
    except ValueError:
        raise HTTPException(422, "Select a valid payroll month (YYYY-MM)")
    permissions = await permissions_for(session, user)
    people_allowed = bool({"people.manage", "people.view_all"} & permissions)
    leave_allowed = bool({"leave.manage", "leave.view_all", "leave.view_team"} & permissions)
    payroll_allowed = "payroll.manage" in permissions
    stmt = select(Company).where(Company.tenant_id == user.tenant_id)
    if company_id:
        stmt = stmt.where(Company.id == company_id)
    companies = (await session.scalars(stmt)).all()
    ids = [row.id for row in companies]
    if company_id and not ids:
        raise HTTPException(403, "Company does not belong to this workspace")
    branches = (await session.scalars(select(Branch).where(Branch.company_id.in_(ids)))).all()
    branch_map = {row.id: row for row in branches}
    company_names = {row.id: row.name for row in companies}
    employees = (await session.scalars(select(Employee).where(
        Employee.company_id.in_(ids), Employee.status.in_(("ACTIVE", "SUSPENDED")),
        await employee_scope(session, user)
    ))).all() if people_allowed else []
    active = [row for row in employees if row.status == "ACTIVE"]

    def person(employee):
        return {"employee_id": str(employee.id), "name": " ".join(filter(None, [employee.first_name, employee.other_names, employee.last_name])),
                "company_id": str(employee.company_id), "company": company_names.get(employee.company_id, ""),
                "branch": branch_map[employee.branch_id].name if employee.branch_id in branch_map else ""}

    activity = []
    def recent(at, title, company, href):
        activity.append({"at": at, "title": title, "company_id": str(company), "company": company_names.get(company, ""), "href": href})

    alerts, contracts, missing = None, None, None
    if people_allowed:
        legacy = (await session.scalars(select(LegacyImportRecord).where(
            LegacyImportRecord.tenant_id == user.tenant_id, LegacyImportRecord.company_id.in_(ids),
            LegacyImportRecord.source_table == "employees"
        ))).all()
        ends = {identity: date.fromisoformat(row.payload["probation_end_date"])
                for row in legacy if row.payload.get("probation_end_date") for identity in row.destination_ids}
        alerts = employee_alerts(active, today, ends)
        identity_map = {str(row.id): person(row) for row in active}
        for key in ("birthdays", "probation"):
            alerts[key] = [{**row, **identity_map[row["employee_id"]]} for row in alerts[key]]
        contracts = [{**person(row), "date": row.date_ended, "days": (row.date_ended - today).days}
                     for row in active if row.employment_type == "CONTRACT" and row.date_ended and (row.date_ended - today).days <= 60]
        contracts.sort(key=lambda row: (row["days"], row["name"]))
        countries = {row.id: row.code for row in (await session.scalars(select(Country))).all()}
        salaries = {}
        if payroll_allowed:
            for row in (await session.scalars(select(EmployeeCompensation).options(selectinload(EmployeeCompensation.lines)).where(
                EmployeeCompensation.company_id.in_(ids), EmployeeCompensation.is_historical.is_(False),
                EmployeeCompensation.effective_from <= today
            ).order_by(EmployeeCompensation.effective_from))).all():
                salaries[row.employee_id] = row.computed_gross
        missing = []
        for row in active:
            reasons = []
            if not (row.email or "").strip():
                reasons.append("Work email")
            branch = branch_map.get(row.branch_id)
            if branch and countries.get(branch.country_id) == "KE":
                reasons += [label for field, label in [("pin_number", "PIN number"), ("shif_no", "SHIF number"), ("nssf_no", "NSSF number")]
                            if not (getattr(row, field) or "").strip()]
            if payroll_allowed:
                if salaries.get(row.id, Decimal(0)) <= 0:
                    reasons.append("Current salary")
                if not (row.bank_name or "").strip() or not (row.bank_account_number or "").strip():
                    reasons.append("Bank details")
            if reasons:
                missing.append({**person(row), "missing": reasons})
        events = (await session.execute(select(EmployeeLifecycleEvent, Employee).join(Employee, Employee.id == EmployeeLifecycleEvent.employee_id).where(
            EmployeeLifecycleEvent.company_id.in_(ids), await employee_scope(session, user)
        ).order_by(EmployeeLifecycleEvent.created_at.desc()).limit(15))).all()
        for event, employee in events:
            recent(event.created_at, f"{event.event_type.replace('_', ' ').title()}: {person(employee)['name']}", event.company_id, f"/app/people/{employee.id}")
        changes = (await session.scalars(select(Employee).where(
            Employee.company_id.in_(ids), await employee_scope(session, user),
            Employee.updated_at > Employee.created_at
        ).order_by(Employee.updated_at.desc()).limit(10))).all()
        for employee in changes:
            recent(employee.updated_at, f"Employee record updated: {person(employee)['name']}", employee.company_id, f"/app/people/{employee.id}")

    pending_leave = None
    on_leave = None
    if leave_allowed:
        leave_filter = await employee_scope(session, user, "leave")
        leave_rows = (await session.execute(select(LeaveRequest, Employee, LeaveType).join(Employee, Employee.id == LeaveRequest.employee_id)
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id).where(LeaveRequest.company_id.in_(ids), leave_filter,
                LeaveRequest.status == "APPROVED", LeaveRequest.start_on <= today, LeaveRequest.end_on >= today,
                Employee.status == "ACTIVE").order_by(Employee.last_name))).all()
        on_leave = []
        for request, employee, leave_type in leave_rows:
            closed = await closed_working_dates(session, employee, today, request.end_on + timedelta(days=60))
            if leave_type.day_basis != "CALENDAR" and (today.weekday() >= 5 or today in closed):
                continue
            partial = request.days < 1 and request.start_on == request.end_on
            back = request.end_on + timedelta(days=1)
            while back.weekday() >= 5 or back in closed:
                back += timedelta(days=1)
            on_leave.append({**person(employee), "leave_type": leave_type.name, "end_on": request.end_on,
                "return_on": None if partial else back, "portion": str(request.days) if partial else None})
        pending_stmt = select(func.count()).select_from(LeaveRequest).join(Employee, Employee.id == LeaveRequest.employee_id).where(
            LeaveRequest.company_id.in_(ids), leave_filter)
        if "leave.manage" in permissions:
            pending_leave = await session.scalar(pending_stmt.where(LeaveRequest.status.in_(("PENDING_HR", "PENDING_SUPERVISOR"))))
        elif "leave.view_team" in permissions and user.employee_id:
            pending_leave = await session.scalar(pending_stmt.where(LeaveRequest.status == "PENDING_SUPERVISOR",
                LeaveRequest.employee_id != user.employee_id, LeaveRequest.employee_id.in_(select(EmployeeSupervisor.employee_id).where(EmployeeSupervisor.supervisor_id == user.employee_id))))
        decisions = (await session.execute(select(LeaveDecision, Employee).join(LeaveRequest, LeaveRequest.id == LeaveDecision.leave_request_id)
            .join(Employee, Employee.id == LeaveRequest.employee_id).where(LeaveDecision.company_id.in_(ids), leave_filter)
            .order_by(LeaveDecision.created_at.desc()).limit(15))).all()
        for decision, employee in decisions:
            recent(decision.created_at, f"Leave {decision.decision.lower()}: {person(employee)['name']}", decision.company_id, "/app/leave")

    payroll, pending_payroll, pending_overtime = None, None, None
    if payroll_allowed:
        if not month:
            latest_period = await session.scalar(select(func.max(PayrollRun.period_start)).where(PayrollRun.company_id.in_(ids)))
            if latest_period:
                period = latest_period.replace(day=1)
        following = (period.replace(day=28) + timedelta(days=4)).replace(day=1)
        pending_payroll = await session.scalar(select(func.count()).select_from(PayrollRun).where(PayrollRun.company_id.in_(ids), PayrollRun.status == "DRAFT"))
        pending_overtime = await session.scalar(select(func.count()).select_from(OvertimeRequest).where(OvertimeRequest.company_id.in_(ids), OvertimeRequest.status == "PENDING"))
        runs = (await session.execute(select(PayrollRun, Currency.code).join(Currency, Currency.id == PayrollRun.currency_id).where(
            PayrollRun.company_id.in_(ids), PayrollRun.period_start >= period, PayrollRun.period_start < following).order_by(PayrollRun.period_start.desc()))).all()
        count_map = dict((await session.execute(select(PayrollPayslip.run_id, func.count()).where(PayrollPayslip.run_id.in_([r.id for r, _ in runs])).group_by(PayrollPayslip.run_id))).all())
        payroll = [{"id": str(run.id), "company_id": str(run.company_id), "branch_id": str(run.branch_id), "company": company_names.get(run.company_id, ""),
                    "branch": branch_map[run.branch_id].name if run.branch_id in branch_map else "", "currency": currency,
                    "status": run.status, "employees": count_map.get(run.id, 0), "gross": str(run.gross_total),
                    "deductions": str(run.deduction_total), "net": str(run.net_total)} for run, currency in runs]
        latest_runs = (await session.scalars(select(PayrollRun).where(PayrollRun.company_id.in_(ids), PayrollRun.status == "APPROVED")
            .order_by(PayrollRun.updated_at.desc()).limit(15))).all()
        for run in latest_runs:
            recent(run.updated_at, f"Payroll approved: {branch_map[run.branch_id].name if run.branch_id in branch_map else ''} ({run.period_start:%b %Y})", run.company_id, "/app/payroll")
    activity.sort(key=lambda row: row["at"].replace(tzinfo=timezone.utc) if row["at"].tzinfo is None else row["at"], reverse=True)
    return {"as_of": today, "month": period.strftime("%Y-%m"), "scope": "company" if company_id else "workspace",
            "companies": len(companies), "branches": len(branches), "employees": len(employees) if people_allowed else None,
            "pending": {"leave": pending_leave, "payroll": pending_payroll, "overtime": pending_overtime},
            "on_leave": on_leave, "alerts": alerts, "contracts": contracts, "missing": missing,
            "payroll": payroll, "activity": activity[:15]}
