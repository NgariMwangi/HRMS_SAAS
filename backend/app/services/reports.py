"""Read-only company reports, explicit selection semantics and exact currency totals."""
import csv
import io
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from app.api.org import branch_for_company, company_for_tenant, optional_department_for_company
from app.models import AttendanceRecord, Branch, Currency, Department, Employee, EmployeeLifecycleEvent, JobTitle, LeaveRequest, LeaveType
from app.models.payroll import PayrollPayslip, PayrollRun

CATALOG = {
    "headcount": {"title": "Headcount", "description": "Current employee records by branch, department and employment status.", "permissions": ["people.view_all", "people.manage"]},
    "payroll": {"title": "Payroll", "description": "Saved payroll results, with separate totals for each currency.", "permissions": ["payroll.manage"]},
    "attendance": {"title": "Attendance", "description": "Recorded attendance, late and absent entries, and completed clock hours.", "permissions": ["attendance.manage"]},
    "leave": {"title": "Leave", "description": "Leave requests, approval status and requested days by leave type.", "permissions": ["leave.view_all", "leave.manage"]},
    "movement": {"title": "Employee movement", "description": "Hires, exits, transfers and other recorded employment changes.", "permissions": ["lifecycle.view_all", "lifecycle.manage"]},
}
MAX_ROWS = 50000


def fail(message, code=400):
    raise HTTPException(code, message)


def allowed(permissions):
    if "reports.view" not in permissions:
        return []
    return [dict(key=key, title=value["title"], description=value["description"]) for key, value in CATALOG.items() if set(value["permissions"]) & set(permissions)]


def column(key, label, kind="text"):
    return dict(key=key, label=label, kind=kind)


def metric(label, value):
    return dict(label=label, value=str(value) if isinstance(value, Decimal) else value)


def name(employee):
    return " ".join(p for p in [employee.first_name, employee.other_names, employee.last_name] if p)


