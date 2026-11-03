import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text

from app.db.seed_demo import (
    DEMO_OWNER_EMAIL,
    DEMO_PASSWORD,
    EXTRA_STAFF,
    SECOND_OWNER_EMAIL,
    seed_demo,
)
from app.db.session import get_session_maker
from app.models import Branch, Company, Employee, Tenant
from tests.conftest import auth_header


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_seed_demo_creates_isolated_multi_company_staff(client: AsyncClient) -> None:
    maker = get_session_maker()
    async with maker() as session:
        first = await seed_demo(session)
        await session.commit()
        assert first["created"] is True
        assert first["added"] == len(EXTRA_STAFF)
        second = await seed_demo(session)
        await session.commit()
        assert second["created"] is False
        assert second["added"] == 0
        await session.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        tenant_count = await session.scalar(select(func.count()).select_from(Tenant))
        company_count = await session.scalar(select(func.count()).select_from(Company))
        branch_count = await session.scalar(select(func.count()).select_from(Branch))
        employee_count = await session.scalar(select(func.count()).select_from(Employee))
        assert tenant_count == 2
        assert company_count == 4
        assert branch_count == 8
        assert employee_count == 36

    login = await client.post(
        "/auth/login",
        json={"email": DEMO_OWNER_EMAIL, "password": DEMO_PASSWORD},
    )
    assert login.status_code == 200, login.text
    headers = auth_header(login.json()["access_token"])
    companies = await client.get("/companies", headers=headers)
    assert companies.status_code == 200, companies.text
    names = {row["name"] for row in companies.json()}
    assert names == {
        "Rift Valley Trading Ltd",
        "Nile Logistics Ltd",
        "Coastal Packers Ltd",
    }
    branches = await client.get("/branches", headers=headers)
    assert branches.status_code == 200, branches.text
    assert len(branches.json()) == 6
    cities = {row["city"] for row in branches.json()}
    assert {"Nairobi", "Mombasa", "Kampala", "Jinja", "Dar es Salaam", "Arusha"} <= cities
    people = await client.get("/employees", headers=headers)
    assert people.status_code == 200, people.text
    assert len(people.json()) == 31
    kenya_staff = [row for row in people.json() if (row.get("nssf_no") or "").startswith("NSSF-KE-")]
    uganda_staff = [row for row in people.json() if (row.get("nssf_no") or "").startswith("NSSF-UG-")]
    tanzania_staff = [row for row in people.json() if (row.get("nssf_no") or "").startswith("NSSF-TZ-")]
    assert len(kenya_staff) == 13
    assert len(uganda_staff) == 10
    assert len(tanzania_staff) == 7

    rift = next(row for row in companies.json() if "Rift" in row["name"])
    nile = next(row for row in companies.json() if "Nile" in row["name"])
    rift_people = await client.get("/employees", headers=headers, params={"company_id": rift["id"]})
    nile_people = await client.get("/employees", headers=headers, params={"company_id": nile["id"]})
    assert len(rift_people.json()) == 14
    assert len(nile_people.json()) == 10
    samuel = next(row for row in rift_people.json() if row["first_name"] == "Samuel")
    bosses = await client.get(f"/employees/{samuel['id']}/supervisors", headers=headers)
    assert bosses.status_code == 200, bosses.text
    assert [row["first_name"] for row in bosses.json()] == ["John"]
    paid = next(row for row in rift_people.json() if row["first_name"] == "Amina")
    salary = await client.get(f"/employees/{paid['id']}/compensation", headers=headers)
    assert salary.status_code == 200, salary.text
    assert salary.json()[0]["structure"] == "GROSS_ONLY"

    hr = await client.post(
        "/auth/login",
        json={"email": "hr@riftvalley.example", "password": DEMO_PASSWORD},
    )
    assert hr.status_code == 200, hr.text
    assert hr.json()["user"]["role"] == "HR"

    acme = await client.post(
        "/auth/login",
        json={"email": SECOND_OWNER_EMAIL, "password": DEMO_PASSWORD},
    )
    assert acme.status_code == 200, acme.text
    acme_headers = auth_header(acme.json()["access_token"])
    acme_companies = await client.get("/companies", headers=acme_headers)
    assert {row["name"] for row in acme_companies.json()} == {"Acme Coffee Ltd"}
    acme_people = await client.get("/employees", headers=acme_headers)
    assert len(acme_people.json()) == 5
    hidden = await client.get(f"/employees/{paid['id']}", headers=acme_headers)
    assert hidden.status_code in {403, 404}
