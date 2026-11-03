from datetime import date

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_tenancy import _kenya, _register


async def _person(client, headers, company_id, branch_id, first, email) -> dict:
    created = await client.post(
        "/employees",
        headers=headers,
        json={
            "company_id": company_id,
            "branch_id": branch_id,
            "first_name": first,
            "last_name": "Otieno",
            "email": email,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


async def _leave_type(client, headers, company_id, name="Annual", basis="WORKING") -> dict:
    created = await client.post(
        "/leave-types",
        headers=headers,
        json={"company_id": company_id, "name": name, "days": 21, "accrued": True, "day_basis": basis},
    )
    assert created.status_code == 201, created.text
    return created.json()


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_leave_request_paths_for_hr_employee_and_supervisor(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="lr-a@example.com",
        tenant_name="Leave Req A",
        company_name="LR A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="lr-b@example.com",
        tenant_name="Leave Req B",
        company_name="LR B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    headers_b = auth_header(tenant_b["access_token"])
    company_a = tenant_a["company"]["id"]
    branch_a = tenant_a["branch"]["id"]

    report = await _person(client, headers_a, company_a, branch_a, "Amina", "amina@lr.example")
    lead = await _person(client, headers_a, company_a, branch_a, "Kesi", "kesi@lr.example")
    annual = await _leave_type(client, headers_a, company_a)
    sick = await _leave_type(client, headers_a, company_a, "Sick", "CALENDAR")
    await client.put(
        f"/employees/{report['id']}/supervisors",
        headers=headers_a,
        json={"supervisor_ids": [lead["id"]]},
    )

    monday = date(2026, 6, 1)
    friday = date(2026, 6, 5)
    weekend = (date(2026, 6, 6), date(2026, 6, 7))

    approved = await client.post(
        "/leave-requests/hr",
        headers=headers_a,
        json={
            "employee_id": report["id"],
            "leave_type_id": annual["id"],
            "start_on": monday.isoformat(),
            "end_on": friday.isoformat(),
            "reason": "Family",
            "hr_action": "APPROVE_NOW",
        },
    )
    assert approved.status_code == 201, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["requested_as"] == "HR"
    assert float(approved.json()["days"]) == 4
    assert approved.json()["employee_name"].startswith("Amina")

    overlap = await client.post(
        "/leave-requests/hr",
        headers=headers_a,
        json={
            "employee_id": report["id"],
            "leave_type_id": annual["id"],
            "start_on": "2026-06-04",
            "end_on": "2026-06-08",
            "hr_action": "APPROVE_NOW",
        },
    )
    assert overlap.status_code == 400

    later_start = date(2026, 7, 6)
    later_end = date(2026, 7, 8)
    to_supervisor = await client.post(
        "/leave-requests/hr",
        headers=headers_a,
        json={
            "employee_id": report["id"],
            "leave_type_id": sick["id"],
            "start_on": later_start.isoformat(),
            "end_on": later_end.isoformat(),
            "hr_action": "SEND_TO_SUPERVISOR",
        },
    )
    assert to_supervisor.status_code == 201, to_supervisor.text
    assert to_supervisor.json()["status"] == "PENDING_SUPERVISOR"
    assert float(to_supervisor.json()["days"]) == 3

    decided = await client.post(
        f"/leave-requests/{to_supervisor.json()['id']}/supervisor-decision",
        headers=headers_a,
        json={"decision": "APPROVED", "supervisor_employee_id": lead["id"]},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "APPROVED"

    self_hr = await client.post(
        "/leave-requests/self",
        headers=headers_a,
        json={
            "employee_id": lead["id"],
            "leave_type_id": annual["id"],
            "start_on": "2026-08-03",
            "end_on": "2026-08-04",
            "approval_mode": "HR_ONLY",
        },
    )
    assert self_hr.status_code == 201, self_hr.text
    assert self_hr.json()["status"] == "PENDING_HR"
    assert self_hr.json()["requested_as"] == "EMPLOYEE"
    hr_ok = await client.post(
        f"/leave-requests/{self_hr.json()['id']}/hr-decision",
        headers=headers_a,
        json={"decision": "APPROVED"},
    )
    assert hr_ok.status_code == 200
    assert hr_ok.json()["status"] == "APPROVED"

    self_both = await client.post(
        "/leave-requests/self",
        headers=headers_a,
        json={
            "employee_id": report["id"],
            "leave_type_id": annual["id"],
            "start_on": "2026-09-07",
            "end_on": "2026-09-08",
            "approval_mode": "SUPERVISOR_THEN_HR",
        },
    )
    assert self_both.status_code == 201, self_both.text
    assert self_both.json()["status"] == "PENDING_SUPERVISOR"
    mid = await client.post(
        f"/leave-requests/{self_both.json()['id']}/supervisor-decision",
        headers=headers_a,
        json={"decision": "APPROVED", "supervisor_employee_id": lead["id"]},
    )
    assert mid.json()["status"] == "PENDING_HR"
    done = await client.post(
        f"/leave-requests/{self_both.json()['id']}/hr-decision",
        headers=headers_a,
        json={"decision": "APPROVED"},
    )
    assert done.json()["status"] == "APPROVED"

    supervisor_apply = await client.post(
        "/leave-requests/supervisor",
        headers=headers_a,
        json={
            "supervisor_employee_id": lead["id"],
            "employee_id": report["id"],
            "leave_type_id": annual["id"],
            "start_on": "2026-10-05",
            "end_on": "2026-10-06",
        },
    )
    assert supervisor_apply.status_code == 201, supervisor_apply.text
    assert supervisor_apply.json()["status"] == "PENDING_HR"
    assert supervisor_apply.json()["requested_as"] == "SUPERVISOR"

    not_their = await client.post(
        "/leave-requests/supervisor",
        headers=headers_a,
        json={
            "supervisor_employee_id": report["id"],
            "employee_id": lead["id"],
            "leave_type_id": annual["id"],
            "start_on": "2026-11-02",
            "end_on": "2026-11-03",
        },
    )
    assert not_their.status_code == 400

    empty_weekend = await client.post(
        "/leave-requests/hr",
        headers=headers_a,
        json={
            "employee_id": lead["id"],
            "leave_type_id": annual["id"],
            "start_on": weekend[0].isoformat(),
            "end_on": weekend[1].isoformat(),
            "hr_action": "APPROVE_NOW",
        },
    )
    assert empty_weekend.status_code == 400

    stolen = await client.get("/leave-requests", headers=headers_b, params={"company_id": company_a})
    assert stolen.status_code == 403

    listed = await client.get("/leave-requests", headers=headers_a, params={"company_id": company_a})
    assert listed.status_code == 200
    assert len(listed.json()) >= 4

    ended = await client.post(
        f"/employees/{lead['id']}/lifecycle",
        headers=headers_a,
        json={"event_type": "TERMINATED", "reason": "Resignation", "effective_on": "2026-12-01"},
    )
    assert ended.status_code == 200, ended.text
    on_ended = await client.post(
        "/leave-requests/hr",
        headers=headers_a,
        json={
            "employee_id": lead["id"],
            "leave_type_id": annual["id"],
            "start_on": "2026-12-07",
            "end_on": "2026-12-08",
            "hr_action": "APPROVE_NOW",
        },
    )
    assert on_ended.status_code == 400
