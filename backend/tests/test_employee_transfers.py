from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID
import pytest
from sqlalchemy import select
from app.db.session import get_session_maker
from app.models import Employee, User, PayrollPayslip, LeaveRequest, EmployeeLifecycleEvent
from tests.test_access import workspace, staff_login
from tests.test_leave_requests import _leave_type
from tests.test_workforce_payments import salary, run
from tests.test_platform import _admin_login


async def destination(client, owner, w):
    company = (await client.post("/companies", headers=owner, json={"name": "Transfer destination"})).json()
    response = await client.post("/branches", headers=owner, json={"company_id": company["id"], "country_id": w["branch"]["country_id"], "name": "Destination office", "code": "DEST"})
    assert response.status_code == 201, response.text
    return company, response.json()


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_company_transfer_preserves_history_and_login_and_supports_destination_domain(client):
    w, owner = await workspace(client)
    person, _, employee_headers = await staff_login(client, owner, w, "CompanyTransfer")
    await salary(client, owner, person["id"])
    payroll = await run(client, owner, w)
    assert (await client.post(f"/payroll/runs/{payroll['id']}/approve", headers=owner)).status_code == 200
    await client.patch(f"/employees/{person['id']}/pay-settings", headers=owner, json={"bank_name": "Original bank", "bank_account_number": "123456"})
    leave_type = await _leave_type(client, owner, w["company"]["id"], basis="CALENDAR")
    leave = await client.post("/leave-requests/hr", headers=owner, json={"employee_id": person["id"], "leave_type_id": leave_type["id"],
        "start_on": "2026-05-04", "end_on": "2026-05-04", "hr_action": "APPROVE_NOW"})
    assert leave.status_code == 201, leave.text
    company, branch = await destination(client, owner, w)
    async with get_session_maker()() as session:
        account = await session.scalar(select(User).where(User.employee_id == UUID(person["id"])))
        identity, password = account.id, account.password_hash
    response = await client.post(f"/employees/{person['id']}/transfer-company", headers=owner, json={"company_id": company["id"], "branch_id": branch["id"]})
    assert response.status_code == 200, response.text
    moved = response.json()
    assert moved["id"] != person["id"] and moved["previous_employee_id"] == person["id"]
    assert moved["company_id"] == company["id"] and moved["branch_id"] == branch["id"]
    assert moved["department_id"] is None and moved["job_title_id"] is None
    assert "bank_account_number" not in moved
    assert (await client.get(f"/employees/{moved['id']}/pay-settings", headers=owner)).json()["bank_account_number"] == "123456"
    assert (await client.get(f"/employees/{person['id']}", headers=owner)).json()["status"] == "TERMINATED"
    assert (await client.get(f"/employees/{moved['id']}/compensation", headers=owner)).json() == []
    assert (await client.get("/employee-portal/me", headers=employee_headers)).json()["employee"]["id"] == moved["id"]
    async with get_session_maker()() as session:
        account = await session.get(User, identity)
        assert account.employee_id == UUID(moved["id"]) and account.password_hash == password
        slip = await session.get(PayrollPayslip, UUID(payroll["payslips"][0]["id"]))
        assert str(slip.employee_id) == person["id"] and str(slip.company_id) == w["company"]["id"]
        request = await session.get(LeaveRequest, UUID(leave.json()["id"]))
        assert str(request.employee_id) == person["id"] and str(request.company_id) == w["company"]["id"]
        assert len((await session.scalars(select(EmployeeLifecycleEvent).where(EmployeeLifecycleEvent.event_type == "TRANSFERRED"))).all()) == 2
    host = (await client.get(f"/domains?company_id={company['id']}", headers=owner)).json()[0]["hostname"]
    response = await client.patch(f"/employees/{moved['id']}", headers={**owner, "Host": host}, json={"phone": "+254700111222"})
    assert response.status_code == 200, response.text
    assert (await client.get(f"/employees/{person['id']}", headers={**owner, "Host": host})).status_code == 404
    again = await client.post(f"/employees/{person['id']}/transfer-company", headers=owner, json={"company_id": company["id"], "branch_id": branch["id"]})
    assert again.status_code == 409


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_transfer_rejects_foreign_company_wrong_branch_and_employee_access(client):
    w, owner = await workspace(client)
    person, _, employee = await staff_login(client, owner, w, "TransferBoundary")
    foreign, _ = await workspace(client, "transfer-foreign@example.com")
    company, branch = await destination(client, owner, w)
    path = f"/employees/{person['id']}/transfer-company"
    body = {"company_id": company["id"], "branch_id": branch["id"]}
    assert (await client.post(path, headers=employee, json=body)).status_code == 403
    assert (await client.post(path, headers=owner, json={"company_id": foreign["company"]["id"], "branch_id": foreign["branch"]["id"]})).status_code == 403
    assert (await client.post(path, headers=owner, json={**body, "branch_id": w["branch"]["id"]})).status_code == 400
    host = (await client.get(f"/domains?company_id={w['company']['id']}", headers=owner)).json()[0]["hostname"]
    assert (await client.post(path, headers={**owner, "Host": host}, json=body)).status_code in {403, 404}
    tomorrow = (datetime.now(ZoneInfo("Africa/Nairobi")).date() + timedelta(days=1)).isoformat()
    assert (await client.post(path, headers=owner, json={**body, "effective_on": tomorrow})).status_code == 400


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_pending_work_blocks_transfer_then_platform_can_complete_it(client):
    w, owner = await workspace(client)
    person, _, employee = await staff_login(client, owner, w, "TransferPending")
    company, branch = await destination(client, owner, w)
    leave_type = await _leave_type(client, owner, w["company"]["id"], basis="CALENDAR")
    request = await client.post("/leave-requests/self", headers=employee, json={"employee_id": person["id"], "leave_type_id": leave_type["id"], "start_on": "2026-12-01", "end_on": "2026-12-01"})
    assert request.status_code == 201, request.text
    path = f"/employees/{person['id']}/transfer-company"
    body = {"company_id": company["id"], "branch_id": branch["id"]}
    response = await client.post(path, headers=owner, json=body)
    assert response.status_code == 409 and "pending leave" in response.json()["detail"]
    assert (await client.get(f"/employees/{person['id']}", headers=owner)).json()["status"] == "ACTIVE"
    cancelled = await client.post(f"/leave-requests/{request.json()['id']}/cancel", headers=owner)
    assert cancelled.status_code == 200, cancelled.text
    await salary(client, owner, person["id"])
    payroll = await run(client, owner, w)
    response = await client.post(path, headers=owner, json=body)
    assert response.status_code == 409 and "draft payrolls" in response.json()["detail"]
    await client.post(f"/payroll/runs/{payroll['id']}/approve", headers=owner)
    admin = await _admin_login(client)
    response = await client.post(f"/platform/tenants/{w['tenant']['id']}{path}", headers=admin, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["company_id"] == company["id"]


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_destination_conflict_rolls_back_without_closing_original(client):
    from tests.test_leave_requests import _person
    w, owner = await workspace(client)
    person, _, _ = await staff_login(client, owner, w, "TransferDuplicate")
    company, branch = await destination(client, owner, w)
    await _person(client, owner, company["id"], branch["id"], "Already there", person["email"])
    response = await client.post(f"/employees/{person['id']}/transfer-company", headers=owner,
        json={"company_id": company["id"], "branch_id": branch["id"]})
    assert response.status_code == 409, response.text
    async with get_session_maker()() as session:
        original = await session.get(Employee, UUID(person["id"]))
        assert original.status == "ACTIVE"
        login = await session.scalar(select(User).where(User.employee_id == original.id))
        assert login is not None
        assert len((await session.scalars(select(Employee).where(Employee.company_id == UUID(company["id"])))).all()) == 1