def decimal(value):
    return str(Decimal(value or 0).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def instant(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat() if value.tzinfo is None else value.astimezone(timezone.utc).isoformat()


def counts(title, rows, key):
    values = Counter(r[key] or "Not assigned" for r in rows)
    return dict(title=title, columns=[column("label", title), column("count", "Records", "number")], rows=[dict(label=k, count=v) for k, v in sorted(values.items(), key=lambda item: (-item[1], item[0]))])


def status_filter(query, field, status, accepted):
    if status and status != "ALL":
        if status not in accepted:
            fail("Invalid status for this report")
        query = query.where(field == status)
    return query


async def generate(session, tenant_id, company_id, kind, start_on, end_on, branch_id=None, department_id=None, status=None, q=None):
    if kind not in CATALOG:
        fail("Report not found", 404)
    company = await company_for_tenant(session, company_id, tenant_id)
    if branch_id:
        await branch_for_company(session, branch_id, company_id)
    await optional_department_for_company(session, department_id, company_id)
    if start_on > end_on:
        fail("Start date must be on or before end date")
    if kind != "headcount" and (end_on - start_on).days > 730:
        fail("Choose a report period of two years or less")
    branches = {b.id: b for b in (await session.scalars(select(Branch).where(Branch.company_id == company_id))).all()}
    departments = {d.id: d.name for d in (await session.scalars(select(Department).where(Department.company_id == company_id))).all()}
    titles = {j.id: j.name for j in (await session.scalars(select(JobTitle).where(JobTitle.company_id == company_id))).all()}
    currencies = {c.id: c.code for c in (await session.scalars(select(Currency))).all()}
    branch_name = lambda identity: branches[identity].name if identity in branches else "Not assigned"
    department_name = lambda identity: departments.get(identity, "Not assigned")
    scoped_people = [Employee.company_id == company_id]
    if department_id:
        scoped_people.append(Employee.department_id == department_id)
    if q and q.strip():
        # Treat search as literal text, not SQL wildcard patterns.
        term = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        scoped_people.append(or_(func.concat_ws(" ", Employee.first_name, Employee.other_names, Employee.last_name).ilike(term, escape="\\"), Employee.employee_number.ilike(term, escape="\\")))
    rows = []
    breakdowns = []
    summaries = []
    note = ""
    statuses = []
    columns = []
    selected_status = status

    if kind == "headcount":
        query = select(Employee).where(*scoped_people).order_by(Employee.last_name, Employee.first_name, Employee.id)
        if branch_id:
            query = query.where(Employee.branch_id == branch_id)
        statuses = ["ACTIVE", "SUSPENDED", "TERMINATED"]
        query = status_filter(query, Employee.status, status, statuses)
        employees = list((await session.scalars(query.limit(MAX_ROWS + 1))).all())
        for e in employees:
            rows.append(dict(id=str(e.id), employee_id=str(e.id), employee_number=e.employee_number, employee=name(e), branch=branch_name(e.branch_id), department=department_name(e.department_id), job_title=titles.get(e.job_title_id, "Not assigned"), employment_type=e.employment_type, status=e.status, joined_on=e.date_joined, ended_on=e.date_ended))
        columns = [column("employee_number", "Employee no."), column("employee", "Employee"), column("branch", "Branch"), column("department", "Department"), column("job_title", "Job title"), column("employment_type", "Employment type", "status"), column("status", "Status", "status"), column("joined_on", "Start date", "date"), column("ended_on", "End date", "date")]
        summaries = [metric("Employee records", len(rows)), *[metric(s.title(), sum(r["status"] == s for r in rows)) for s in statuses]]
        breakdowns = [counts("Departments", rows, "department"), counts("Branches", rows, "branch"), counts("Employment types", rows, "employment_type")]
        note = "Current employee records and stored employment statuses. Date ranges do not change this snapshot; use Employee movement for historical changes."

    elif kind == "payroll":
        query = select(PayrollPayslip, PayrollRun, Employee).join(PayrollRun, PayrollPayslip.run_id == PayrollRun.id).join(Employee, PayrollPayslip.employee_id == Employee.id).where(PayrollPayslip.company_id == company_id, PayrollRun.company_id == company_id, *scoped_people, PayrollRun.period_end.between(start_on, end_on)).order_by(PayrollRun.period_end.desc(), PayrollPayslip.employee_name, PayrollPayslip.id)
        if branch_id:
            query = query.where(PayrollRun.branch_id == branch_id)
        statuses = ["APPROVED", "DRAFT"]
        selected_status = status or "APPROVED"
        query = status_filter(query, PayrollRun.status, selected_status, statuses)
        totals = defaultdict(lambda: dict(gross=Decimal("0"), deductions=Decimal("0"), employer=Decimal("0"), net=Decimal("0"), payslips=0))
        run_ids = set()
        for p, run, e in (await session.execute(query.limit(MAX_ROWS + 1))).all():
            currency = currencies.get(run.currency_id, "Unknown")
            run_ids.add(run.id)
            rows.append(dict(id=str(p.id), employee_id=str(e.id), run_id=str(run.id), employee_number=p.employee_number, employee=p.employee_name, branch=branch_name(run.branch_id), department=department_name(e.department_id), period_start=run.period_start, period_end=run.period_end, status=run.status, currency=currency, gross=decimal(p.gross), deductions=decimal(p.employee_deductions), employer=decimal(p.employer_contributions), net=decimal(p.net)))
            t = totals[currency]
            t["payslips"] += 1
            for key, value in [("gross", p.gross), ("deductions", p.employee_deductions), ("employer", p.employer_contributions), ("net", p.net)]:
                t[key] += value
        columns = [column("employee_number", "Employee no."), column("employee", "Employee"), column("branch", "Payroll branch"), column("period_start", "Period start", "date"), column("period_end", "Period end", "date"), column("status", "Status", "status"), column("currency", "Currency"), column("gross", "Gross", "decimal"), column("deductions", "Deductions", "decimal"), column("employer", "Employer contributions", "decimal"), column("net", "Net pay", "decimal")]
        summaries = [metric("Payroll runs", len(run_ids)), metric("Payslips", len(rows)), metric("Employees included", len({r["employee_id"] for r in rows})), metric("Currencies", len(totals))]
        breakdowns = [dict(title="Totals by currency", columns=[column("currency", "Currency"), column("payslips", "Payslips", "number"), *[column(k, label, "decimal") for k, label in [("gross", "Gross"), ("deductions", "Deductions"), ("employer", "Employer contributions"), ("net", "Net pay")]]], rows=[dict(currency=c, **{k: decimal(v) if isinstance(v, Decimal) else v for k, v in t.items()}) for c, t in sorted(totals.items())])]
        note = "Includes full saved payslips for payroll periods ending within the selected dates. Approved runs are shown by default. Currencies are never added together. Department filtering uses the employee's current department."

    elif kind == "attendance":
        query = select(AttendanceRecord, Employee).join(Employee, AttendanceRecord.employee_id == Employee.id).where(AttendanceRecord.company_id == company_id, *scoped_people, AttendanceRecord.work_on.between(start_on, end_on)).order_by(AttendanceRecord.work_on.desc(), Employee.last_name, AttendanceRecord.id)
        if branch_id:
            query = query.where(AttendanceRecord.branch_id == branch_id)
        statuses = ["PRESENT", "LATE", "ABSENT", "ON_LEAVE"]
        query = status_filter(query, AttendanceRecord.status, status, statuses)
        for a, e in (await session.execute(query.limit(MAX_ROWS + 1))).all():
            seconds = max(0, (a.checked_out_at - a.checked_in_at).total_seconds()) if a.checked_in_at and a.checked_out_at else None
            hours = decimal(Decimal(str(seconds)) / 3600) if seconds is not None else None
            rows.append(dict(id=str(a.id), employee_id=str(e.id), employee_number=e.employee_number, employee=name(e), branch=branch_name(a.branch_id), department=department_name(e.department_id), work_on=a.work_on, status=a.status, source=a.source, checked_in_at=instant(a.checked_in_at), checked_out_at=instant(a.checked_out_at), hours=hours))
        columns = [column("work_on", "Work date", "date"), column("employee_number", "Employee no."), column("employee", "Employee"), column("branch", "Recorded branch"), column("department", "Department"), column("status", "Status", "status"), column("source", "Source"), column("checked_in_at", "Clock in", "datetime"), column("checked_out_at", "Clock out", "datetime"), column("hours", "Clock hours", "decimal")]
        summaries = [metric("Recorded employee-days", len(rows)), metric("Present or late", sum(r["status"] in {"PRESENT", "LATE"} for r in rows)), metric("Absent entries", sum(r["status"] == "ABSENT" for r in rows)), metric("Completed clock hours", sum((Decimal(r["hours"]) for r in rows if r["hours"] is not None), Decimal("0")))]
        breakdowns = [counts("Attendance statuses", rows, "status"), counts("Branches", rows, "branch")]
        note = "Shows recorded attendance only. Missing entries are not counted as absences, and approved leave is reported under Leave. Clock hours require both clock-in and clock-out; department uses the current employee record."

    elif kind == "leave":
        query = select(LeaveRequest, Employee, LeaveType).join(Employee, LeaveRequest.employee_id == Employee.id).join(LeaveType, LeaveRequest.leave_type_id == LeaveType.id).where(LeaveRequest.company_id == company_id, LeaveType.company_id == company_id, *scoped_people, LeaveRequest.start_on <= end_on, LeaveRequest.end_on >= start_on).order_by(LeaveRequest.start_on.desc(), Employee.last_name, LeaveRequest.id)
        if branch_id:
            query = query.where(Employee.branch_id == branch_id)
        statuses = ["PENDING_SUPERVISOR", "PENDING_HR", "APPROVED", "REJECTED", "CANCELLED"]
        query = status_filter(query, LeaveRequest.status, status, statuses)
        for request, e, leave_type in (await session.execute(query.limit(MAX_ROWS + 1))).all():
            rows.append(dict(id=str(request.id), employee_id=str(e.id), employee_number=e.employee_number, employee=name(e), branch=branch_name(e.branch_id), department=department_name(e.department_id), leave_type=leave_type.name, start_on=request.start_on, end_on=request.end_on, days=decimal(request.days), status=request.status))
        columns = [column("employee_number", "Employee no."), column("employee", "Employee"), column("branch", "Current branch"), column("department", "Department"), column("leave_type", "Leave type"), column("start_on", "From", "date"), column("end_on", "To", "date"), column("days", "Request days", "decimal"), column("status", "Status", "status")]
        pending = {"PENDING_SUPERVISOR", "PENDING_HR"}
        summaries = [metric("Leave requests", len(rows)), metric("Approved request days", sum((Decimal(r["days"]) for r in rows if r["status"] == "APPROVED"), Decimal("0"))), metric("Pending requests", sum(r["status"] in pending for r in rows)), metric("Employees requesting leave", len({r["employee_id"] for r in rows}))]
        grouped = defaultdict(lambda: dict(requests=0, approved_days=Decimal("0"), pending_days=Decimal("0")))
        for r in rows:
            t = grouped[r["leave_type"]]; t["requests"] += 1
            if r["status"] == "APPROVED": t["approved_days"] += Decimal(r["days"])
            if r["status"] in pending: t["pending_days"] += Decimal(r["days"])
        breakdowns = [dict(title="Leave types", columns=[column("type", "Leave type"), column("requests", "Requests", "number"), column("approved_days", "Approved request days", "decimal"), column("pending_days", "Pending request days", "decimal")], rows=[dict(type=k, **{field: decimal(v) if isinstance(v, Decimal) else v for field, v in value.items()}) for k, value in sorted(grouped.items())]), counts("Approval statuses", rows, "status")]
        note = "Includes requests overlapping the selected dates. Days are the full stored request totals, not prorated to the date range. Branch and department use the current employee record."

    elif kind == "movement":
        # Membership matches either side of a recorded change, with current assignment as fallback for legacy events.
        people = [Employee.company_id == company_id]
        if q and q.strip(): people.append(scoped_people[-1])
        query = select(EmployeeLifecycleEvent, Employee).join(Employee, EmployeeLifecycleEvent.employee_id == Employee.id).where(EmployeeLifecycleEvent.company_id == company_id, *people, EmployeeLifecycleEvent.effective_on.between(start_on, end_on)).order_by(EmployeeLifecycleEvent.effective_on.desc(), Employee.last_name, EmployeeLifecycleEvent.id)
        for identity, before, after, current in [(branch_id, EmployeeLifecycleEvent.from_branch_id, EmployeeLifecycleEvent.to_branch_id, Employee.branch_id), (department_id, EmployeeLifecycleEvent.from_department_id, EmployeeLifecycleEvent.to_department_id, Employee.department_id)]:
            if identity: query = query.where(or_(before == identity, after == identity, before.is_(None) & after.is_(None) & (current == identity)))
        statuses = ["HIRED", "REHIRED", "SUSPENDED", "REINSTATED", "TERMINATED", "ROLE_CHANGED", "EXTENDED"]
        query = status_filter(query, EmployeeLifecycleEvent.event_type, status, statuses)
        for event, e in (await session.execute(query.limit(MAX_ROWS + 1))).all():
            rows.append(dict(id=str(event.id), employee_id=str(e.id), employee_number=e.employee_number, employee=name(e), effective_on=event.effective_on, event_type=event.event_type, from_branch=branch_name(event.from_branch_id) if event.from_branch_id else "", to_branch=branch_name(event.to_branch_id) if event.to_branch_id else "", from_department=department_name(event.from_department_id) if event.from_department_id else "", to_department=department_name(event.to_department_id) if event.to_department_id else "", from_job_title=titles.get(event.from_job_title_id, ""), to_job_title=titles.get(event.to_job_title_id, ""), reason=event.reason or ""))
        columns = [column("effective_on", "Effective date", "date"), column("employee_number", "Employee no."), column("employee", "Employee"), column("event_type", "Change", "status"), column("from_branch", "From branch"), column("to_branch", "To branch"), column("from_department", "From department"), column("to_department", "To department"), column("from_job_title", "From job title"), column("to_job_title", "To job title"), column("reason", "Reason")]
        summaries = [metric("Recorded changes", len(rows)), metric("Hires and rehires", sum(r["event_type"] in {"HIRED", "REHIRED"} for r in rows)), metric("Exits", sum(r["event_type"] == "TERMINATED" for r in rows)), metric("Employees with changes", len({r["employee_id"] for r in rows}))]
        breakdowns = [counts("Change types", rows, "event_type")]
        note = "Shows lifecycle events by effective date. Branch and department filters match either side of the recorded change; older events without those fields use the current employee assignment. Private event notes and attachments are excluded."

    if len(rows) > MAX_ROWS:
        fail("This selection has more than 50,000 records. Narrow the dates, branch, department or search.", 422)
    return dict(key=kind, title=CATALOG[kind]["title"], company=company.name, branch=branch_name(branch_id) if branch_id else "All branches", department=department_name(department_id) if department_id else "All departments", start_on=start_on, end_on=end_on, generated_at=datetime.now(timezone.utc).isoformat(), note=note, selected_status=selected_status or "ALL", statuses=statuses, summary=summaries, breakdowns=breakdowns, columns=columns, rows=rows, total_rows=len(rows))


def csv_bytes(report):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow([c["label"] for c in report["columns"]])
    for row in report["rows"]:
        values = []
        for c in report["columns"]:
            value = row.get(c["key"])
            text = "" if value is None else str(value)
            # Keep human-entered names and reasons from becoming spreadsheet formulas.
            if c["kind"] in {"text", "status"} and text.lstrip().startswith(("=", "+", "-", "@")):
                text = "'" + text
            values.append(text)
        writer.writerow(values)
    return ("\ufeff" + stream.getvalue()).encode("utf-8")
