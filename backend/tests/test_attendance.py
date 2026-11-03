import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_leave_requests import _leave_type, _person
from tests.test_tenancy import _kenya, _register


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_self_clock_in_device_rules_and_hr_roster(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="att-a@example.com",
        tenant_name="Att A",
        company_name="Att A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="att-b@example.com",
        tenant_name="Att B",
        company_name="Att B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    headers_b = auth_header(tenant_b["access_token"])
    company_a = tenant_a["company"]["id"]
    branch_a = tenant_a["branch"]["id"]
    amina = await _person(client, headers_a, company_a, branch_a, "Amina", "amina@att.example")
    john = await _person(client, headers_a, company_a, branch_a, "John", "john@att.example")

    no_link = await client.post("/attendance/clock-in", headers=headers_a, json={"device_id": "device-owner-01"})
    assert no_link.status_code == 403

    login = await client.post(
        f"/employees/{amina['id']}/login",
        headers=headers_a,
        json={"email": "amina.clock@example.com", "password": "password12"},
    )
    assert login.status_code == 201, login.text
    assert login.json()["employee_id"] == amina["id"]
    john_login = await client.post(
        f"/employees/{john['id']}/login",
        headers=headers_a,
        json={"email": "john.clock@example.com", "password": "password12"},
    )
    assert john_login.status_code == 201, john_login.text

    amina_auth = await client.post("/auth/login", json={"email": "amina.clock@example.com", "password": "password12"})
    john_auth = await client.post("/auth/login", json={"email": "john.clock@example.com", "password": "password12"})
    amina_headers = auth_header(amina_auth.json()["access_token"])
    john_headers = auth_header(john_auth.json()["access_token"])
    phone_a = "phone-amina-device-1"
    phone_b = "phone-john-device-1"

    first = await client.post("/attendance/clock-in", headers=amina_headers, json={"device_id": phone_a})
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "PRESENT"
    work_on = first.json()["work_on"]
    again = await client.post("/attendance/clock-in", headers=amina_headers, json={"device_id": phone_a})
    assert again.status_code == 400

    other_phone = await client.post("/attendance/clock-in", headers=amina_headers, json={"device_id": "phone-stolen-99"})
    assert other_phone.status_code == 403

    buddy = await client.post("/attendance/clock-in", headers=john_headers, json={"device_id": phone_a})
    assert buddy.status_code == 403

    john_ok = await client.post("/attendance/clock-in", headers=john_headers, json={"device_id": phone_b})
    assert john_ok.status_code == 200, john_ok.text
    bound = await client.post("/attendance/clock-in", headers=john_headers, json={"device_id": "phone-john-other"})
    assert bound.status_code == 403

    reset = await client.post(f"/employees/{john['id']}/clock-device/reset", headers=headers_a)
    assert reset.status_code == 200
    assert reset.json()["has_clock_device"] is False
    john_out = await client.post("/attendance/clock-out", headers=john_headers, json={"device_id": phone_b})
    assert john_out.status_code == 200

    roster = await client.get(
        "/attendance",
        headers=headers_a,
        params={"company_id": company_a, "branch_id": branch_a, "work_on": work_on},
    )
    assert roster.status_code == 200, roster.text
    by_id = {row["employee_id"]: row for row in roster.json()}
    assert by_id[amina["id"]]["status"] == "PRESENT"
    assert by_id[john["id"]]["checked_out_at"] is not None

    stolen = await client.get(
        "/attendance",
        headers=headers_b,
        params={"company_id": company_a, "branch_id": branch_a, "work_on": work_on},
    )
    assert stolen.status_code in {403, 404}

    marked = await client.put(
        "/attendance",
        headers=headers_a,
        json={"employee_id": john["id"], "work_on": work_on, "status": "ABSENT"},
    )
    assert marked.status_code == 200
    assert marked.json()["status"] == "ABSENT"
    assert marked.json()["source"] == "HR"


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_clock_in_blocked_when_on_leave(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant = await _register(
        client,
        email="att-leave@example.com",
        tenant_name="Att Leave",
        company_name="Att Leave Corp",
        country_id=kenya.id,
    )
    headers = auth_header(tenant["access_token"])
    company_id = tenant["company"]["id"]
    branch_id = tenant["branch"]["id"]
    person = await _person(client, headers, company_id, branch_id, "Amina", "amina-leave@att.example")
    annual = await _leave_type(client, headers, company_id)
    from datetime import date, timedelta

    today = date.today()
    leave = await client.post(
        "/leave-requests/hr",
        headers=headers,
        json={
            "employee_id": person["id"],
            "leave_type_id": annual["id"],
            "start_on": (today - timedelta(days=1)).isoformat(),
            "end_on": (today + timedelta(days=1)).isoformat(),
            "hr_action": "APPROVE_NOW",
        },
    )
    assert leave.status_code == 201, leave.text
    await client.post(
        f"/employees/{person['id']}/login",
        headers=headers,
        json={"email": "amina.leave.clock@example.com", "password": "password12"},
    )
    auth = await client.post("/auth/login", json={"email": "amina.leave.clock@example.com", "password": "password12"})
    clock = await client.post(
        "/attendance/clock-in",
        headers=auth_header(auth.json()["access_token"]),
        json={"device_id": "phone-leave-device"},
    )
    assert clock.status_code == 400
    roster = await client.get(
        "/attendance",
        headers=headers,
        params={"company_id": company_id, "branch_id": branch_id, "work_on": today.isoformat()},
    )
    row = next(item for item in roster.json() if item["employee_id"] == person["id"])
    assert row["status"] == "ON_LEAVE"
    assert row["on_leave"] is True
