import uuid

import pytest

from app.db.session import get_session_maker
from app.models import User
from tests.conftest import auth_header
from tests.test_leave_requests import _leave_type, _person
from tests.test_tenancy import _kenya, _register


async def workspace(client, email="roles-owner@example.com"):
    country = await _kenya()
    data = await _register(client, email=email, tenant_name="Access test", company_name="Access company", country_id=country.id)
    return data, auth_header(data["access_token"])


async def staff_login(client, headers, workspace, name, role="EMPLOYEE"):
    person = await _person(client, headers, workspace["company"]["id"], workspace["branch"]["id"], name, f"{name.lower()}@roles.example")
    response = await client.post(f"/employees/{person['id']}/login", headers=headers, json={"email": f"{name.lower()}@login.example", "password": "Password123!"})
    assert response.status_code == 201, response.text
    identity = response.json()
    if role != "EMPLOYEE":
        assigned = await client.patch(f"/access/users/{identity['id']}", headers=headers, json={"role": role})
        assert assigned.status_code == 200, assigned.text
    login = await client.post("/auth/login", json={"email": identity["email"], "password": "Password123!"})
    assert login.status_code == 200, login.text
    return person, identity, auth_header(login.json()["access_token"])


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_role_crud_validation_and_tenant_isolation(client):
    a, owner = await workspace(client)
    b, other = await workspace(client, "roles-other@example.com")
    roles = await client.get("/access/roles", headers=owner)
    assert roles.status_code == 200
    assert {row["key"] for row in roles.json()} == {"OWNER", "ADMIN", "HR", "MANAGER", "EMPLOYEE"}
    owner_role = next(row for row in roles.json() if row["key"] == "OWNER")
    assert (await client.patch(f"/access/roles/{owner_role['id']}", headers=owner, json={"name": "Changed", "permissions": []})).status_code == 400
    for payload in ({"name": "   "}, {"name": "Bad", "permissions": ["invented.permission"]}):
        assert (await client.post("/access/roles", headers=owner, json=payload)).status_code == 400
    role = await client.post("/access/roles", headers=owner, json={"name": "Payroll clerk", "permissions": ["payroll.manage"]})
    assert role.status_code == 201, role.text
    role = role.json()
    assert (await client.post("/access/roles", headers=owner, json={"name": "payroll CLERK"})).status_code == 409
    assert (await client.patch(f"/access/roles/{role['id']}", headers=other, json={"name": "Hijack"})).status_code == 404
    assert (await client.delete(f"/access/roles/{role['id']}", headers=other)).status_code == 404
    updated = await client.patch(f"/access/roles/{role['id']}", headers=owner, json={"name": "Payroll reader", "permissions": ["people.view_all"]})
    assert updated.status_code == 200, updated.text
    assert updated.json()["permissions"] == ["people.view_all"]
    assert (await client.delete(f"/access/roles/{role['id']}", headers=owner)).status_code == 204
    assert (await client.delete(f"/access/roles/{owner_role['id']}", headers=owner)).status_code == 400


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_employee_self_scope_and_direct_api_mutation_denials(client):
    data, owner = await workspace(client)
    person, identity, employee = await staff_login(client, owner, data, "Self")
    other = await _person(client, owner, data["company"]["id"], data["branch"]["id"], "Other", "other@records.example")
    rows = await client.get("/employees", headers=employee)
    assert rows.status_code == 200
    assert [row["id"] for row in rows.json()] == [person["id"]]
    assert (await client.get(f"/employees/{other['id']}", headers=employee)).status_code == 404
    assert (await client.get(f"/employees/{person['id']}/next-of-kin", headers=employee)).status_code == 200
    assert (await client.get(f"/employees/{other['id']}/documents", headers=employee)).status_code == 404
    denied = [
        ("post", "/companies", {"name": "Forbidden"}),
        ("patch", f"/companies/{data['company']['id']}", {"name": "Forbidden"}),
        ("post", "/employees", {"company_id": data["company"]["id"], "branch_id": data["branch"]["id"], "first_name": "Bad", "last_name": "Actor"}),
        ("patch", f"/employees/{person['id']}", {"first_name": "Forbidden"}),
        ("put", f"/employees/{person['id']}/next-of-kin", {"items": []}),
        ("put", f"/employees/{person['id']}/supervisors", {"supervisor_ids": []}),
        ("delete", f"/employees/{person['id']}/photo", None),
    ]
    for method, path, payload in denied:
        response = await client.request(method.upper(), path, headers=employee, json=payload)
        assert response.status_code == 403, (path, response.text)
    for path in ("/access/roles", "/access/users", "/audit-logs", "/documents?company_id=" + data["company"]["id"], "/payroll/runs?company_id=" + data["company"]["id"] + "&branch_id=" + data["branch"]["id"]):
        assert (await client.get(path, headers=employee)).status_code == 403, path


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_custom_grants_revoke_without_relogin_and_assigned_role_cannot_be_deleted(client):
    data, owner = await workspace(client)
    person, identity, employee = await staff_login(client, owner, data, "Custom")
    created = await client.post("/access/roles", headers=owner, json={"name": "People editor", "permissions": ["people.manage"]})
    role = created.json()
    assigned = await client.patch(f"/access/users/{identity['id']}", headers=owner, json={"role": role["key"]})
    assert assigned.status_code == 200, assigned.text
    assert (await client.patch(f"/employees/{person['id']}", headers=employee, json={"first_name": "Allowed"})).status_code == 200
    assert (await client.post("/companies", headers=employee, json={"name": "No org grant"})).status_code == 403
    assert (await client.delete(f"/access/roles/{role['id']}", headers=owner)).status_code == 409
    edited = await client.patch(f"/access/roles/{role['id']}", headers=owner, json={"name": role["name"], "permissions": ["people.view_own"]})
    assert edited.status_code == 200, edited.text
    assert (await client.patch(f"/employees/{person['id']}", headers=employee, json={"first_name": "Denied"})).status_code == 403
    assert (await client.get("/access/me", headers=employee)).json()["permissions"] == ["people.view_own"]


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_last_active_owner_and_non_owner_promotion_protection(client):
    data, owner = await workspace(client)
    person, identity, admin = await staff_login(client, owner, data, "Admin", "ADMIN")
    assert (await client.patch(f"/access/users/{data['user']['id']}", headers=owner, json={"role": "ADMIN"})).status_code == 400
    assert (await client.patch(f"/access/users/{identity['id']}", headers=admin, json={"role": "OWNER"})).status_code == 403
    assert (await client.patch(f"/access/users/{data['user']['id']}", headers=admin, json={"role": "HR"})).status_code == 403
    assert (await client.patch(f"/access/users/{identity['id']}", headers=owner, json={"role": "DOES_NOT_EXIST"})).status_code == 400
    assert (await client.patch(f"/access/users/{identity['id']}", headers=owner, json={"role": "OWNER"})).status_code == 200
    maker = get_session_maker()
    async with maker() as session:
        target = await session.get(User, uuid.UUID(identity["id"]))
        target.status = "INACTIVE"
        await session.commit()
    assert (await client.patch(f"/access/users/{data['user']['id']}", headers=owner, json={"role": "ADMIN"})).status_code == 400


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_manager_team_leave_and_identity_cannot_be_spoofed(client):
    data, owner = await workspace(client)
    lead, lead_user, manager = await staff_login(client, owner, data, "Lead", "MANAGER")
    report, report_user, employee = await staff_login(client, owner, data, "Report")
    stranger, stranger_user, outsider = await staff_login(client, owner, data, "Stranger")
    await client.put(f"/employees/{report['id']}/supervisors", headers=owner, json={"supervisor_ids": [lead["id"]]})
    kind = await _leave_type(client, owner, data["company"]["id"], "Medical", "CALENDAR")
    payload = {"employee_id": report["id"], "leave_type_id": kind["id"], "start_on": "2026-06-01", "end_on": "2026-06-02", "approval_mode": "SUPERVISOR_THEN_HR"}
    assert (await client.post("/leave-requests/self", headers=outsider, json=payload)).status_code == 403
    created = await client.post("/leave-requests/self", headers=employee, json=payload)
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]
    assert (await client.get(f"/leave-requests/{request_id}", headers=outsider)).status_code == 404
    assert (await client.get("/leave-requests", headers=outsider)).json() == []
    assert (await client.get("/leave-requests", headers=manager)).json()[0]["id"] == request_id
    assert (await client.get(f"/employees/{stranger['id']}", headers=manager)).status_code == 404
    assert (await client.get(f"/employees/{report['id']}", headers=manager)).status_code == 200
    decision = {"supervisor_employee_id": lead["id"], "decision": "APPROVED"}
    assert (await client.post(f"/leave-requests/{request_id}/supervisor-decision", headers=employee, json=decision)).status_code == 403
    decision["supervisor_employee_id"] = stranger["id"]
    assert (await client.post(f"/leave-requests/{request_id}/supervisor-decision", headers=manager, json=decision)).status_code == 403
    decision["supervisor_employee_id"] = lead["id"]
    result = await client.post(f"/leave-requests/{request_id}/supervisor-decision", headers=manager, json=decision)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "PENDING_HR"
    assert (await client.post(f"/leave-requests/{request_id}/hr-decision", headers=manager, json={"decision": "APPROVED"})).status_code == 403
    balances = await client.get("/leave-balances", headers=employee)
    assert balances.status_code == 200
    assert {row["employee_id"] for row in balances.json()} == {report["id"]}


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_custom_leave_only_role_uses_limited_people_choices(client):
    data, owner = await workspace(client)
    person, identity, staff = await staff_login(client, owner, data, "LeaveOnly")
    other = await _person(client, owner, data["company"]["id"], data["branch"]["id"], "Colleague", "colleague@records.example")
    created = await client.post("/access/roles", headers=owner, json={"name": "Leave self service", "permissions": ["leave.view_own"]})
    role = created.json()
    assigned = await client.patch(f"/access/users/{identity['id']}", headers=owner, json={"role": role["key"]})
    assert assigned.status_code == 200, assigned.text
    assert (await client.get("/employees", headers=staff)).status_code == 403
    choices = await client.get(f"/leave-requests/people?company_id={data['company']['id']}", headers=staff)
    assert choices.status_code == 200, choices.text
    assert [row["id"] for row in choices.json()] == [person["id"]]
    assert "id_number" not in choices.json()[0]
    assert "personal_email" not in choices.json()[0]


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_custom_payroll_and_document_grants_do_not_expose_full_profiles(client):
    data, owner = await workspace(client)
    person, identity, staff = await staff_login(client, owner, data, "PayrollOnly")
    other = await _person(client, owner, data["company"]["id"], data["branch"]["id"], "OtherSummary", "othersummary@records.example")
    created = await client.post("/access/roles", headers=owner, json={"name": "Payroll and own files", "permissions": ["payroll.manage", "documents.view_own"]})
    role = created.json()
    assert (await client.patch(f"/access/users/{identity['id']}", headers=owner, json={"role": role["key"]})).status_code == 200
    assert (await client.get(f"/employees/{person['id']}", headers=staff)).status_code == 404
    summary = await client.get(f"/employees/{person['id']}/summary?area=documents", headers=staff)
    assert summary.status_code == 200, summary.text
    assert "id_number" not in summary.json()
    assert (await client.get(f"/employees/{other['id']}/summary?area=documents", headers=staff)).status_code == 404
    assert (await client.get(f"/employees/{other['id']}/summary?area=payroll", headers=staff)).status_code == 200
    assert (await client.get(f"/employees/{other['id']}/compensation", headers=staff)).status_code == 200
    assert (await client.get(f"/employees/{person['id']}/summary?area=people", headers=staff)).status_code == 422
    assert (await client.get(f"/employees/{person['id']}/documents", headers=staff)).status_code == 200


def test_every_tenant_mutation_has_a_permission_dependency():
    from app.main import create_app
    from fastapi.routing import APIRoute
    for route in create_app().routes:
        if not isinstance(route, APIRoute) or not route.methods.intersection({"POST", "PUT", "PATCH", "DELETE"}):
            continue
        if route.path.startswith(("/auth", "/platform", "/access")):
            continue
        assert any(dependency.call.__module__ == "app.api.access_control" for dependency in route.dependant.dependencies), route.path
