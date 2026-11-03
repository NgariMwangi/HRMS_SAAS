import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_tenancy import _kenya, _register


def _person(company_id: str, branch_id: str, first: str = "Amina") -> dict:
    return {
        "company_id": company_id,
        "branch_id": branch_id,
        "first_name": first,
        "last_name": "Otieno",
    }


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_next_of_kin_is_optional_and_isolated(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="kin-a@example.com",
        tenant_name="Kin A",
        company_name="Kin A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="kin-b@example.com",
        tenant_name="Kin B",
        company_name="Kin B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    headers_b = auth_header(tenant_b["access_token"])
    company_a = tenant_a["company"]["id"]
    branch_a = tenant_a["branch"]["id"]

    created = await client.post(
        "/employees",
        headers=headers_a,
        json=_person(company_a, branch_a),
    )
    assert created.status_code == 201, created.text
    employee_id = created.json()["id"]

    empty = await client.get(f"/employees/{employee_id}/next-of-kin", headers=headers_a)
    assert empty.status_code == 200
    assert empty.json() == []

    saved = await client.put(
        f"/employees/{employee_id}/next-of-kin",
        headers=headers_a,
        json={
            "items": [
                {
                    "name": "Mary Otieno",
                    "relationship": "Spouse",
                    "phone": "+254700111111",
                    "other_phone": "+254711111111",
                    "email": "mary@example.com",
                    "address": "Kisumu",
                },
                {
                    "name": "John Otieno",
                    "relationship": "Parent",
                    "phone": "+254700222222",
                },
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    rows = saved.json()
    assert [row["name"] for row in rows] == ["Mary Otieno", "John Otieno"]
    assert rows[0]["relationship"] == "Spouse"
    assert rows[0]["phone"] == "+254700111111"
    assert rows[0]["email"] == "mary@example.com"
    assert rows[1]["other_phone"] is None

    stolen = await client.get(f"/employees/{employee_id}/next-of-kin", headers=headers_b)
    assert stolen.status_code in {403, 404}

    stolen_put = await client.put(
        f"/employees/{employee_id}/next-of-kin",
        headers=headers_b,
        json={"items": [{"name": "Nope", "relationship": "Friend", "phone": "+254700000000"}]},
    )
    assert stolen_put.status_code in {403, 404}

    replaced = await client.put(
        f"/employees/{employee_id}/next-of-kin",
        headers=headers_a,
        json={"items": [{"name": "Grace Otieno", "relationship": "Sibling", "phone": "+254700333333"}]},
    )
    assert replaced.status_code == 200
    assert [row["name"] for row in replaced.json()] == ["Grace Otieno"]

    cleared = await client.put(
        f"/employees/{employee_id}/next-of-kin",
        headers=headers_a,
        json={"items": []},
    )
    assert cleared.status_code == 200
    assert cleared.json() == []

    nested = await client.post(
        "/employees",
        headers=headers_a,
        json={
            **_person(company_a, branch_a, "Brian"),
            "email": "brian@a-corp.example",
            "next_of_kin": [
                {"name": "Ann Mwangi", "relationship": "Parent", "phone": "+254700444444"},
            ],
        },
    )
    assert nested.status_code == 201, nested.text
    listed = await client.get(f"/employees/{nested.json()['id']}/next-of-kin", headers=headers_a)
    assert listed.status_code == 200
    assert [row["name"] for row in listed.json()] == ["Ann Mwangi"]

    patched = await client.patch(
        f"/employees/{nested.json()['id']}",
        headers=headers_a,
        json={"next_of_kin": []},
    )
    assert patched.status_code == 200
    after_patch = await client.get(
        f"/employees/{nested.json()['id']}/next-of-kin",
        headers=headers_a,
    )
    assert after_patch.json() == []
