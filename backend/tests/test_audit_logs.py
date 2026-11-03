import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_platform import _admin_login
from tests.test_tenancy import _kenya, _register


def _by_action(rows: list[dict], action: str) -> list[dict]:
    return [row for row in rows if row["action"] == action]


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_audit_log_records_requester_action_and_outcome(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="audit-a@example.com",
        tenant_name="Audit A",
        company_name="Audit A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="audit-b@example.com",
        tenant_name="Audit B",
        company_name="Audit B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    headers_b = auth_header(tenant_b["access_token"])
    company_a = tenant_a["company"]["id"]

    created = await client.post(
        "/departments",
        headers=headers_a,
        json={"company_id": company_a, "name": "UniqueAuditDept", "code": "UAD"},
    )
    assert created.status_code == 201, created.text

    denied = await client.post(
        "/auth/login",
        json={"email": "audit-a@example.com", "password": "wrong-password"},
    )
    assert denied.status_code == 401

    listed_a = await client.get("/audit-logs", headers=headers_a)
    assert listed_a.status_code == 200, listed_a.text
    rows_a = listed_a.json()
    assert all(row["tenant_id"] == tenant_a["tenant"]["id"] for row in rows_a)

    login_fail = _by_action(rows_a, "POST /auth/login")
    assert login_fail
    assert login_fail[0]["outcome"] == "FAILED"
    assert login_fail[0]["requester"] == "Ada Owner (audit-a@example.com)"
    assert "password12" not in login_fail[0]["request"]
    assert "wrong-password" not in login_fail[0]["request"]
    assert "[redacted]" in login_fail[0]["request"]
    assert login_fail[0]["response"]

    created_log = _by_action(rows_a, "POST /departments")
    assert created_log
    assert created_log[0]["outcome"] == "SUCCESS"
    assert created_log[0]["response"] == "Successful"
    assert "UniqueAuditDept" in created_log[0]["request"]
    assert created_log[0]["requester"] == "Ada Owner (audit-a@example.com)"
    assert created_log[0]["created_at"].endswith("Z")

    assert not _by_action(rows_a, "GET /audit-logs")

    listed_b = await client.get("/audit-logs", headers=headers_b)
    assert listed_b.status_code == 200, listed_b.text
    rows_b = listed_b.json()
    assert all("UniqueAuditDept" not in row["request"] for row in rows_b)
    assert all(row["tenant_id"] == tenant_b["tenant"]["id"] for row in rows_b)

    admin = await _admin_login(client)
    platform = await client.get("/platform/audit-logs", headers=admin)
    assert platform.status_code == 200, platform.text
    platform_rows = platform.json()
    assert any("UniqueAuditDept" in row["request"] for row in platform_rows)
    assert not _by_action(platform_rows, "GET /platform/audit-logs")
