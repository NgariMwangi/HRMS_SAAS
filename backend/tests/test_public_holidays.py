import pytest
from httpx import AsyncClient

from app.services.holidays import annual_holiday_names, one_off_holiday_names
from tests.conftest import auth_header
from tests.test_leave_requests import _leave_type, _person
from tests.test_tenancy import _kenya, _register, _uganda

KENYA_ANNUAL = annual_holiday_names("KE")
KENYA_ONE_OFF = one_off_holiday_names("KE")
KENYA_SEEDED = KENYA_ANNUAL | KENYA_ONE_OFF


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_kenya_branch_receives_annual_holidays(client: AsyncClient) -> None:
    kenya = await _kenya()
    uganda = await _uganda()
    tenant = await _register(
        client,
        email="ke-hol@example.com",
        tenant_name="Ke Hol",
        company_name="Ke Hol Corp",
        country_id=kenya.id,
    )
    headers = auth_header(tenant["access_token"])
    company_id = tenant["company"]["id"]
    kenya_branch = tenant["branch"]["id"]

    seeded = await client.get("/public-holidays", headers=headers, params={"company_id": company_id})
    assert seeded.status_code == 200, seeded.text
    assert {row["name"] for row in seeded.json()} == KENYA_SEEDED
    assert {row["name"] for row in seeded.json() if row["kind"] == "ONCE"} == KENYA_ONE_OFF
    assert all(row["country_id"] == str(kenya.id) for row in seeded.json())

    second = await client.post(
        "/branches",
        headers=headers,
        json={"company_id": company_id, "country_id": str(kenya.id), "name": "Mombasa", "code": "MBA"},
    )
    assert second.status_code == 201, second.text
    again = await client.get("/public-holidays", headers=headers, params={"company_id": company_id})
    assert {row["name"] for row in again.json()} == KENYA_SEEDED

    kampala = await client.post(
        "/branches",
        headers=headers,
        json={"company_id": company_id, "country_id": str(uganda.id), "name": "Kampala", "code": "KLA"},
    )
    assert kampala.status_code == 201, kampala.text
    uganda_list = await client.get(
        "/public-holidays",
        headers=headers,
        params={"company_id": company_id, "branch_id": kampala.json()["id"]},
    )
    assert uganda_list.status_code == 200, uganda_list.text
    assert uganda_list.json() == []

    kenya_list = await client.get(
        "/public-holidays",
        headers=headers,
        params={"company_id": company_id, "branch_id": kenya_branch},
    )
    assert {row["name"] for row in kenya_list.json()} == KENYA_SEEDED

    kenya_person = await _person(client, headers, company_id, kenya_branch, "Amina", "amina@kehol.example")
    uganda_person = await _person(client, headers, company_id, kampala.json()["id"], "Brian", "brian@kehol.example")
    annual = await _leave_type(client, headers, company_id)

    kenya_leave = await client.post(
        "/leave-requests/hr",
        headers=headers,
        json={
            "employee_id": kenya_person["id"],
            "leave_type_id": annual["id"],
            "start_on": "2026-06-01",
            "end_on": "2026-06-05",
            "hr_action": "APPROVE_NOW",
        },
    )
    assert kenya_leave.status_code == 201, kenya_leave.text
    assert float(kenya_leave.json()["days"]) == 4

    uganda_leave = await client.post(
        "/leave-requests/hr",
        headers=headers,
        json={
            "employee_id": uganda_person["id"],
            "leave_type_id": annual["id"],
            "start_on": "2026-07-06",
            "end_on": "2026-07-10",
            "hr_action": "APPROVE_NOW",
        },
    )
    assert uganda_leave.status_code == 201, uganda_leave.text
    assert float(uganda_leave.json()["days"]) == 5


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_public_holidays_yearly_once_and_working_days(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="hol-a@example.com",
        tenant_name="Hol A",
        company_name="Hol A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="hol-b@example.com",
        tenant_name="Hol B",
        company_name="Hol B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    headers_b = auth_header(tenant_b["access_token"])
    company_a = tenant_a["company"]["id"]
    branch_a = tenant_a["branch"]["id"]

    seeded = await client.get("/public-holidays", headers=headers_a, params={"company_id": company_a})
    assert {row["name"] for row in seeded.json()} == KENYA_SEEDED
    jamhuri = next(row for row in seeded.json() if row["name"] == "Jamhuri Day")

    funeral = await client.post(
        "/public-holidays",
        headers=headers_a,
        json={
            "company_id": company_a,
            "branch_id": branch_a,
            "name": "State funeral",
            "kind": "ONCE",
            "observed_on": "2026-06-03",
        },
    )
    assert funeral.status_code == 201, funeral.text
    assert funeral.json()["kind"] == "ONCE"
    assert funeral.json()["observed_on"] == "2026-06-03"
    assert funeral.json()["country_id"] == str(kenya.id)

    listed = await client.get("/public-holidays", headers=headers_a, params={"company_id": company_a})
    assert {row["name"] for row in listed.json()} == KENYA_SEEDED | {"State funeral"}

    other = await client.get("/public-holidays", headers=headers_b, params={"company_id": tenant_b["company"]["id"]})
    assert other.status_code == 200
    assert {row["name"] for row in other.json()} == KENYA_SEEDED

    stolen = await client.get("/public-holidays", headers=headers_b, params={"company_id": company_a})
    assert stolen.status_code in {403, 404}

    duplicate = await client.post(
        "/public-holidays",
        headers=headers_a,
        json={"company_id": company_a, "name": "Another Jamhuri", "kind": "YEARLY", "month": 12, "day": 12},
    )
    assert duplicate.status_code == 409

    person = await _person(client, headers_a, company_a, branch_a, "Amina", "amina@hol.example")
    annual = await _leave_type(client, headers_a, company_a)
    leave = await client.post(
        "/leave-requests/hr",
        headers=headers_a,
        json={
            "employee_id": person["id"],
            "leave_type_id": annual["id"],
            "start_on": "2026-06-01",
            "end_on": "2026-06-05",
            "hr_action": "APPROVE_NOW",
        },
    )
    assert leave.status_code == 201, leave.text
    assert float(leave.json()["days"]) == 3

    patched = await client.patch(
        f"/public-holidays/{funeral.json()['id']}",
        headers=headers_a,
        json={"name": "National mourning"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "National mourning"

    deleted = await client.delete(f"/public-holidays/{jamhuri['id']}", headers=headers_a)
    assert deleted.status_code == 204
    remaining = await client.get("/public-holidays", headers=headers_a, params={"company_id": company_a})
    names = {row["name"] for row in remaining.json()}
    assert "Jamhuri Day" not in names
    assert "National mourning" in names
    assert names >= (KENYA_ANNUAL - {"Jamhuri Day"})
