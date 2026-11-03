import base64

import pytest
from httpx import AsyncClient

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

from tests.conftest import auth_header
from tests.test_tenancy import _kenya, _register


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_employees_are_isolated_per_company(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="people-a@example.com",
        tenant_name="Tenant A",
        company_name="A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="people-b@example.com",
        tenant_name="Tenant B",
        company_name="B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    company_a = tenant_a["company"]["id"]
    branch_a = tenant_a["branch"]["id"]

    created = await client.post(
        "/employees",
        headers=headers_a,
        json={
            "company_id": company_a,
            "branch_id": branch_a,
            "first_name": "Amina",
            "other_names": "Wanjiku",
            "last_name": "Otieno",
            "email": "amina@a-corp.example",
            "personal_email": "amina.personal@example.com",
            "phone": "+254700000000",
            "other_phone": "+254711000000",
            "id_number": "12345678",
            "nssf_no": "NSSF-001",
            "shif_no": "SHIF-001",
            "employment_type": "FULL_TIME",
        },
    )
    assert created.status_code == 201, created.text
    employee = created.json()
    assert employee["employee_number"].startswith("EMP-")
    assert employee["company_id"] == company_a
    assert employee["employment_type"] == "FULL_TIME"
    assert employee["other_names"] == "Wanjiku"
    assert employee["personal_email"] == "amina.personal@example.com"
    assert employee["other_phone"] == "+254711000000"
    assert employee["id_number"] == "12345678"
    assert employee["nssf_no"] == "NSSF-001"
    assert employee["shif_no"] == "SHIF-001"

    duplicate_ids = await client.post(
        "/employees",
        headers=headers_a,
        json={
            "company_id": company_a,
            "branch_id": branch_a,
            "first_name": "Jane",
            "last_name": "Doe",
            "id_number": "12345678",
        },
    )
    assert duplicate_ids.status_code == 409

    listed = await client.get(
        "/employees",
        headers=headers_a,
        params={"company_id": company_a},
    )
    assert listed.status_code == 200
    assert {row["email"] for row in listed.json()} == {"amina@a-corp.example"}

    foreign_create = await client.post(
        "/employees",
        headers=headers_a,
        json={
            "company_id": tenant_b["company"]["id"],
            "branch_id": tenant_b["branch"]["id"],
            "first_name": "Nope",
            "last_name": "Nope",
        },
    )
    assert foreign_create.status_code == 403

    foreign_list = await client.get(
        "/employees",
        headers=auth_header(tenant_b["access_token"]),
    )
    assert foreign_list.status_code == 200
    assert foreign_list.json() == []

    stolen = await client.get(
        f"/employees/{employee['id']}",
        headers=auth_header(tenant_b["access_token"]),
    )
    assert stolen.status_code in {403, 404}

    patched = await client.patch(
        f"/employees/{employee['id']}",
        headers=headers_a,
        json={"phone": "+254700000111", "status": "INACTIVE"},
    )
    assert patched.status_code == 200
    assert patched.json()["phone"] == "+254700000111"
    assert patched.json()["status"] == "ACTIVE"

    wrong_branch = await client.post(
        "/employees",
        headers=headers_a,
        json={
            "company_id": company_a,
            "branch_id": tenant_b["branch"]["id"],
            "first_name": "Wrong",
            "last_name": "Branch",
        },
    )
    assert wrong_branch.status_code == 400

    period = await client.post(
        "/employees",
        headers=headers_a,
        json={
            "company_id": company_a,
            "branch_id": branch_a,
            "first_name": "Brian",
            "last_name": "Mwangi",
            "employment_type": "PROBATION",
            "date_joined": "2026-01-01",
            "date_ended": "2026-03-31",
        },
    )
    assert period.status_code == 201, period.text
    assert period.json()["employment_type"] == "PROBATION"
    assert period.json()["date_ended"] == "2026-03-31"

    missing_end = await client.post(
        "/employees",
        headers=headers_a,
        json={
            "company_id": company_a,
            "branch_id": branch_a,
            "first_name": "Cate",
            "last_name": "Njeri",
            "employment_type": "INTERN",
            "date_joined": "2026-02-01",
        },
    )
    assert missing_end.status_code == 400

    open_contract = await client.post(
        "/employees",
        headers=headers_a,
        json={
            "company_id": company_a,
            "branch_id": branch_a,
            "first_name": "David",
            "last_name": "Otieno",
            "employment_type": "CONTRACT",
            "date_joined": "2026-02-01",
        },
    )
    assert open_contract.status_code == 201, open_contract.text
    assert open_contract.json()["date_ended"] is None

    fixed_contract = await client.post(
        "/employees",
        headers=headers_a,
        json={
            "company_id": company_a,
            "branch_id": branch_a,
            "first_name": "Eva",
            "last_name": "Achieng",
            "employment_type": "CONTRACT",
            "date_joined": "2026-02-01",
            "date_ended": "2026-12-31",
        },
    )
    assert fixed_contract.status_code == 201, fixed_contract.text
    assert fixed_contract.json()["date_ended"] == "2026-12-31"

    uploaded = await client.put(
        f"/employees/{employee['id']}/photo",
        headers=headers_a,
        files={"file": ("passport.png", TINY_PNG, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["has_photo"] is True

    photo = await client.get(f"/employees/{employee['id']}/photo", headers=headers_a)
    assert photo.status_code == 200
    assert photo.headers["content-type"] == "image/png"
    assert photo.content == TINY_PNG

    stolen_photo = await client.get(
        f"/employees/{employee['id']}/photo",
        headers=auth_header(tenant_b["access_token"]),
    )
    assert stolen_photo.status_code in {403, 404}

    removed = await client.delete(f"/employees/{employee['id']}/photo", headers=headers_a)
    assert removed.status_code == 204
    gone = await client.get(f"/employees/{employee['id']}/photo", headers=headers_a)
    assert gone.status_code == 404
    assert (await client.get(f"/employees/{employee['id']}", headers=headers_a)).json()["has_photo"] is False
