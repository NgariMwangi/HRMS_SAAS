from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from app.db.session import get_session_maker
from app.models import Employee, LeaveRequest
from tests.test_access import workspace, staff_login
from tests.test_leave_requests import _person, _leave_type
from tests.test_workforce_payments import salary, run


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_dashboard_scopes_permissions_and_real_employee_alerts(client):
    w, owner = await workspace(client)
    foreign, _ = await workspace(client, "dashboard-foreign@example.com")
    _, _, staff = await staff_login(client, owner, w, "DashboardStaff")
    second = (await client.post("/companies", headers=owner, json={"name": "Dashboard second"})).json()
    branch = (await client.post("/branches", headers=owner, json={"company_id": second["id"], "country_id": w["branch"]["country_id"], "name": "Other office", "code": "OTHER"})).json()
    person = await _person(client, owner, second["id"], branch["id"], "BirthdayContract", None)
    today = datetime.now(ZoneInfo("Africa/Nairobi")).date()
    async with get_session_maker()() as session:
        row = await session.get(Employee, UUID(person["id"]))
        row.date_of_birth = today.replace(year=2000)
        row.employment_type = "CONTRACT"
        row.date_ended = today + timedelta(days=30)
        row.bank_account_number = "PRIVATE-ACCOUNT"
        await session.commit()
    path = f"/employees/dashboard?company_id={w['company']['id']}"
    response = await client.get(path, headers=owner)
    assert response.status_code == 200, response.text
    assert response.json()["contracts"] == []
    response = await client.get("/employees/dashboard?month=2026-11", headers=owner)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["companies"] == 2
    assert data["branches"] == 2
    assert data["alerts"]["birthdays"][0]["employee_id"] == person["id"]
    assert data["contracts"][0]["days"] == 30
    assert data["pending"] == {"leave": 0, "payroll": 0, "overtime": 0}
    item = next(row for row in data["missing"] if row["employee_id"] == person["id"])
    assert {"Work email", "Current salary", "Bank details", "PIN number"} <= set(item["missing"])
    assert "PRIVATE-ACCOUNT" not in response.text
    assert (await client.get(f"/employees/dashboard?company_id={foreign['company']['id']}", headers=owner)).status_code == 403
    assert (await client.get("/employees/dashboard", headers=staff)).status_code == 403
    response = await client.get(path, headers=staff)
    assert response.status_code == 200, response.text
    assert response.json()["payroll"] is None
    assert response.json()["missing"] is None
    assert response.json()["alerts"] is None
    assert (await client.get(path + "&month=2026-99", headers=owner)).status_code == 422


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_dashboard_leave_today_and_pending_decisions(client):
    w, owner = await workspace(client)
    person = await _person(client, owner, w["company"]["id"], w["branch"]["id"], "PartialLeave", "partial@example.com")
    leave_type = await _leave_type(client, owner, w["company"]["id"], basis="CALENDAR")
    today = datetime.now(ZoneInfo("Africa/Nairobi")).date()
    async with get_session_maker()() as session:
        session.add(LeaveRequest(company_id=UUID(w["company"]["id"]), employee_id=UUID(person["id"]),
            leave_type_id=UUID(leave_type["id"]), start_on=today, end_on=today, days=Decimal("0.25"),
            requested_as="SELF", approval_mode="HR_ONLY", status="APPROVED"))
        session.add(LeaveRequest(company_id=UUID(w["company"]["id"]), employee_id=UUID(person["id"]),
            leave_type_id=UUID(leave_type["id"]), start_on=today + timedelta(days=2), end_on=today + timedelta(days=2),
            days=1, requested_as="SELF", approval_mode="HR_ONLY", status="PENDING_HR"))
        await session.commit()
    response = await client.get(f"/employees/dashboard?company_id={w['company']['id']}", headers=owner)
    assert response.status_code == 200, response.text
    assert response.json()["pending"]["leave"] == 1
    assert response.json()["on_leave"][0]["portion"] == "0.25"
    assert response.json()["on_leave"][0]["return_on"] is None


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_dashboard_payroll_month_totals_and_approval_activity(client):
    w, owner = await workspace(client)
    person = await _person(client, owner, w["company"]["id"], w["branch"]["id"], "DashboardPayroll", "dashboard-payroll@example.com")
    await salary(client, owner, person["id"])
    payroll = await run(client, owner, w)
    overtime = await client.post("/workforce/overtime", headers=owner, json={
        "employee_id": person["id"], "worked_dates": ["2026-04-02"], "days": "1", "daily_rate": "1000", "month": "2026-04-01"})
    assert overtime.status_code == 201, overtime.text
    path = f"/employees/dashboard?company_id={w['company']['id']}"
    response = await client.get(path + "&month=2026-04", headers=owner)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["pending"]["payroll"] == 1
    assert data["pending"]["overtime"] == 1
    assert data["payroll"][0]["employees"] == 1
    assert data["payroll"][0]["currency"] == "KES"
    assert Decimal(data["payroll"][0]["gross"]) == Decimal(payroll["gross_total"])
    assert Decimal(data["payroll"][0]["net"]) == Decimal(payroll["net_total"])
    latest = (await client.get(path, headers=owner)).json()
    assert latest["month"] == "2026-04"
    assert latest["payroll"][0]["id"] == payroll["id"]
    assert (await client.get(path + "&month=2026-05", headers=owner)).json()["payroll"] == []
    assert (await client.post(f"/payroll/runs/{payroll['id']}/approve", headers=owner)).status_code == 200
    data = (await client.get(path + "&month=2026-04", headers=owner)).json()
    assert data["pending"]["payroll"] == 0
    assert any("Payroll approved" in row["title"] for row in data["activity"])
