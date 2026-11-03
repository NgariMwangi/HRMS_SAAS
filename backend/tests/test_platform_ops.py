from datetime import date

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_platform import _admin_login, _register
from tests.test_tenancy import _kenya


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_platform_admin_runs_leave_attendance_payroll_and_clock_login(
    client: AsyncClient,
) -> None:
    kenya = await _kenya()
    tenant = await _register(client, "ops-owner@example.com", str(kenya.id))
    other = await _register(client, "ops-other@example.com", str(kenya.id))
    tenant_id = tenant["tenant"]["id"]
    other_id = other["tenant"]["id"]
    company_id = tenant["company"]["id"]
    branch_id = tenant["branch"]["id"]
    admin = await _admin_login(client)
    base = f"/platform/tenants/{tenant_id}"

    employee = await client.post(
        f"{base}/employees",
        headers=admin,
        json={
            "company_id": company_id,
            "branch_id": branch_id,
            "first_name": "Amina",
            "last_name": "Wanjiku",
            "email": "amina.ops@example.com",
            "id_number": "12345678",
            "nssf_no": "NSSF-1",
            "shif_no": "SHIF-1",
        },
    )
    assert employee.status_code == 201, employee.text
    employee_id = employee.json()["id"]
    assert employee.json()["id_number"] == "12345678"

    clash = await client.post(
        f"{base}/employees",
        headers=admin,
        json={
            "company_id": company_id,
            "branch_id": branch_id,
            "first_name": "Other",
            "last_name": "Person",
            "id_number": "12345678",
        },
    )
    assert clash.status_code == 409

    leave_type = await client.post(
        f"{base}/leave-types",
        headers=admin,
        json={"company_id": company_id, "name": "Annual", "days": "21", "accrued": True, "day_basis": "WORKING"},
    )
    assert leave_type.status_code == 201, leave_type.text
    leave_type_id = leave_type.json()["id"]

    applied = await client.post(
        f"{base}/leave-requests/hr",
        headers=admin,
        json={
            "employee_id": employee_id,
            "leave_type_id": leave_type_id,
            "start_on": "2026-04-06",
            "end_on": "2026-04-08",
            "hr_action": "APPROVE_NOW",
        },
    )
    assert applied.status_code == 201, applied.text
    assert applied.json()["status"] == "APPROVED"

    listed = await client.get(f"{base}/leave-requests", headers=admin, params={"company_id": company_id})
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    balances = await client.get(
        f"{base}/leave-balances",
        headers=admin,
        params={"company_id": company_id, "employee_id": employee_id, "year": 2026},
    )
    assert balances.status_code == 200
    assert balances.json()

    holiday = await client.post(
        f"{base}/public-holidays",
        headers=admin,
        json={"company_id": company_id, "name": "Test Day", "kind": "ONCE", "observed_on": "2026-12-12"},
    )
    assert holiday.status_code == 201, holiday.text

    work_on = date(2026, 3, 16).isoformat()
    register = await client.get(
        f"{base}/attendance",
        headers=admin,
        params={"company_id": company_id, "branch_id": branch_id, "work_on": work_on},
    )
    assert register.status_code == 200, register.text
    assert any(row["employee_id"] == employee_id for row in register.json())

    marked = await client.put(
        f"{base}/attendance",
        headers=admin,
        json={"employee_id": employee_id, "work_on": work_on, "status": "PRESENT"},
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["status"] == "PRESENT"

    settings = await client.put(
        f"{base}/payroll/settings",
        headers=admin,
        params={"company_id": company_id, "branch_id": branch_id},
        json={"frequency": "MONTHLY", "salary_structure": "GROSS_ONLY"},
    )
    assert settings.status_code == 200, settings.text
    assert settings.json()["country_code"] == "KE"

    pay = await client.post(
        f"{base}/employees/{employee_id}/compensation",
        headers=admin,
        json={"effective_from": "2026-01-01", "structure": "GROSS_ONLY", "gross_amount": "100000"},
    )
    assert pay.status_code == 201, pay.text

    run = await client.post(
        f"{base}/payroll/runs",
        headers=admin,
        json={
            "company_id": company_id,
            "branch_id": branch_id,
            "period_start": "2026-03-01",
            "period_end": "2026-03-31",
        },
    )
    assert run.status_code == 201, run.text
    assert run.json()["payslips"]

    login = await client.post(
        f"{base}/employees/{employee_id}/login",
        headers=admin,
        json={"email": "amina.clock@example.com", "password": "password12"},
    )
    assert login.status_code == 201, login.text
    profile = await client.get(f"{base}/employees/{employee_id}", headers=admin)
    assert profile.status_code == 200
    assert profile.json()["clock_login_email"] == "amina.clock@example.com"

    events = await client.get(f"{base}/lifecycle", headers=admin, params={"company_id": company_id})
    assert events.status_code == 200
    assert events.json()

    hidden = await client.get(
        f"/platform/tenants/{other_id}/employees/{employee_id}",
        headers=admin,
    )
    assert hidden.status_code == 403

    tenant_blocked = await client.get(
        f"{base}/payroll/runs",
        headers=auth_header(tenant["access_token"]),
        params={"company_id": company_id, "branch_id": branch_id},
    )
    assert tenant_blocked.status_code == 403
