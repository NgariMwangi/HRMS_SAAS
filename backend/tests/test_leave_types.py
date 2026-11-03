import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_platform import _admin_login
from tests.test_tenancy import _kenya, _register


def _days(value: object) -> float:
    return float(value)


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_company_leave_types_are_isolated_and_editable(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="leave-a@example.com",
        tenant_name="Leave A",
        company_name="Leave A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="leave-b@example.com",
        tenant_name="Leave B",
        company_name="Leave B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    headers_b = auth_header(tenant_b["access_token"])
    company_a = tenant_a["company"]["id"]
    company_b = tenant_b["company"]["id"]

    empty = await client.get("/leave-types", headers=headers_a, params={"company_id": company_a})
    assert empty.status_code == 200, empty.text
    assert empty.json() == []

    annual = await client.post(
        "/leave-types",
        headers=headers_a,
        json={
            "company_id": company_a,
            "name": "Annual leave",
            "days": 21,
            "accrued": True,
            "day_basis": "WORKING",
        },
    )
    assert annual.status_code == 201, annual.text
    annual_body = annual.json()
    assert annual_body["name"] == "Annual leave"
    assert _days(annual_body["days"]) == 21
    assert annual_body["accrued"] is True
    assert _days(annual_body["accrual_per_month"]) == 1.75
    assert annual_body["day_basis"] == "WORKING"

    monthly = await client.post(
        "/leave-types",
        headers=headers_a,
        json={
            "company_id": company_a,
            "name": "Custom accrue",
            "accrued": True,
            "accrual_per_month": 1.75,
            "day_basis": "WORKING",
        },
    )
    assert monthly.status_code == 201, monthly.text
    assert _days(monthly.json()["accrual_per_month"]) == 1.75
    assert _days(monthly.json()["days"]) == 21
    removed_monthly = await client.delete(f"/leave-types/{monthly.json()['id']}", headers=headers_a)
    assert removed_monthly.status_code == 204

    sick = await client.post(
        "/leave-types",
        headers=headers_a,
        json={
            "company_id": company_a,
            "name": "Sick leave",
            "days": 7,
            "accrued": False,
            "day_basis": "CALENDAR",
        },
    )
    assert sick.status_code == 201, sick.text
    assert sick.json()["accrued"] is False
    assert sick.json()["day_basis"] == "CALENDAR"

    listed = await client.get("/leave-types", headers=headers_a, params={"company_id": company_a})
    assert listed.status_code == 200
    names = [row["name"] for row in listed.json()]
    assert names == ["Annual leave", "Sick leave"]

    duplicate = await client.post(
        "/leave-types",
        headers=headers_a,
        json={"company_id": company_a, "name": "Annual leave", "days": 10},
    )
    assert duplicate.status_code == 409

    bad_basis = await client.post(
        "/leave-types",
        headers=headers_a,
        json={
            "company_id": company_a,
            "name": "Compassionate",
            "day_basis": "BUSINESS",
        },
    )
    assert bad_basis.status_code == 400

    negative = await client.post(
        "/leave-types",
        headers=headers_a,
        json={"company_id": company_a, "name": "Negative", "days": -1},
    )
    assert negative.status_code == 422

    stolen_create = await client.post(
        "/leave-types",
        headers=headers_a,
        json={"company_id": company_b, "name": "Stolen"},
    )
    assert stolen_create.status_code == 403

    stolen_list = await client.get(
        "/leave-types",
        headers=headers_b,
        params={"company_id": company_a},
    )
    assert stolen_list.status_code == 403

    other_list = await client.get("/leave-types", headers=headers_b, params={"company_id": company_b})
    assert other_list.status_code == 200
    assert other_list.json() == []

    patched = await client.patch(
        f"/leave-types/{annual_body['id']}",
        headers=headers_a,
        json={"days": 24.5, "accrued": False, "day_basis": "CALENDAR"},
    )
    assert patched.status_code == 200, patched.text
    assert _days(patched.json()["days"]) == 24.5
    assert patched.json()["accrued"] is False
    assert patched.json()["day_basis"] == "CALENDAR"

    stolen_patch = await client.patch(
        f"/leave-types/{annual_body['id']}",
        headers=headers_b,
        json={"name": "Hijacked"},
    )
    assert stolen_patch.status_code in {403, 404}

    removed = await client.delete(f"/leave-types/{sick.json()['id']}", headers=headers_a)
    assert removed.status_code == 204
    leftover = await client.get("/leave-types", headers=headers_a, params={"company_id": company_a})
    assert [row["name"] for row in leftover.json()] == ["Annual leave"]

    second = await client.post(
        "/companies",
        headers=headers_a,
        json={"name": "Leave A West"},
    )
    assert second.status_code == 201, second.text
    west_id = second.json()["id"]
    west = await client.post(
        "/leave-types",
        headers=headers_a,
        json={
            "company_id": west_id,
            "name": "Annual leave",
            "days": 18,
            "accrued": True,
            "day_basis": "WORKING",
        },
    )
    assert west.status_code == 201, west.text
    west_list = await client.get("/leave-types", headers=headers_a, params={"company_id": west_id})
    assert [row["name"] for row in west_list.json()] == ["Annual leave"]
    east_list = await client.get("/leave-types", headers=headers_a, params={"company_id": company_a})
    assert _days(east_list.json()[0]["days"]) == 24.5

    admin = await _admin_login(client)
    platform = await client.post(
        f"/platform/tenants/{tenant_a['tenant']['id']}/leave-types",
        headers=admin,
        json={
            "company_id": company_a,
            "name": "Maternity",
            "days": 90,
            "accrued": False,
            "day_basis": "CALENDAR",
        },
    )
    assert platform.status_code == 201, platform.text
    workspace = await client.get(
        f"/platform/tenants/{tenant_a['tenant']['id']}/workspace",
        headers=admin,
    )
    assert workspace.status_code == 200, workspace.text
    workspace_names = {row["name"] for row in workspace.json()["leave_types"]}
    assert workspace_names == {"Annual leave", "Maternity"}
    other_workspace = await client.get(
        f"/platform/tenants/{tenant_b['tenant']['id']}/workspace",
        headers=admin,
    )
    assert other_workspace.json()["leave_types"] == []
