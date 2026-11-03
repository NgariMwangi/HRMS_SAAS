import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_platform import _admin_login, _register


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_platform_admin_manages_tenant_data_and_stays_isolated(
    client: AsyncClient,
) -> None:
    countries = await client.get("/countries")
    kenya_id = next(row["id"] for row in countries.json() if row["code"] == "KE")
    tenant_a = await _register(client, "ada@example.com", kenya_id)
    tenant_b = await _register(client, "bev@example.com", kenya_id)
    tenant_a_id = tenant_a["tenant"]["id"]
    tenant_b_id = tenant_b["tenant"]["id"]
    company_a_id = tenant_a["company"]["id"]
    company_b_id = tenant_b["company"]["id"]
    branch_a_id = tenant_a["branch"]["id"]

    tenant_headers = auth_header(tenant_a["access_token"])
    blocked = await client.get(
        f"/platform/tenants/{tenant_a_id}/workspace",
        headers=tenant_headers,
    )
    assert blocked.status_code == 403

    admin = await _admin_login(client)
    workspace = await client.get(
        f"/platform/tenants/{tenant_a_id}/workspace",
        headers=admin,
    )
    assert workspace.status_code == 200, workspace.text
    body = workspace.json()
    assert body["tenant"]["id"] == tenant_a_id
    assert {row["id"] for row in body["companies"]} == {company_a_id}
    assert body["leave_types"] == []
    assert all(row["company_id"] != company_b_id for row in body["employees"])

    company = await client.post(
        f"/platform/tenants/{tenant_a_id}/companies",
        headers=admin,
        json={"name": "Ada Logistics"},
    )
    assert company.status_code == 201, company.text
    new_company_id = company.json()["id"]

    other_company = await client.post(
        f"/platform/tenants/{tenant_a_id}/branches",
        headers=admin,
        json={
            "company_id": company_b_id,
            "country_id": kenya_id,
            "name": "Stolen",
            "code": "XX",
        },
    )
    assert other_company.status_code == 403

    branch = await client.post(
        f"/platform/tenants/{tenant_a_id}/branches",
        headers=admin,
        json={
            "company_id": new_company_id,
            "country_id": kenya_id,
            "name": "Mombasa",
            "code": "MBA",
        },
    )
    assert branch.status_code == 201, branch.text
    new_branch_id = branch.json()["id"]
    assert branch.json()["timezone"] == "Africa/Nairobi"

    department = await client.post(
        f"/platform/tenants/{tenant_a_id}/departments",
        headers=admin,
        json={"company_id": new_company_id, "name": "Operations", "code": "OPS"},
    )
    assert department.status_code == 201, department.text

    title = await client.post(
        f"/platform/tenants/{tenant_a_id}/job-titles",
        headers=admin,
        json={
            "company_id": new_company_id,
            "department_id": department.json()["id"],
            "name": "Driver",
        },
    )
    assert title.status_code == 201, title.text

    employee = await client.post(
        f"/platform/tenants/{tenant_a_id}/employees",
        headers=admin,
        json={
            "company_id": new_company_id,
            "branch_id": new_branch_id,
            "department_id": department.json()["id"],
            "job_title_id": title.json()["id"],
            "first_name": "Kesi",
            "last_name": "Otieno",
            "email": "kesi@example.com",
            "employment_type": "FULL_TIME",
        },
    )
    assert employee.status_code == 201, employee.text
    employee_id = employee.json()["id"]
    assert employee.json()["employee_number"] == "EMP-0001"

    viewed = await client.get(
        f"/platform/tenants/{tenant_a_id}/employees/{employee_id}",
        headers=admin,
    )
    assert viewed.status_code == 200, viewed.text
    assert viewed.json()["first_name"] == "Kesi"
    assert viewed.json()["personal_email"] is None

    hidden = await client.get(
        f"/platform/tenants/{tenant_b_id}/employees/{employee_id}",
        headers=admin,
    )
    assert hidden.status_code == 403

    renamed = await client.patch(
        f"/platform/tenants/{tenant_a_id}/employees/{employee_id}",
        headers=admin,
        json={"other_names": "Achieng"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["other_names"] == "Achieng"

    user = await client.post(
        f"/platform/tenants/{tenant_a_id}/users",
        headers=admin,
        json={
            "full_name": "HR Lead",
            "email": "hr@example.com",
            "password": "password12",
            "role": "HR",
        },
    )
    assert user.status_code == 201, user.text

    deleted = await client.delete(
        f"/platform/tenants/{tenant_a_id}/employees/{employee_id}",
        headers=admin,
    )
    assert deleted.status_code == 204

    leftover = await client.get(
        f"/platform/tenants/{tenant_a_id}/workspace",
        headers=admin,
    )
    assert leftover.status_code == 200
    assert leftover.json()["employees"] == []

    remove_company = await client.delete(
        f"/platform/tenants/{tenant_a_id}/companies/{new_company_id}",
        headers=admin,
    )
    assert remove_company.status_code == 204

    after = await client.get(
        f"/platform/tenants/{tenant_a_id}/workspace",
        headers=admin,
    )
    assert {row["id"] for row in after.json()["companies"]} == {company_a_id}
    assert {row["id"] for row in after.json()["branches"]} == {branch_a_id}

    other = await client.get(
        f"/platform/tenants/{tenant_b_id}/workspace",
        headers=admin,
    )
    assert other.status_code == 200
    assert {row["id"] for row in other.json()["companies"]} == {company_b_id}
