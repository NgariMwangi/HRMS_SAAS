from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.session import get_session_maker
from app.models import Country
from tests.conftest import auth_header


async def _kenya_id() -> str:
    maker = get_session_maker()
    async with maker() as session:
        country = await session.scalar(
            select(Country)
            .options(selectinload(Country.default_currency))
            .where(Country.code == "KE")
        )
        assert country is not None
        return str(country.id)


def _register_payload(email: str, country_id: str, **overrides: object) -> dict:
    body: dict = {
        "owner_full_name": "Ada Owner",
        "email": email,
        "password": "password12",
        "tenant_name": "Ada Holdings",
        "company_name": "Ada Trading",
        "country_id": country_id,
    }
    body.update(overrides)
    return body


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_register_creates_trial_tenant_owner_company_and_branch(
    client: AsyncClient,
) -> None:
    country_id = await _kenya_id()
    response = await client.post(
        "/auth/register",
        json=_register_payload("ada@example.com", country_id),
    )
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] == 600
    assert body["refresh_expires_in"] == 1800
    assert body["tenant"]["subscription_tier"] == "TRIAL"
    assert body["tenant"]["status"] == "ACTIVE"
    assert body["tenant"]["name"] == "Ada Holdings"
    trial_end = datetime.fromisoformat(body["tenant"]["trial_ends_at"])
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert trial_end > now + timedelta(days=13)
    assert trial_end < now + timedelta(days=15)

    assert body["user"]["email"] == "ada@example.com"
    assert body["user"]["role"] == "OWNER"
    assert body["user"]["tenant_id"] == body["tenant"]["id"]
    assert body["company"]["name"] == "Ada Trading"
    assert body["company"]["tenant_id"] == body["tenant"]["id"]
    assert body["branch"]["code"] == "HQ"
    assert body["branch"]["timezone"] == "Africa/Nairobi"

    me = await client.get("/auth/me", headers=auth_header(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "ada@example.com"


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    country_id = await _kenya_id()
    first = await client.post(
        "/auth/register",
        json=_register_payload("ada@example.com", country_id),
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        "/auth/register",
        json=_register_payload("ada@example.com", country_id, tenant_name="Other"),
    )
    assert second.status_code == 409


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_login_and_rejected_wrong_password(client: AsyncClient) -> None:
    country_id = await _kenya_id()
    registered = await client.post(
        "/auth/register",
        json=_register_payload("ada@example.com", country_id),
    )
    assert registered.status_code == 201, registered.text

    wrong = await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "wrongpass"},
    )
    assert wrong.status_code == 401

    login = await client.post(
        "/auth/login",
        json={"email": "Ada@example.com", "password": "password12"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["id"] == registered.json()["user"]["id"]
    assert login.json()["tenant"]["id"] == registered.json()["tenant"]["id"]
    assert login.json()["refresh_token"]
    assert login.json()["expires_in"] == 600


def _claims(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_access_and_refresh_token_lifetimes(client: AsyncClient) -> None:
    country_id = await _kenya_id()
    registered = await client.post(
        "/auth/register",
        json=_register_payload("ada@example.com", country_id),
    )
    assert registered.status_code == 201, registered.text
    body = registered.json()
    access = _claims(body["access_token"])
    refresh = _claims(body["refresh_token"])
    assert access["token_use"] == "access"
    assert refresh["token_use"] == "refresh"
    assert access["kind"] == "tenant"
    assert refresh["kind"] == "tenant"
    assert access["exp"] - access["iat"] == 10 * 60
    assert refresh["exp"] - refresh["iat"] == 30 * 60


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_refresh_rotates_tokens_and_rejects_wrong_use(client: AsyncClient) -> None:
    country_id = await _kenya_id()
    registered = await client.post(
        "/auth/register",
        json=_register_payload("ada@example.com", country_id),
    )
    assert registered.status_code == 201, registered.text
    body = registered.json()

    blocked = await client.get("/auth/me", headers=auth_header(body["refresh_token"]))
    assert blocked.status_code == 401

    access_as_refresh = await client.post(
        "/auth/refresh",
        json={"refresh_token": body["access_token"]},
    )
    assert access_as_refresh.status_code == 401

    refreshed = await client.post(
        "/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert refreshed.status_code == 200, refreshed.text
    pair = refreshed.json()
    assert pair["access_token"]
    assert pair["refresh_token"]
    assert pair["access_token"] != body["access_token"]
    assert pair["refresh_token"] != body["refresh_token"]
    assert pair["expires_in"] == 600
    assert pair["refresh_expires_in"] == 1800

    me = await client.get("/auth/me", headers=auth_header(pair["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "ada@example.com"

    platform = await client.post(
        "/platform/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    assert platform.status_code == 403
