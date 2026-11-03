from datetime import date

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_tenancy import _kenya, _register


async def _hire(client: AsyncClient, token: str, company_id: str, branch_id: str, email: str = "amina@a-corp.example"):
    created = await client.post(
        "/employees",
        headers=auth_header(token),
        json={
            "company_id": company_id,
            "branch_id": branch_id,
            "first_name": "Amina",
            "last_name": "Otieno",
            "email": email,
            "employment_type": "FULL_TIME",
            "date_joined": "2026-01-15",
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_lifecycle_transitions_and_rehire_modes(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="life-a@example.com",
        tenant_name="Tenant A",
        company_name="A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="life-b@example.com",
        tenant_name="Tenant B",
        company_name="B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    headers_b = auth_header(tenant_b["access_token"])
    company_a = tenant_a["company"]["id"]
    branch_a = tenant_a["branch"]["id"]

    employee = await _hire(client, tenant_a["access_token"], company_a, branch_a)
    assert employee["status"] == "ACTIVE"

    hired = await client.get(f"/employees/{employee['id']}/lifecycle", headers=headers_a)
    assert hired.status_code == 200
    assert [row["event_type"] for row in hired.json()] == ["HIRED"]

    blocked = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={"event_type": "REINSTATED", "reason": "Back", "effective_on": "2026-02-01"},
    )
    assert blocked.status_code == 400

    suspended = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={
            "event_type": "SUSPENDED",
            "reason": "Investigation",
            "effective_on": "2026-02-01",
            "pay_treatment": "WITH_PAY",
        },
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["employee"]["status"] == "SUSPENDED"
    assert suspended.json()["event"]["pay_treatment"] == "WITH_PAY"
    assert suspended.json()["event"]["pay_deduction_percent"] == 0
    assert suspended.json()["employee"]["suspension_pay_treatment"] == "WITH_PAY"

    promote_while_suspended = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={
            "event_type": "ROLE_CHANGED",
            "reason": "PROMOTION",
            "effective_on": "2026-02-02",
        },
    )
    assert promote_while_suspended.status_code == 400

    reinstated = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={"event_type": "REINSTATED", "reason": "Cleared", "effective_on": "2026-02-10"},
    )
    assert reinstated.status_code == 200
    assert reinstated.json()["employee"]["status"] == "ACTIVE"
    assert reinstated.json()["employee"]["suspension_pay_treatment"] is None
    assert reinstated.json()["employee"]["suspension_pay_deduction_percent"] is None

    dept = await client.post(
        "/departments",
        headers=headers_a,
        json={"company_id": company_a, "name": "Finance"},
    )
    title = await client.post(
        "/job-titles",
        headers=headers_a,
        json={"company_id": company_a, "name": "Accountant", "department_id": dept.json()["id"]},
    )
    promoted = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={
            "event_type": "ROLE_CHANGED",
            "reason": "PROMOTION",
            "effective_on": "2026-03-01",
            "department_id": dept.json()["id"],
            "job_title_id": title.json()["id"],
        },
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["employee"]["job_title_id"] == title.json()["id"]
    assert promoted.json()["employee"]["status"] == "ACTIVE"

    ended = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={"event_type": "TERMINATED", "reason": "Resignation", "effective_on": "2026-04-01"},
    )
    assert ended.status_code == 200
    assert ended.json()["employee"]["status"] == "TERMINATED"
    assert ended.json()["employee"]["date_ended"] == "2026-04-01"

    current = await client.get("/employees", headers=headers_a, params={"company_id": company_a})
    assert current.status_code == 200
    assert current.json() == []

    leavers = await client.get(
        "/employees",
        headers=headers_a,
        params={"company_id": company_a, "status": "TERMINATED"},
    )
    assert len(leavers.json()) == 1

    same = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={
            "event_type": "REHIRED",
            "rehire_mode": "SAME_RECORD",
            "effective_on": "2026-05-01",
            "note": "Came back",
        },
    )
    assert same.status_code == 200, same.text
    assert same.json()["employee"]["status"] == "ACTIVE"
    assert same.json()["employee"]["date_ended"] is None
    assert same.json()["employee"]["date_joined"] == "2026-01-15"
    assert same.json()["employee"]["employee_number"] == employee["employee_number"]

    await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={"event_type": "TERMINATED", "reason": "End of contract", "effective_on": "2026-06-01"},
    )
    fresh = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={
            "event_type": "REHIRED",
            "rehire_mode": "NEW_RECORD",
            "copy_from_previous": True,
            "effective_on": "2026-07-01",
            "email": "amina@a-corp.example",
        },
    )
    assert fresh.status_code == 200, fresh.text
    new_employee = fresh.json()["new_employee"]
    assert new_employee is not None
    assert new_employee["status"] == "ACTIVE"
    assert new_employee["previous_employee_id"] == employee["id"]
    assert new_employee["employee_number"] != employee["employee_number"]
    assert new_employee["email"] == "amina@a-corp.example"

    old = await client.get(f"/employees/{employee['id']}", headers=headers_a)
    assert old.json()["status"] == "TERMINATED"
    assert old.json()["email"] is None

    stolen = await client.get(f"/employees/{employee['id']}/lifecycle", headers=headers_b)
    assert stolen.status_code in {403, 404}

    hidden = await client.get("/lifecycle", headers=headers_b, params={"company_id": company_a})
    assert hidden.status_code == 403

    feed = await client.get("/lifecycle", headers=headers_a, params={"company_id": company_a})
    assert feed.status_code == 200
    types = {row["event_type"] for row in feed.json()}
    assert {"HIRED", "SUSPENDED", "REINSTATED", "ROLE_CHANGED", "TERMINATED", "REHIRED"}.issubset(types)

    by_name = await client.get(
        "/lifecycle",
        headers=headers_a,
        params={"company_id": company_a, "q": "Amina"},
    )
    assert by_name.status_code == 200
    assert by_name.json()
    assert all("Amina" in (row["employee_name"] or "") for row in by_name.json())

    by_number = await client.get(
        "/lifecycle",
        headers=headers_a,
        params={"company_id": company_a, "q": employee["employee_number"]},
    )
    assert by_number.status_code == 200
    assert by_number.json()
    assert all(row["employee_number"] == employee["employee_number"] for row in by_number.json())

    missed = await client.get(
        "/lifecycle",
        headers=headers_a,
        params={"company_id": company_a, "q": "nobody-xyz"},
    )
    assert missed.status_code == 200
    assert missed.json() == []


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_cannot_rehire_an_active_employee(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant = await _register(
        client,
        email="life-c@example.com",
        tenant_name="Tenant C",
        company_name="C Corp",
        country_id=kenya.id,
    )
    employee = await _hire(
        client,
        tenant["access_token"],
        tenant["company"]["id"],
        tenant["branch"]["id"],
        email="cate@c-corp.example",
    )
    refused = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=auth_header(tenant["access_token"]),
        json={"event_type": "REHIRED", "rehire_mode": "SAME_RECORD", "effective_on": str(date.today())},
    )
    assert refused.status_code == 400


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_lifecycle_attachments_on_suspend_role_and_terminate(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="life-docs-a@example.com",
        tenant_name="Docs A",
        company_name="Docs A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="life-docs-b@example.com",
        tenant_name="Docs B",
        company_name="Docs B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    headers_b = auth_header(tenant_b["access_token"])
    employee = await _hire(
        client,
        tenant_a["access_token"],
        tenant_a["company"]["id"],
        tenant_a["branch"]["id"],
        email="docs@a-corp.example",
    )
    hired_id = (await client.get(f"/employees/{employee['id']}/lifecycle", headers=headers_a)).json()[0]["id"]
    letter = ("notice.pdf", b"%PDF-1.4 notice", "application/pdf")

    hired_attach = await client.post(
        f"/employees/{employee['id']}/lifecycle/{hired_id}/attachments",
        headers=headers_a,
        files={"files": letter},
    )
    assert hired_attach.status_code == 400

    suspended = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={
            "event_type": "SUSPENDED",
            "reason": "Investigation",
            "effective_on": "2026-02-01",
            "pay_treatment": "WITH_PAY",
        },
    )
    assert suspended.status_code == 200
    event_id = suspended.json()["event"]["id"]

    uploaded = await client.post(
        f"/employees/{employee['id']}/lifecycle/{event_id}/attachments",
        headers=headers_a,
        files={"files": letter},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()[0]["filename"] == "notice.pdf"
    attachment_id = uploaded.json()[0]["id"]

    timeline = await client.get(f"/employees/{employee['id']}/lifecycle", headers=headers_a)
    suspended_row = next(row for row in timeline.json() if row["event_type"] == "SUSPENDED")
    assert len(suspended_row["attachments"]) == 1

    download = await client.get(
        f"/employees/{employee['id']}/lifecycle/{event_id}/attachments/{attachment_id}",
        headers=headers_a,
    )
    assert download.status_code == 200
    assert download.content == b"%PDF-1.4 notice"

    stolen = await client.get(
        f"/employees/{employee['id']}/lifecycle/{event_id}/attachments/{attachment_id}",
        headers=headers_b,
    )
    assert stolen.status_code in {403, 404}

    await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={"event_type": "REINSTATED", "reason": "Cleared", "effective_on": "2026-02-10"},
    )
    reinstated_id = next(
        row["id"]
        for row in (await client.get(f"/employees/{employee['id']}/lifecycle", headers=headers_a)).json()
        if row["event_type"] == "REINSTATED"
    )
    refused = await client.post(
        f"/employees/{employee['id']}/lifecycle/{reinstated_id}/attachments",
        headers=headers_a,
        files={"files": letter},
    )
    assert refused.status_code == 400

    dept = await client.post(
        "/departments",
        headers=headers_a,
        json={"company_id": tenant_a["company"]["id"], "name": "Operations"},
    )
    assert dept.status_code == 201, dept.text
    role = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={
            "event_type": "ROLE_CHANGED",
            "reason": "DEMOTION",
            "effective_on": "2026-03-01",
            "department_id": dept.json()["id"],
        },
    )
    assert role.status_code == 200, role.text
    ended = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={"event_type": "TERMINATED", "reason": "End of contract", "effective_on": "2026-04-01"},
    )
    assert ended.status_code == 200, ended.text
    for result in (role, ended):
        attached = await client.post(
            f"/employees/{result.json()['employee']['id']}/lifecycle/{result.json()['event']['id']}/attachments",
            headers=headers_a,
            files={"files": ("letter.txt", b"notice", "text/plain")},
        )
        assert attached.status_code == 200, attached.text


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_rehire_intern_needs_period_dates(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant = await _register(
        client,
        email="life-intern@example.com",
        tenant_name="Intern Tenant",
        company_name="Intern Corp",
        country_id=kenya.id,
    )
    headers = auth_header(tenant["access_token"])
    created = await client.post(
        "/employees",
        headers=headers,
        json={
            "company_id": tenant["company"]["id"],
            "branch_id": tenant["branch"]["id"],
            "first_name": "Imani",
            "last_name": "Wanjiru",
            "email": "imani@intern-corp.example",
            "employment_type": "INTERN",
            "date_joined": "2026-01-01",
            "date_ended": "2026-03-31",
        },
    )
    assert created.status_code == 201, created.text
    employee_id = created.json()["id"]
    await client.post(
        f"/employees/{employee_id}/lifecycle",
        headers=headers,
        json={"event_type": "TERMINATED", "reason": "Ended", "effective_on": "2026-03-31"},
    )

    missing = await client.post(
        f"/employees/{employee_id}/lifecycle",
        headers=headers,
        json={"event_type": "REHIRED", "rehire_mode": "SAME_RECORD", "effective_on": "2026-04-15"},
    )
    assert missing.status_code == 400
    assert "start date" in missing.json()["detail"].lower()

    same = await client.post(
        f"/employees/{employee_id}/lifecycle",
        headers=headers,
        json={
            "event_type": "REHIRED",
            "rehire_mode": "SAME_RECORD",
            "effective_on": "2026-04-15",
            "employment_type": "INTERN",
            "date_joined": "2026-04-15",
            "date_ended": "2026-07-15",
        },
    )
    assert same.status_code == 200, same.text
    assert same.json()["employee"]["employment_type"] == "INTERN"
    assert same.json()["employee"]["date_joined"] == "2026-04-15"
    assert same.json()["employee"]["date_ended"] == "2026-07-15"

    await client.post(
        f"/employees/{employee_id}/lifecycle",
        headers=headers,
        json={"event_type": "TERMINATED", "reason": "Ended", "effective_on": "2026-07-15"},
    )
    fresh = await client.post(
        f"/employees/{employee_id}/lifecycle",
        headers=headers,
        json={
            "event_type": "REHIRED",
            "rehire_mode": "NEW_RECORD",
            "copy_from_previous": True,
            "effective_on": "2026-08-01",
            "employment_type": "PROBATION",
            "date_joined": "2026-08-01",
            "date_ended": "2026-10-30",
        },
    )
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["new_employee"]["employment_type"] == "PROBATION"
    assert fresh.json()["new_employee"]["date_joined"] == "2026-08-01"
    assert fresh.json()["new_employee"]["date_ended"] == "2026-10-30"

    await client.post(
        f"/employees/{fresh.json()['new_employee']['id']}/lifecycle",
        headers=headers,
        json={"event_type": "TERMINATED", "reason": "Ended", "effective_on": "2026-10-30"},
    )
    converted = await client.post(
        f"/employees/{fresh.json()['new_employee']['id']}/lifecycle",
        headers=headers,
        json={
            "event_type": "REHIRED",
            "rehire_mode": "SAME_RECORD",
            "effective_on": "2026-11-01",
            "employment_type": "FULL_TIME",
        },
    )
    assert converted.status_code == 200, converted.text
    assert converted.json()["employee"]["employment_type"] == "FULL_TIME"
    assert converted.json()["employee"]["date_ended"] is None


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_extend_intern_and_contract(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant = await _register(
        client,
        email="life-extend@example.com",
        tenant_name="Extend Tenant",
        company_name="Extend Corp",
        country_id=kenya.id,
    )
    headers = auth_header(tenant["access_token"])
    intern = await client.post(
        "/employees",
        headers=headers,
        json={
            "company_id": tenant["company"]["id"],
            "branch_id": tenant["branch"]["id"],
            "first_name": "Ivy",
            "last_name": "Kamau",
            "email": "ivy@extend-corp.example",
            "employment_type": "INTERN",
            "date_joined": "2026-01-01",
            "date_ended": "2026-03-31",
        },
    )
    assert intern.status_code == 201, intern.text
    intern_id = intern.json()["id"]

    refused_full_time = await client.post(
        f"/employees/{intern_id}/lifecycle",
        headers=headers,
        json={"event_type": "EXTENDED", "reason": "DAYS", "extension_days": 30, "effective_on": "2026-03-01"},
    )
    # intern can extend
    assert refused_full_time.status_code == 200, refused_full_time.text
    assert refused_full_time.json()["employee"]["date_ended"] == "2026-04-30"
    assert refused_full_time.json()["event"]["reason"] == "DAYS"
    assert refused_full_time.json()["event"]["extension_days"] == 30
    assert refused_full_time.json()["event"]["from_date_ended"] == "2026-03-31"
    assert refused_full_time.json()["event"]["to_date_ended"] == "2026-04-30"
    assert refused_full_time.json()["event"]["employment_type"] == "INTERN"
    attached = await client.post(
        f"/employees/{intern_id}/lifecycle/{refused_full_time.json()['event']['id']}/attachments",
        headers=headers,
        files={"files": ("extension.pdf", b"%PDF-1.4 extension", "application/pdf")},
    )
    assert attached.status_code == 200, attached.text

    too_soon = await client.post(
        f"/employees/{intern_id}/lifecycle",
        headers=headers,
        json={
            "event_type": "EXTENDED",
            "reason": "UNTIL_DATE",
            "date_ended": "2026-04-15",
            "effective_on": "2026-04-01",
        },
    )
    assert too_soon.status_code == 400

    contract = await client.post(
        "/employees",
        headers=headers,
        json={
            "company_id": tenant["company"]["id"],
            "branch_id": tenant["branch"]["id"],
            "first_name": "Cole",
            "last_name": "Mwangi",
            "email": "cole@extend-corp.example",
            "employment_type": "CONTRACT",
            "date_joined": "2026-01-01",
        },
    )
    assert contract.status_code == 201, contract.text
    until = await client.post(
        f"/employees/{contract.json()['id']}/lifecycle",
        headers=headers,
        json={
            "event_type": "EXTENDED",
            "reason": "UNTIL_DATE",
            "date_ended": "2026-12-31",
            "effective_on": "2026-02-01",
        },
    )
    assert until.status_code == 200, until.text
    assert until.json()["employee"]["date_ended"] == "2026-12-31"
    assert until.json()["event"]["from_date_ended"] is None
    assert until.json()["event"]["employment_type"] == "CONTRACT"

    staff = await _hire(
        client,
        tenant["access_token"],
        tenant["company"]["id"],
        tenant["branch"]["id"],
        email="staff@extend-corp.example",
    )
    blocked = await client.post(
        f"/employees/{staff['id']}/lifecycle",
        headers=headers,
        json={"event_type": "EXTENDED", "reason": "DAYS", "extension_days": 30, "effective_on": "2026-03-01"},
    )
    assert blocked.status_code == 400


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_suspension_pay_treatments(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant = await _register(
        client,
        email="life-pay@example.com",
        tenant_name="Pay Tenant",
        company_name="Pay Corp",
        country_id=kenya.id,
    )
    headers = auth_header(tenant["access_token"])
    employee = await _hire(
        client,
        tenant["access_token"],
        tenant["company"]["id"],
        tenant["branch"]["id"],
        email="pay@pay-corp.example",
    )

    missing = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers,
        json={"event_type": "SUSPENDED", "reason": "Case", "effective_on": "2026-02-01"},
    )
    assert missing.status_code == 400

    unpaid = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers,
        json={
            "event_type": "SUSPENDED",
            "reason": "Case",
            "effective_on": "2026-02-01",
            "pay_treatment": "WITHOUT_PAY",
        },
    )
    assert unpaid.status_code == 200, unpaid.text
    assert unpaid.json()["event"]["pay_treatment"] == "WITHOUT_PAY"
    assert unpaid.json()["event"]["pay_deduction_percent"] == 100
    assert unpaid.json()["employee"]["suspension_pay_treatment"] == "WITHOUT_PAY"

    await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers,
        json={"event_type": "REINSTATED", "reason": "Cleared", "effective_on": "2026-02-10"},
    )
    no_percent = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers,
        json={
            "event_type": "SUSPENDED",
            "reason": "Case",
            "effective_on": "2026-03-01",
            "pay_treatment": "PARTIAL",
        },
    )
    assert no_percent.status_code == 400

    partial = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers,
        json={
            "event_type": "SUSPENDED",
            "reason": "Case",
            "effective_on": "2026-03-01",
            "pay_treatment": "PARTIAL",
            "pay_deduction_percent": 25,
        },
    )
    assert partial.status_code == 200, partial.text
    assert partial.json()["event"]["pay_treatment"] == "PARTIAL"
    assert partial.json()["event"]["pay_deduction_percent"] == 25
    assert partial.json()["employee"]["suspension_pay_deduction_percent"] == 25
