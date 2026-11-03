import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_tenancy import _kenya, _register


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_departments_and_job_titles_are_isolated_per_company(
    client: AsyncClient,
) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="dept-a@example.com",
        tenant_name="Tenant A",
        company_name="A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="dept-b@example.com",
        tenant_name="Tenant B",
        company_name="B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    company_a = tenant_a["company"]["id"]
    company_b = tenant_b["company"]["id"]

    created = await client.post(
        "/departments",
        headers=headers_a,
        json={"company_id": company_a, "name": "Finance", "code": "FIN"},
    )
    assert created.status_code == 201, created.text
    finance = created.json()

    title = await client.post(
        "/job-titles",
        headers=headers_a,
        json={
            "company_id": company_a,
            "department_id": finance["id"],
            "name": "Accountant",
            "code": "ACC",
        },
    )
    assert title.status_code == 201, title.text
    assert title.json()["department_id"] == finance["id"]

    listed = await client.get(
        "/departments",
        headers=headers_a,
        params={"company_id": company_a},
    )
    assert listed.status_code == 200
    assert {row["name"] for row in listed.json()} == {"Finance"}

    foreign_company = await client.post(
        "/departments",
        headers=headers_a,
        json={"company_id": company_b, "name": "Should Fail"},
    )
    assert foreign_company.status_code == 403

    foreign_list = await client.get(
        "/departments",
        headers=auth_header(tenant_b["access_token"]),
    )
    assert foreign_list.status_code == 200
    assert foreign_list.json() == []

    stolen = await client.get(
        f"/departments/{finance['id']}",
        headers=auth_header(tenant_b["access_token"]),
    )
    assert stolen.status_code in {403, 404}

    patched = await client.patch(
        f"/job-titles/{title.json()['id']}",
        headers=headers_a,
        json={"name": "Senior Accountant"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Senior Accountant"

    wrong_dept = await client.post(
        "/job-titles",
        headers=headers_a,
        json={
            "company_id": company_a,
            "department_id": "00000000-0000-0000-0000-000000000001",
            "name": "Ghost Role",
        },
    )
    assert wrong_dept.status_code == 400
