import csv
import io
import uuid
from datetime import date, datetime
from decimal import Decimal
import pytest
from app.db.session import get_session_maker
from app.models import AttendanceRecord, Employee, EmployeeLifecycleEvent, LeaveRequest
from tests.test_access import staff_login, workspace
from tests.test_leave_requests import _leave_type
from tests.test_platform import _admin_login
from tests.test_tenancy import _kenya, _uganda


async def create(client, headers, path, data):
    response = await client.post(path, headers=headers, json=data)
    assert response.status_code == 201, response.text
    return response.json()


async def person(client, headers, w, first, branch=None, department=None):
    return await create(client, headers, "/employees", dict(company_id=w["company"]["id"], branch_id=branch or w["branch"]["id"], department_id=department,
        first_name=first, last_name="Report", email=f"{uuid.uuid4().hex[:12]}@report.example", date_joined="2026-01-01"))


async def report(client, headers, company_id, kind, **params):
    response = await client.get(f"/reports/{kind}", headers=headers, params=dict(company_id=company_id, start_on="2026-03-01", end_on="2026-03-31", **params))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_headcount_filters_pagination_csv_and_empty_report(client):
    w, owner = await workspace(client)
    cid = w["company"]["id"]
    dept = await create(client, owner, "/departments", {"company_id":cid, "name":"Clinical"})
    a = await person(client, owner, w, "=Formula", department=dept["id"])
    b = await person(client, owner, w, "Brian")
    value = await report(client, owner, cid, "headcount", page_size=1)
    assert value["total_rows"] == 2 and len(value["rows"]) == 1
    assert value["summary"][0]["value"] == 2
    second = await report(client, owner, cid, "headcount", page_size=1, page=2)
    assert second["rows"][0]["id"] != value["rows"][0]["id"]
    selected = await report(client, owner, cid, "headcount", department_id=dept["id"])
    assert {r["employee_id"] for r in selected["rows"]} == {a["id"]}
    searched = await report(client, owner, cid, "headcount", q="Brian")
    assert {r["employee_id"] for r in searched["rows"]} == {b["id"]}
    assert (await report(client, owner, cid, "headcount", q="Brian Report"))["total_rows"] == 1
    assert (await report(client, owner, cid, "headcount", q="%"))["total_rows"] == 0
    assert (await report(client, owner, cid, "headcount", status="TERMINATED"))["rows"] == []
    exported = await client.get("/reports/headcount/export", headers=owner, params={"company_id":cid, "page_size":1})
    assert exported.status_code == 200 and "text/csv" in exported.headers["content-type"]
    csv_rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert len(csv_rows) == 2  # Export is not limited to the displayed page.
    assert any(row["Employee"].startswith("'=Formula") for row in csv_rows)
    assert "email" not in exported.text.lower() and "id_number" not in exported.text
    assert (await client.get("/reports/headcount", headers=owner, params={"company_id":cid,"status":"NOT_A_STATUS"})).status_code == 400
    assert (await client.get("/reports/unknown", headers=owner, params={"company_id":cid})).status_code == 404
    assert (await client.get("/reports/leave", headers=owner, params={"company_id":cid,"start_on":"2026-04-01","end_on":"2026-03-01"})).status_code == 400
    assert (await client.get("/reports/attendance", headers=owner, params={"company_id":cid,"start_on":"2020-01-01","end_on":"2026-03-01"})).status_code == 400
    assert (await client.get("/reports/headcount", headers=owner, params={"company_id":cid,"page_size":10000})).status_code == 422


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_reports_permission_boundaries_company_isolation_and_platform_access(client):
    w, owner = await workspace(client)
    foreign_w, foreign_owner = await workspace(client, "foreign-report-owner@example.com")
    cid = w["company"]["id"]
    _, identity, employee = await staff_login(client, owner, w, "Reader")
    _, _, manager = await staff_login(client, owner, w, "Lead", "MANAGER")
    _, _, hr = await staff_login(client, owner, w, "HR", "HR")
    for h in [employee, manager]:
        assert (await client.get("/reports/catalog", headers=h, params={"company_id":cid})).status_code == 403
        assert (await client.get("/reports/headcount/export", headers=h, params={"company_id":cid})).status_code == 403
    catalog = await client.get("/reports/catalog", headers=hr, params={"company_id":cid})
    assert catalog.status_code == 200 and len(catalog.json()["reports"]) == 5
    role = await create(client, owner, "/access/roles", {"name":"Headcount analyst", "permissions":["reports.view","people.view_all"]})
    assigned = await client.patch(f"/access/users/{identity['id']}", headers=owner, json={"role":role["key"]})
    assert assigned.status_code == 200
    limited = (await client.get("/reports/catalog", headers=employee, params={"company_id":cid})).json()
    assert [r["key"] for r in limited["reports"]] == ["headcount"]
    assert (await client.get("/reports/headcount", headers=employee, params={"company_id":cid})).status_code == 200
    for path in ["/reports/payroll", "/reports/payroll/export", "/reports/attendance", "/reports/movement"]:
        assert (await client.get(path, headers=employee, params={"company_id":cid})).status_code == 403
    for path in ["/reports/catalog", "/reports/headcount", "/reports/headcount/export"]:
        assert (await client.get(path, headers=owner, params={"company_id":foreign_w["company"]["id"]})).status_code == 403
    other_company = await create(client, owner, "/companies", {"name":"Second company"})
    other_dept = await create(client, owner, "/departments", {"company_id":other_company["id"],"name":"Other department"})
    assert (await client.get("/reports/headcount", headers=owner, params={"company_id":cid,"branch_id":foreign_w["branch"]["id"]})).status_code == 400
    assert (await client.get("/reports/headcount", headers=owner, params={"company_id":cid,"department_id":other_dept["id"]})).status_code == 400
    assert (await report(client, owner, other_company["id"], "headcount"))["total_rows"] == 0
    admin = await _admin_login(client)
    path = f"/platform/tenants/{w['tenant']['id']}/reports/headcount"
    assert (await client.get(path, headers=owner, params={"company_id":cid})).status_code == 403
    result = await client.get(path, headers=admin, params={"company_id":cid})
    assert result.status_code == 200 and result.json()["total_rows"] == 3
    assert (await client.get(path, headers=admin, params={"company_id":foreign_w["company"]["id"]})).status_code == 403
    export = await client.get(path + "/export", headers=admin, params={"company_id":cid})
    assert export.status_code == 200 and "text/csv" in export.headers["content-type"]
    revoked = await client.patch(f"/access/roles/{role['id']}", headers=owner, json={"name":role["name"], "permissions":["people.view_all"]})
    assert revoked.status_code == 200
    assert (await client.get("/reports/headcount", headers=employee, params={"company_id":cid})).status_code == 403


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_attendance_leave_and_movement_use_correct_dates_and_branch_history(client):
    w, owner = await workspace(client)
    cid, bid = w["company"]["id"], w["branch"]["id"]
    kenya = await _kenya()
    destination = await create(client, owner, "/branches", {"company_id":cid,"country_id":str(kenya.id),"name":"Destination","code":"DEST"})
    dept = await create(client, owner, "/departments", {"company_id":cid,"name":"Old department"})
    new_dept = await create(client, owner, "/departments", {"company_id":cid,"name":"New department"})
    p = await person(client, owner, w, "Amina", department=dept["id"])
    leave_type = await _leave_type(client, owner, cid)
    async with get_session_maker()() as session:
        employee = await session.get(Employee, uuid.UUID(p["id"]))
        employee.branch_id = uuid.UUID(destination["id"])
        employee.department_id = uuid.UUID(new_dept["id"])
        base = dict(company_id=uuid.UUID(cid), employee_id=employee.id)
        session.add_all([
            AttendanceRecord(**base, branch_id=uuid.UUID(bid), work_on=date(2026,3,1), status="PRESENT", source="SELF", checked_in_at=datetime(2026,3,1,6), checked_out_at=datetime(2026,3,1,14,30)),
            AttendanceRecord(**base, branch_id=uuid.UUID(bid), work_on=date(2026,3,2), status="LATE", source="SELF", checked_in_at=datetime(2026,3,2,7)),
            AttendanceRecord(**base, branch_id=uuid.UUID(bid), work_on=date(2026,3,3), status="ABSENT", source="HR"),
            AttendanceRecord(**base, branch_id=uuid.UUID(bid), work_on=date(2026,4,1), status="PRESENT", source="HR"),
            LeaveRequest(**base, leave_type_id=uuid.UUID(leave_type["id"]), start_on=date(2026,2,27), end_on=date(2026,3,2), days=Decimal("2"), requested_as="HR", approval_mode="HR_ONLY", status="APPROVED"),
            LeaveRequest(**base, leave_type_id=uuid.UUID(leave_type["id"]), start_on=date(2026,3,25), end_on=date(2026,3,26), days=Decimal("2"), requested_as="EMPLOYEE", approval_mode="HR_ONLY", status="PENDING_HR"),
            LeaveRequest(**base, leave_type_id=uuid.UUID(leave_type["id"]), start_on=date(2026,4,2), end_on=date(2026,4,3), days=Decimal("2"), requested_as="HR", approval_mode="HR_ONLY", status="APPROVED"),
            EmployeeLifecycleEvent(**base, event_type="ROLE_CHANGED", effective_on=date(2026,3,15), reason="DEPARTMENT_CHANGE", from_branch_id=uuid.UUID(bid), to_branch_id=uuid.UUID(destination["id"]), from_department_id=uuid.UUID(dept["id"]), to_department_id=uuid.UUID(new_dept["id"]), note="Private disciplinary details"),
        ])
        await session.commit()
    attendance = await report(client, owner, cid, "attendance", branch_id=bid)
    assert attendance["total_rows"] == 3
    assert next(m["value"] for m in attendance["summary"] if m["label"] == "Completed clock hours") == "8.50"
    assert next(r for r in attendance["rows"] if r["status"] == "LATE")["hours"] is None
    assert attendance["rows"][0]["branch"] != destination["name"]
    assert (await report(client, owner, cid, "attendance", branch_id=destination["id"]))["total_rows"] == 0
    leave = await report(client, owner, cid, "leave")
    assert leave["total_rows"] == 2  # Cross-boundary request included, future request excluded.
    assert next(m["value"] for m in leave["summary"] if m["label"] == "Approved request days") == "2.00"
    assert "not prorated" in leave["note"]
    assert (await report(client, owner, cid, "leave", branch_id=bid))["total_rows"] == 0
    movement = await report(client, owner, cid, "movement", branch_id=bid, department_id=dept["id"])
    assert movement["total_rows"] == 1
    assert movement["rows"][0]["to_branch"] == destination["name"]
    assert movement["rows"][0]["from_department"] == dept["name"]
    assert "Private disciplinary details" not in str(movement)
    assert (await report(client, owner, cid, "movement", branch_id=destination["id"]))["total_rows"] == 1


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_payroll_report_uses_approved_snapshots_and_separate_currencies(client):
    w, owner = await workspace(client)
    cid, bid = w["company"]["id"], w["branch"]["id"]
    uganda = await _uganda()
    ug = await create(client, owner, "/branches", {"company_id":cid,"country_id":str(uganda.id),"name":"Kampala","code":"UG"})
    runs = []
    for first, branch, salary in [("Kenyan", bid, "100000.13"), ("Ugandan", ug["id"], "1500000.37")]:
        p = await person(client, owner, w, first, branch=branch)
        settings = await client.put("/payroll/settings", headers=owner, params={"company_id":cid,"branch_id":branch}, json={"frequency":"MONTHLY","salary_structure":"GROSS_ONLY"})
        assert settings.status_code == 200, settings.text
        await create(client, owner, f"/employees/{p['id']}/compensation", {"effective_from":"2026-01-01","structure":"GROSS_ONLY","gross_amount":salary})
        run = await create(client, owner, "/payroll/runs", {"company_id":cid,"branch_id":branch,"period_start":"2026-03-01","period_end":"2026-03-31"})
        approved = await client.post(f"/payroll/runs/{run['id']}/approve", headers=owner)
        assert approved.status_code == 200
        runs.append(approved.json())
    await create(client, owner, "/payroll/runs", {"company_id":cid,"branch_id":bid,"period_start":"2026-04-01","period_end":"2026-04-30"})
    result = await report(client, owner, cid, "payroll")
    assert result["selected_status"] == "APPROVED" and result["total_rows"] == 2
    totals = {r["currency"]:r for r in result["breakdowns"][0]["rows"]}
    assert set(totals) == {"KES","UGX"}
    assert totals["KES"]["gross"] == "100000.13" and totals["UGX"]["gross"] == "1500000.00"  # Saved UGX payroll uses whole shillings.
    for run in runs:
        currency = run["currency_code"]
        assert Decimal(totals[currency]["net"]) == sum(Decimal(p["net"]) for p in run["payslips"])
    default_april = await client.get("/reports/payroll", headers=owner, params={"company_id":cid,"start_on":"2026-04-01","end_on":"2026-04-30"})
    assert default_april.status_code == 200 and default_april.json()["total_rows"] == 0
    drafts = await client.get("/reports/payroll", headers=owner, params={"company_id":cid,"start_on":"2026-04-01","end_on":"2026-04-30","status":"DRAFT"})
    assert drafts.status_code == 200 and drafts.json()["total_rows"] == 1
    assert (await report(client, owner, cid, "payroll", branch_id=bid))["breakdowns"][0]["rows"][0]["currency"] == "KES"
