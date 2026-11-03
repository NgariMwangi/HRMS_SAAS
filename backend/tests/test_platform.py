import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from tests.conftest import auth_header


async def _admin_login(client: AsyncClient) -> dict[str, str]:
    settings = get_settings()
    response = await client.post(
        "/platform/auth/login",
        json={
            "email": settings.platform_admin_email,
            "password": settings.platform_admin_password,
        },
    )
    assert response.status_code == 200, response.text
    return auth_header(response.json()["access_token"])


async def _register(client: AsyncClient, email: str, country_id: str) -> dict:
    response = await client.post(
        "/auth/register",
        json={
            "owner_full_name": "Ada Owner",
            "email": email,
            "password": "password12",
            "tenant_name": "Ada Holdings",
            "company_name": "Ada Trading",
            "country_id": country_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_platform_admin_lists_and_suspends_tenants(client: AsyncClient) -> None:
    countries = await client.get("/countries")
    kenya_id = next(row["id"] for row in countries.json() if row["code"] == "KE")
    registered = await _register(client, "ada@example.com", kenya_id)
    tenant_id = registered["tenant"]["id"]

    tenant_headers = auth_header(registered["access_token"])
    forbidden = await client.get("/platform/tenants", headers=tenant_headers)
    assert forbidden.status_code == 403

    admin = await _admin_login(client)
    listed = await client.get("/platform/tenants", headers=admin)
    assert listed.status_code == 200, listed.text
    assert any(row["id"] == tenant_id for row in listed.json())

    overview = await client.get("/platform/overview", headers=admin)
    assert overview.status_code == 200
    assert overview.json()["tenant_count"] >= 1

    suspended = await client.patch(
        f"/platform/tenants/{tenant_id}",
        headers=admin,
        json={"status": "SUSPENDED"},
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "SUSPENDED"

    login = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "password12"},
    )
    assert login.status_code == 403

    detail = await client.get(f"/platform/tenants/{tenant_id}", headers=admin)
    assert detail.status_code == 200
    assert detail.json()["companies"][0]["branches"][0]["code"] == "HQ"

    user_id = detail.json()["users"][0]["id"]
    paused = await client.patch(
        f"/platform/users/{user_id}",
        headers=admin,
        json={"status": "INACTIVE"},
    )
    assert paused.status_code == 200
    assert paused.json()["status"] == "INACTIVE"


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_platform_admin_can_extend_trial_and_toggle_country(
    client: AsyncClient,
) -> None:
    countries = await client.get("/countries")
    kenya = next(row for row in countries.json() if row["code"] == "KE")
    await _register(client, "ada@example.com", kenya["id"])
    admin = await _admin_login(client)

    listed = await client.get("/platform/tenants", headers=admin)
    tenant_id = listed.json()[0]["id"]
    original_end = listed.json()[0]["trial_ends_at"]

    extended = await client.post(
        f"/platform/tenants/{tenant_id}/extend-trial",
        headers=admin,
    )
    assert extended.status_code == 200
    assert extended.json()["subscription_tier"] == "TRIAL"
    assert extended.json()["trial_ends_at"] != original_end

    try:
        toggled = await client.patch(
            f"/platform/countries/{kenya['id']}",
            headers=admin,
            json={"is_active": False},
        )
        assert toggled.status_code == 200
        assert toggled.json()["is_active"] is False
        public = await client.get("/countries")
        assert kenya["id"] not in {row["id"] for row in public.json()}
    finally:
        await client.patch(
            f"/platform/countries/{kenya['id']}",
            headers=admin,
            json={"is_active": True},
        )


async def test_platform_refresh_tokens(client: AsyncClient) -> None:
    settings = get_settings()
    login = await client.post(
        "/platform/auth/login",
        json={
            "email": settings.platform_admin_email,
            "password": settings.platform_admin_password,
        },
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["refresh_token"]
    assert body["expires_in"] == 600
    assert body["refresh_expires_in"] == 1800

    blocked = await client.get("/platform/me", headers=auth_header(body["refresh_token"]))
    assert blocked.status_code == 401

    refreshed = await client.post(
        "/platform/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert refreshed.status_code == 200, refreshed.text
    me = await client.get(
        "/platform/me",
        headers=auth_header(refreshed.json()["access_token"]),
    )
    assert me.status_code == 200
    assert me.json()["email"] == settings.platform_admin_email
