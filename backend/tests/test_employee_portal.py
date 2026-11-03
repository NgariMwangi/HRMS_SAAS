from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from app.core.config import get_settings
from app.db.session import get_session_maker
from app.models import Tenant
from app.services import google_auth
from tests.test_access import workspace, staff_login


@pytest.fixture
def google_tokens(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test.apps.googleusercontent.com")
    get_settings.cache_clear()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(google_auth.keys, "get_signing_key_from_jwt", lambda credential: SimpleNamespace(key=key.public_key()))
    def token(challenge_nonce, subject="google-employee-1", **overrides):
        now = datetime.now(timezone.utc)
        claims = {"sub": subject, "iss": "https://accounts.google.com", "aud": "test.apps.googleusercontent.com", "iat": now, "exp": now + timedelta(minutes=5), "email": "personal@gmail.com", "email_verified": True, "nonce": challenge_nonce, **overrides}
        return jwt.encode(claims, key, algorithm="RS256")
    yield token
    get_settings.cache_clear()


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_portal_profile_identity_allowlist_and_password(client):
    data, owner = await workspace(client)
    person, identity, employee = await staff_login(client, owner, data, "Portal")
    other, _, _ = await staff_login(client, owner, data, "Other")
    assert (await client.get("/employee-portal/me", headers=owner)).status_code == 403
    me = await client.get("/employee-portal/me", headers=employee)
    assert me.status_code == 200, me.text
    assert me.json()["employee"]["id"] == person["id"]
    assert not me.json()["google_linked"]
    assert (await client.get("/employee-portal/summary", headers=employee)).json() == {"pending_leave": 0, "documents": 0, "active_appraisals": 0, "unread_notifications": 0}
    update = await client.patch("/employee-portal/profile", headers=employee, json={"phone": "+254700000001", "personal_email": "personal@example.com"})
    assert update.status_code == 200, update.text
    assert update.json()["phone"] == "+254700000001"
    for payload in ({"employee_id": other["id"], "phone": "stolen"}, {"status": "TERMINATED"}, {"email": "change@login.example"}, {"role": "OWNER"}):
        assert (await client.patch("/employee-portal/profile", headers=employee, json=payload)).status_code == 422
    saved = await client.put("/employee-portal/emergency-contacts", headers=employee, json={"items": [{"name": "Jane", "relationship": "Sibling", "phone": "0700000000"}]})
    assert saved.status_code == 200, saved.text
    assert (await client.get("/employee-portal/emergency-contacts", headers=employee)).json()[0]["name"] == "Jane"
    assert (await client.get(f"/employees/{other['id']}/next-of-kin", headers=employee)).status_code == 404
    assert (await client.post("/employee-portal/password", headers=employee, json={"current_password": "wrong", "new_password": "NewPassword123!"})).status_code == 400
    assert (await client.post("/employee-portal/password", headers=employee, json={"current_password": "Password123!", "new_password": "NewPassword123!"})).status_code == 200
    assert (await client.post("/auth/login", json={"email": identity["email"], "password": "Password123!"})).status_code == 401
    assert (await client.post("/auth/login", json={"email": identity["email"], "password": "NewPassword123!"})).status_code == 200


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_portal_payslip_approved_own_only(client):
    data, owner = await workspace(client)
    a, _, staff = await staff_login(client, owner, data, "Paid")
    b, _, second = await staff_login(client, owner, data, "OtherPaid")
    for person in (a, b):
        saved = await client.post(f"/employees/{person['id']}/compensation", headers=owner, json={"effective_from": "2026-01-01", "structure": "GROSS_ONLY", "gross_amount": "100000"})
        assert saved.status_code == 201, saved.text
    result = await client.post("/payroll/runs", headers=owner, json={"company_id": data["company"]["id"], "branch_id": data["branch"]["id"], "period_start": "2026-03-01", "period_end": "2026-03-31"})
    assert result.status_code == 201, result.text
    run = result.json()
    own = next(s for s in run["payslips"] if s["employee_id"] == a["id"])
    foreign = next(s for s in run["payslips"] if s["employee_id"] == b["id"])
    assert (await client.get("/employee-portal/payslips", headers=staff)).json() == []
    assert (await client.get(f"/employee-portal/payslips/{own['id']}", headers=staff)).status_code == 404
    assert (await client.post(f"/payroll/runs/{run['id']}/approve", headers=owner)).status_code == 200
    rows = await client.get("/employee-portal/payslips", headers=staff)
    assert rows.status_code == 200, rows.text
    assert [r["id"] for r in rows.json()] == [own["id"]]
    assert rows.json()[0]["currency_code"] == "KES"
    assert (await client.get(f"/employee-portal/payslips/{foreign['id']}", headers=staff)).status_code == 404
    assert (await client.get(f"/employee-portal/payslips/{own['id']}", headers=second)).status_code == 404


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_google_requires_link_password_then_uses_subject_and_prevents_replay(client, google_tokens):
    data, owner = await workspace(client)
    person, identity, staff = await staff_login(client, owner, data, "Google")
    nonce = (await client.get("/auth/google/challenge")).json()["nonce"]
    credential = google_tokens(nonce)
    assert (await client.post("/auth/google/login", json={"credential": credential})).status_code == 409
    assert (await client.post("/auth/google/login", json={"credential": credential, "email": identity["email"], "password": "incorrect"})).status_code == 401
    linked = await client.post("/auth/google/login", json={"credential": credential, "email": identity["email"], "password": "Password123!"})
    assert linked.status_code == 200, linked.text
    assert linked.json()["user"]["id"] == identity["id"]
    assert linked.json()["user"]["role"] == "EMPLOYEE"
    # Reusing a consumed nonce fails even if the old cookie is restored.
    client.cookies.set("hrms_google_nonce", nonce, path="/auth/google")
    assert (await client.post("/auth/google/login", json={"credential": credential})).status_code == 401
    client.cookies.clear()
    nonce = (await client.get("/auth/google/challenge")).json()["nonce"]
    again = await client.post("/auth/google/login", json={"credential": google_tokens(nonce, email="changed@gmail.com")})
    assert again.status_code == 200, again.text
    assert again.json()["user"]["id"] == identity["id"]
    assert (await client.get("/employee-portal/me", headers=staff)).json()["google_linked"]
    assert (await client.post("/auth/google/unlink", headers=staff, json={"password": "wrong"})).status_code == 400
    assert (await client.post("/auth/google/unlink", headers=staff, json={"password": "Password123!"})).status_code == 200
    assert not (await client.get("/employee-portal/me", headers=staff)).json()["google_linked"]


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_google_rejects_invalid_claims_and_unprovisioned_accounts(client, google_tokens):
    data, owner = await workspace(client)
    _, identity, staff = await staff_login(client, owner, data, "Secure")
    for overrides in ({"aud": "attacker.apps.googleusercontent.com"}, {"iss": "https://attacker.example"}, {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)}, {"nonce": "different"}, {"email_verified": False}, {"iat": datetime.now(timezone.utc) + timedelta(hours=1)}, {"sub": 123}):
        nonce = (await client.get("/auth/google/challenge")).json()["nonce"]
        rejected = await client.post("/auth/google/login", json={"credential": google_tokens(nonce, **overrides), "email": identity["email"], "password": "Password123!"})
        assert rejected.status_code == 401, rejected.text
    nonce = (await client.get("/auth/google/challenge")).json()["nonce"]
    assert (await client.post("/auth/google/login", json={"credential": google_tokens(nonce), "email": "unregistered@example.com", "password": "Password123!"})).status_code == 401
    assert (await client.post("/auth/google/login", json={"credential": google_tokens(nonce), "email": data["user"]["email"], "password": "password12"})).status_code == 403
    assert (await client.get("/employee-portal/attendance?start=2026-03-31&end=2026-03-01", headers=staff)).status_code == 400


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_portal_attendance_is_own_even_with_hr_role_and_google_disabled(client, monkeypatch):
    data, owner = await workspace(client)
    own, _, staff = await staff_login(client, owner, data, "HrEmployee", role="HR")
    other, _, other_staff = await staff_login(client, owner, data, "OtherClock")
    for person in (own, other):
        marked = await client.put("/attendance", headers=owner, json={"employee_id": person["id"], "work_on": "2026-03-01", "status": "PRESENT"})
        assert marked.status_code == 200, marked.text
    history = await client.get("/employee-portal/attendance", headers=staff)
    assert history.status_code == 200, history.text
    assert len(history.json()) == 1
    assert history.json()[0]["work_on"] == "2026-03-01"
    other_history = (await client.get("/employee-portal/attendance", headers=other_staff)).json()
    assert other_history[0]["id"] != history.json()[0]["id"]
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    get_settings.cache_clear()
    assert (await client.get("/auth/google/config")).json() == {"client_id": "", "enabled": False}
    assert (await client.get("/auth/google/challenge")).status_code == 503


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_google_binding_conflict_and_inactive_tenant(client, google_tokens):
    data, owner = await workspace(client)
    _, identity, staff = await staff_login(client, owner, data, "Linked")
    _, other, other_staff = await staff_login(client, owner, data, "Conflict")
    nonce = (await client.get("/auth/google/challenge")).json()["nonce"]
    assert (await client.post("/auth/google/link", headers=staff, json={"credential": google_tokens(nonce), "password": "Password123!"})).status_code == 200
    nonce = (await client.get("/auth/google/challenge")).json()["nonce"]
    conflict = await client.post("/auth/google/link", headers=other_staff, json={"credential": google_tokens(nonce), "password": "Password123!"})
    assert conflict.status_code == 409, conflict.text
    async with get_session_maker()() as session:
        tenant = await session.get(Tenant, uuid.UUID(data["tenant"]["id"]))
        tenant.status = "SUSPENDED"
        await session.commit()
    assert (await client.get("/employee-portal/me", headers=staff)).status_code == 403
    nonce = (await client.get("/auth/google/challenge")).json()["nonce"]
    assert (await client.post("/auth/google/login", json={"credential": google_tokens(nonce)})).status_code == 403


def test_google_credentials_are_redacted_from_audit():
    from app.services.audit import redact_value
    assert redact_value({"credential": "private-token", "nonce": "secret-challenge", "password": "secret"}) == {"credential": "[redacted]", "nonce": "[redacted]", "password": "[redacted]"}
