import uuid
import pytest
from tests.test_access import workspace, staff_login
from tests.test_platform import _admin_login
from tests.test_performance import setup_cycle
from tests.test_recruitment import vacancy, candidate, post


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_platform_module_oversight_is_scoped_and_read_only(client):
    a, owner = await workspace(client)
    b, other = await workspace(client, "portal-other@example.com")
    person, _, employee = await staff_login(client, owner, a, "PortalReview")
    manager, _, _ = await staff_login(client, owner, a, "PortalManager", "MANAGER")
    review, _ = await setup_cycle(client, owner, a["company"]["id"])
    assigned = await post(client, owner, f"/performance/cycles/{review['id']}/participants", {"employee_ids": [person["id"]], "manager_id": manager["id"]})
    appraisal = assigned[0]["appraisal_id"]
    job = await vacancy(client, owner, a["company"]["id"])
    applicant = await candidate(client, owner, a["company"]["id"])
    await vacancy(client, other, b["company"]["id"])
    pdf = b"%PDF-1.4\nPortal test"
    assert (await client.post(f"/recruitment/candidates/{applicant['id']}/cv", headers=owner, files={"file": ("cv.pdf", pdf, "application/pdf")})).status_code == 200
    admin = await _admin_login(client)
    base = f"/platform/tenants/{a['tenant']['id']}/modules"
    cid = a["company"]["id"]
    for module in ("performance", "recruitment"):
        assert (await client.get(f"{base}/{module}?company_id={cid}", headers=employee)).status_code == 403
        assert (await client.get(f"{base}/{module}?company_id={b['company']['id']}", headers=admin)).status_code == 403
        response = await client.get(f"{base}/{module}?company_id={cid}", headers=admin)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert (await client.post(f"{base}/{module}", headers=admin, json={})).status_code == 405
    data = (await client.get(f"{base}/performance?company_id={cid}", headers=admin)).json()
    assert data["report"]["participants"] == 1
    assert data["appraisals"][0]["id"] == appraisal
    detail = await client.get(f"{base}/performance/appraisals/{appraisal}?company_id={cid}", headers=admin)
    assert detail.status_code == 200, detail.text
    assert detail.json()["participant"]["employee_id"] == person["id"]
    # Same-tenant but wrong-company detail must not be returned either.
    extra = await post(client, owner, "/companies", {"name": "Extra company"})
    assert (await client.get(f"{base}/performance/appraisals/{appraisal}?company_id={extra['id']}", headers=admin)).status_code == 404
    export = await client.get(f"{base}/performance/export?company_id={cid}", headers=admin)
    assert export.status_code == 200 and "PortalReview" in export.text
    recruitment = (await client.get(f"{base}/recruitment?company_id={cid}", headers=admin)).json()
    assert [j["id"] for j in recruitment["jobs"]] == [job["id"]]
    assert "cv_data" not in recruitment["candidates"][0]
    cv = await client.get(f"{base}/recruitment/candidates/{applicant['id']}/cv?company_id={cid}", headers=admin)
    assert cv.content == pdf
    assert (await client.get(f"{base}/recruitment/candidates/{applicant['id']}/cv?company_id={extra['id']}", headers=admin)).status_code == 404


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_employee_published_plans_and_assigned_development_only(client):
    w, owner = await workspace(client)
    person, _, employee = await staff_login(client, owner, w, "PlanOwner")
    outsider, _, outsider_login = await staff_login(client, owner, w, "PlanOther")
    manager, _, _ = await staff_login(client, owner, w, "PlanManager", "MANAGER")
    cid = w["company"]["id"]
    review, _ = await setup_cycle(client, owner, cid)
    assigned = await post(client, owner, f"/performance/cycles/{review['id']}/participants", {"employee_ids": [person["id"]], "manager_id": manager["id"]})
    appraisal = assigned[0]["appraisal_id"]
    action = await post(client, owner, f"/performance/appraisals/{appraisal}/development-actions", {
        "title": "Complete learning", "owner_id": person["id"], "due_date": "2026-12-31", "action": "Attend training", "comments": "Manager guidance"})
    manager_action = await post(client, owner, f"/performance/appraisals/{appraisal}/development-actions", {
        "title": "Arrange training", "owner_id": manager["id"], "due_date": "2026-12-31", "action": "Provide resources"})
    payload = {"version": action["version"], "status": "IN_PROGRESS", "progress": 50, "comments": "Half complete"}
    path = f"/employee-portal/development-actions/{action['id']}"
    assert (await client.patch(path, headers=outsider_login, json=payload)).status_code == 404
    assert (await client.patch(f"/employee-portal/development-actions/{manager_action['id']}", headers=employee, json=payload)).status_code == 404
    assert (await client.patch(path, headers=employee, json={**payload, "owner_id": outsider["id"]})).status_code == 422
    assert (await client.patch(path, headers=employee, json={**payload, "status": "CANCELLED"})).status_code == 403
    updated = await client.patch(path, headers=employee, json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["details"]["comments"] == "Manager guidance"
    assert updated.json()["details"]["employee_comments"] == "Half complete"
    assert (await client.patch(path, headers=employee, json=payload)).status_code == 409
    completed = await client.patch(path, headers=employee, json={**payload, "version": updated.json()["version"], "status": "COMPLETED", "progress": 90})
    assert completed.status_code == 200 and completed.json()["progress"] == "100"
    assert (await client.patch(path, headers=employee, json={**payload, "version": completed.json()["version"]})).status_code == 409
    plan = await post(client, owner, f"/performance/pips?company_id={cid}", {
        "employee_id": person["id"], "manager_id": manager["id"], "hr_owner_id": w["user"]["id"], "appraisal_id": appraisal,
        "start_date": "2026-01-01", "end_date": "2026-12-31", "reason": "Agreed support", "issues": "Training gap", "support": "Coaching",
        "objectives": [{"title": "Learn", "target": "One course", "expected_standard": "Pass"}]})
    assert (await client.get("/employee-portal/improvement-plans", headers=employee)).json() == []
    active = await client.patch(f"/performance/pips/{plan['id']}", headers=owner, json={"version": plan["version"], "status": "ACTIVE", "reason": "Publish agreed plan"})
    assert active.status_code == 200, active.text
    meeting = await post(client, owner, f"/performance/pips/{plan['id']}/reviews", {"meeting_date": "2026-03-01", "notes": "Discussed progress", "objective_progress": ["Course booked"], "next_review": "2026-04-01"})
    published = (await client.get("/employee-portal/improvement-plans", headers=employee)).json()
    assert len(published) == 1 and published[0]["reviews"][0]["id"] == meeting["id"]
    assert "hr_owner_id" not in published[0] and "approved_by" not in published[0]["details"]
    assert (await client.get("/employee-portal/improvement-plans", headers=outsider_login)).json() == []


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_platform_accounts_roles_and_last_owner_guard(client):
    w, owner = await workspace(client)
    other, other_owner = await workspace(client, "other-account@example.com")
    person, identity, _ = await staff_login(client, owner, w, "Linked")
    foreign, _, _ = await staff_login(client, other_owner, other, "ForeignLinked")
    admin = await _admin_login(client)
    base = f"/platform/tenants/{w['tenant']['id']}"
    access = base + "/modules/access"
    role = await post(client, admin, access + "/roles", {"name": "Portal analyst", "permissions": ["people.view_own", "performance.view_own"]})
    assert (await client.get(access + "/roles", headers=owner)).status_code == 403
    assert (await client.patch(access + f"/users/{identity['id']}", headers=admin, json={"role": role["key"]})).status_code == 200
    assert (await client.delete(access + f"/roles/{role['id']}", headers=admin)).status_code == 409
    assert (await client.patch(base + f"/users/{identity['id']}", headers=admin, json={"employee_id": foreign["id"]})).status_code == 403
    assert (await client.patch(base + f"/users/{identity['id']}", headers=admin, json={"employee_id": None})).status_code == 200
    account = await post(client, admin, base + "/users", {"full_name": "Portal account", "email": "linked-platform@example.com", "password": "Password123!", "role": "EMPLOYEE", "employee_id": person["id"]})
    assert account["employee_id"] == person["id"]
    duplicate = await client.post(base + "/users", headers=admin, json={"full_name": "Duplicate", "email": "duplicate-platform@example.com", "password": "Password123!", "employee_id": person["id"]})
    assert duplicate.status_code == 409
    login = await client.post("/auth/login", json={"email": account["email"], "password": "Password123!"})
    assert login.status_code == 200
    assert (await client.get("/employee-portal/me", headers={"Authorization": "Bearer " + login.json()["access_token"]})).json()["employee"]["id"] == person["id"]
    for payload in ({"role": "HR"}, {"status": "INACTIVE"}):
        assert (await client.patch(base + f"/users/{w['user']['id']}", headers=admin, json=payload)).status_code == 400
    assert (await client.delete(base + f"/users/{w['user']['id']}", headers=admin)).status_code == 400
    assert (await client.patch(access + f"/users/{w['user']['id']}", headers=admin, json={"role": "HR"})).status_code == 400
    assert (await client.get(f"/platform/tenants/{uuid.uuid4()}/modules/access/roles", headers=admin)).status_code == 404
