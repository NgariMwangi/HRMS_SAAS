import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import get_session_maker
from app.models import Country
from tests.conftest import auth_header


@dataclass(frozen=True)
class KenyaRef:
    id: uuid.UUID
    default_currency_id: uuid.UUID
    currency_code: str
    decimal_places: int


async def _country(code: str) -> KenyaRef:
    maker = get_session_maker()
    async with maker() as session:
        country = await session.scalar(
            select(Country)
            .options(selectinload(Country.default_currency))
            .where(Country.code == code)
        )
        assert country is not None
        assert country.default_currency_id is not None
        assert country.default_currency is not None
        return KenyaRef(
            id=country.id,
            default_currency_id=country.default_currency_id,
            currency_code=country.default_currency.code,
            decimal_places=country.default_currency.decimal_places,
        )


async def _kenya() -> KenyaRef:
    return await _country("KE")


async def _uganda() -> KenyaRef:
    return await _country("UG")


async def _register(
    client: AsyncClient,
    *,
    email: str,
    tenant_name: str,
    company_name: str,
    country_id: uuid.UUID,
) -> dict:
    response = await client.post(
        "/auth/register",
        json={
            "owner_full_name": "Ada Owner",
            "email": email,
            "password": "password12",
            "tenant_name": tenant_name,
            "company_name": company_name,
            "country_id": str(country_id),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_create_company_and_branch_inherits_country_defaults(
    client: AsyncClient,
) -> None:
    kenya = await _kenya()
    registered = await _register(
        client,
        email="ada@holdings.example",
        tenant_name="East Africa Holdings",
        company_name="Nairobi Trading Ltd",
        country_id=kenya.id,
    )
    headers = auth_header(registered["access_token"])
    first_company_id = registered["company"]["id"]

    company_resp = await client.post(
        "/companies",
        headers=headers,
        json={"name": "Mombasa Logistics", "legal_name": "Mombasa Logistics Limited"},
    )
    assert company_resp.status_code == 201, company_resp.text
    company = company_resp.json()
    assert company["tenant_id"] == registered["tenant"]["id"]
    assert company["name"] == "Mombasa Logistics"

    branch_resp = await client.post(
        "/branches",
        headers=headers,
        json={
            "company_id": company["id"],
            "country_id": str(kenya.id),
            "name": "Westlands",
            "code": "NBO-WL",
        },
    )
    assert branch_resp.status_code == 201, branch_resp.text
    branch = branch_resp.json()
    assert branch["currency_id"] == str(kenya.default_currency_id)
    assert branch["timezone"] == "Africa/Nairobi"
    assert kenya.currency_code == "KES"
    assert kenya.decimal_places == 2

    listed = await client.get("/companies", headers=headers)
    assert listed.status_code == 200
    names = {row["name"] for row in listed.json()}
    assert names == {"Nairobi Trading Ltd", "Mombasa Logistics"}
    assert first_company_id in {row["id"] for row in listed.json()}

    fetched = await client.get(f"/branches/{branch['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["code"] == "NBO-WL"


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_branch_create_rejects_cross_tenant_company_id(
    client: AsyncClient,
) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="a@example.com",
        tenant_name="Tenant A",
        company_name="A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="b@example.com",
        tenant_name="Tenant B",
        company_name="B Corp",
        country_id=kenya.id,
    )

    response = await client.post(
        "/branches",
        headers=auth_header(tenant_a["access_token"]),
        json={
            "company_id": tenant_b["company"]["id"],
            "country_id": str(kenya.id),
            "name": "Should Fail",
            "code": "X-TENANT",
        },
    )
    assert response.status_code == 403
    assert "company_id" in response.json()["detail"]


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_list_companies_is_isolated_per_tenant(
    client: AsyncClient,
) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="iso-a@example.com",
        tenant_name="Tenant A",
        company_name="A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="iso-b@example.com",
        tenant_name="Tenant B",
        company_name="B Corp",
        country_id=kenya.id,
    )

    listed_a = await client.get("/companies", headers=auth_header(tenant_a["access_token"]))
    listed_b = await client.get("/companies", headers=auth_header(tenant_b["access_token"]))
    assert listed_a.status_code == 200
    assert listed_b.status_code == 200
    names_a = {row["name"] for row in listed_a.json()}
    names_b = {row["name"] for row in listed_b.json()}
    assert names_a == {"A Corp"}
    assert names_b == {"B Corp"}
    assert tenant_b["company"]["id"] not in {row["id"] for row in listed_a.json()}

    foreign_company = await client.get(
        f"/companies/{tenant_b['company']['id']}",
        headers=auth_header(tenant_a["access_token"]),
    )
    assert foreign_company.status_code == 404

    branches_a = await client.get("/branches", headers=auth_header(tenant_a["access_token"]))
    branches_b = await client.get("/branches", headers=auth_header(tenant_b["access_token"]))
    assert branches_a.status_code == 200
    assert branches_b.status_code == 200
    ids_a = {row["id"] for row in branches_a.json()}
    ids_b = {row["id"] for row in branches_b.json()}
    assert tenant_a["branch"]["id"] in ids_a
    assert tenant_b["branch"]["id"] in ids_b
    assert tenant_b["branch"]["id"] not in ids_a
    assert tenant_a["branch"]["id"] not in ids_b

    foreign_branch = await client.get(
        f"/branches/{tenant_b['branch']['id']}",
        headers=auth_header(tenant_a["access_token"]),
    )
    assert foreign_branch.status_code in {403, 404}


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_update_company_and_branch_are_tenant_scoped(
    client: AsyncClient,
) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="upd-a@example.com",
        tenant_name="Tenant A",
        company_name="A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="upd-b@example.com",
        tenant_name="Tenant B",
        company_name="B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])

    updated = await client.patch(
        f"/companies/{tenant_a['company']['id']}",
        headers=headers_a,
        json={"legal_name": "A Corp Limited", "phone": "+254700000001"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["legal_name"] == "A Corp Limited"
    assert updated.json()["phone"] == "+254700000001"

    foreign = await client.patch(
        f"/companies/{tenant_b['company']['id']}",
        headers=headers_a,
        json={"name": "Hijacked"},
    )
    assert foreign.status_code == 404

    branch_id = tenant_a["branch"]["id"]
    patched = await client.patch(
        f"/branches/{branch_id}",
        headers=headers_a,
        json={"city": "Nairobi", "status": "INACTIVE"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["city"] == "Nairobi"
    assert patched.json()["status"] == "INACTIVE"

    other_branch = await client.patch(
        f"/branches/{tenant_b['branch']['id']}",
        headers=headers_a,
        json={"name": "Stolen"},
    )
    assert other_branch.status_code in {403, 404}


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_countries_are_readable_without_tenant(
    client: AsyncClient,
) -> None:
    response = await client.get("/countries")
    assert response.status_code == 200
    codes = {row["code"] for row in response.json()}
    assert codes == {"KE", "UG", "TZ", "RW"}
    kenya = next(row for row in response.json() if row["code"] == "KE")
    assert kenya["default_timezone"] == "Africa/Nairobi"
    assert kenya["default_currency"]["code"] == "KES"


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_companies_require_auth(client: AsyncClient) -> None:
    response = await client.post("/companies", json={"name": "Ghost Co"})
    assert response.status_code == 401
