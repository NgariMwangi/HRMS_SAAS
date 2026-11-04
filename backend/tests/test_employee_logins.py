import pytest
from tests.test_access import workspace, staff_login


async def login(client, email, password):
    return await client.post("/auth/login", json={"email": email, "password": password})


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_owner_changes_employee_login_and_resets_password_with_scoped_access(client):
    w, owner = await workspace(client)
    person, account, employee = await staff_login(client, owner, w, "LoginChange")
    _, _, hr = await staff_login(client, owner, w, "LoginHr", "HR")
    _, foreign = await workspace(client, "foreign-login-owner@example.com")
    path = f"/employees/{person['id']}/login"
    body = {"email": "new.login@example.com"}
    for actor in (employee, hr):
        assert (await client.patch(path, headers=actor, json=body)).status_code == 403
    assert (await client.patch(path, headers=foreign, json=body)).status_code in {403, 404}
    # Email-only changes preserve the password, employee profile and role.
    saved = await client.patch(path, headers=owner, json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["id"] == account["id"] and saved.json()["role"] == "EMPLOYEE"
    assert "password_hash" not in saved.json()
    assert (await login(client, account["email"], "Password123!")).status_code == 401
    assert (await login(client, body["email"], "Password123!")).status_code == 200
    profile = (await client.get(f"/employees/{person['id']}", headers=owner)).json()
    assert profile["email"] == person["email"] and profile["clock_login_email"] == body["email"]
    reset = await client.patch(path, headers=owner, json={**body, "password": "Replacement123!"})
    assert reset.status_code == 200, reset.text
    assert (await login(client, body["email"], "Password123!")).status_code == 401
    assert (await login(client, body["email"], "Replacement123!")).status_code == 200
    assert (await client.patch(path, headers=owner, json={"email": w["user"]["email"]})).status_code == 409
    assert (await client.patch(path, headers=owner, json={**body, "password": "é" * 40})).status_code == 422
    assert (await client.patch(path, headers=owner, json={**body, "role": "OWNER"})).status_code == 422
    # Failed changes do not overwrite the last successful credentials.
    assert (await login(client, body["email"], "Replacement123!")).status_code == 200


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_employee_changes_own_email_with_password_confirmation_and_no_identity_override(client):
    w, owner = await workspace(client)
    person, account, employee = await staff_login(client, owner, w, "OwnLogin")
    other, other_account, _ = await staff_login(client, owner, w, "OtherLogin")
    path = "/employee-portal/login"
    body = {"email": "self.updated@example.com", "current_password": "Password123!"}
    assert (await client.patch(path, headers=employee, json={**body, "current_password": "wrong-password"})).status_code == 400
    assert (await client.patch(path, headers=employee, json={**body, "employee_id": other["id"]})).status_code == 422
    assert (await client.patch(path, headers=employee, json={**body, "email": other_account["email"]})).status_code == 409
    result = await client.patch(path, headers=employee, json=body)
    assert result.status_code == 200, result.text
    assert result.json()["id"] == account["id"] and result.json()["employee_id"] == person["id"]
    assert result.json()["email"] == body["email"] and "password_hash" not in result.json()
    assert (await login(client, account["email"], "Password123!")).status_code == 401
    assert (await login(client, body["email"], "Password123!")).status_code == 200
    # Existing self-service password change still works after the email change.
    changed = await client.post("/employee-portal/password", headers=employee, json={"current_password": "Password123!", "new_password": "OwnReplacement123!"})
    assert changed.status_code == 200, changed.text
    assert (await login(client, body["email"], "Password123!")).status_code == 401
    assert (await login(client, body["email"], "OwnReplacement123!")).status_code == 200
    assert (await login(client, other_account["email"], "Password123!")).status_code == 200
