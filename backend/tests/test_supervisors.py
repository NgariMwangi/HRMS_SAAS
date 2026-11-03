import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_tenancy import _kenya, _register


async def _person(
    client: AsyncClient,
    headers: dict[str, str],
    company_id: str,
    branch_id: str,
    first: str,
    email: str,
) -> dict:
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


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_supervisors_are_optional_fellow_employees(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="sup-a@example.com",
        tenant_name="Sup A",
        company_name="Sup A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="sup-b@example.com",
        tenant_name="Sup B",
        company_name="Sup B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    headers_b = auth_header(tenant_b["access_token"])
    company_a = tenant_a["company"]["id"]
    branch_a = tenant_a["branch"]["id"]
    company_b = tenant_b["company"]["id"]
    branch_b = tenant_b["branch"]["id"]

    report = await _person(client, headers_a, company_a, branch_a, "Amina", "amina@a.example")
    lead = await _person(client, headers_a, company_a, branch_a, "Kesi", "kesi@a.example")
    other = await _person(client, headers_a, company_a, branch_a, "Wanjiku", "wanjiku@a.example")
    outsider = await _person(client, headers_b, company_b, branch_b, "Bev", "bev@b.example")

    empty = await client.get(f"/employees/{report['id']}/supervisors", headers=headers_a)
    assert empty.status_code == 200
    assert empty.json() == []

    self_assign = await client.put(
        f"/employees/{report['id']}/supervisors",
        headers=headers_a,
        json={"supervisor_ids": [report["id"]]},
    )
    assert self_assign.status_code == 400

    stolen = await client.put(
        f"/employees/{report['id']}/supervisors",
        headers=headers_a,
        json={"supervisor_ids": [outsider["id"]]},
    )
    assert stolen.status_code == 400

    saved = await client.put(
        f"/employees/{report['id']}/supervisors",
        headers=headers_a,
        json={"supervisor_ids": [lead["id"], other["id"], lead["id"]]},
    )
    assert saved.status_code == 200, saved.text
    names = [row["first_name"] for row in saved.json()]
    assert names == ["Kesi", "Wanjiku"]
    assert saved.json()[0]["employee_number"] == lead["employee_number"]

    listed = await client.get(f"/employees/{report['id']}/supervisors", headers=headers_a)
    assert [row["id"] for row in listed.json()] == [lead["id"], other["id"]]

    hidden = await client.get(f"/employees/{report['id']}/supervisors", headers=headers_b)
    assert hidden.status_code in {403, 404}

    created = await client.post(
        "/employees",
        headers=headers_a,
        json={
            "company_id": company_a,
            "branch_id": branch_a,
            "first_name": "Imani",
            "last_name": "Odhiambo",
            "email": "imani@a.example",
            "supervisor_ids": [lead["id"]],
        },
    )
    assert created.status_code == 201, created.text
    assigned = await client.get(f"/employees/{created.json()['id']}/supervisors", headers=headers_a)
    assert [row["id"] for row in assigned.json()] == [lead["id"]]

    cleared = await client.patch(
        f"/employees/{report['id']}",
        headers=headers_a,
        json={"supervisor_ids": []},
    )
    assert cleared.status_code == 200, cleared.text
    after = await client.get(f"/employees/{report['id']}/supervisors", headers=headers_a)
    assert after.json() == []
