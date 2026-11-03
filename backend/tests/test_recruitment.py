from datetime import date, datetime, timedelta, timezone
import pytest
from tests.test_access import staff_login, workspace


async def post(client, headers, path, data, expected=201):
    response = await client.post(path, headers=headers, json=data)
    assert response.status_code == expected, response.text
    return response.json()


async def vacancy(client, headers, company_id, **kwargs):
    return await post(client, headers, f"/recruitment/jobs?company_id={company_id}", {
        "title": "Clinical officer", "description": "Provide patient care", "requirements": "Relevant experience", **kwargs})


async def candidate(client, headers, company_id, email="applicant@example.com"):
    return await post(client, headers, f"/recruitment/candidates?company_id={company_id}", {
        "first_name": "Amina", "last_name": "Applicant", "email": email, "notes": "Private HR note"})


async def open_job(client, headers, job):
    await post(client, headers, f"/recruitment/jobs/{job['id']}/status", {"status": "OPEN"}, 200)


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_complete_hiring_workflow_and_guards(client):
    w, owner = await workspace(client)
    cid, bid = w["company"]["id"], w["branch"]["id"]
    person, _, manager = await staff_login(client, owner, w, "Interviewer", "MANAGER")
    job = await vacancy(client, owner, cid, manager_id=person["id"])
    c = await candidate(client, owner, cid)
    payload = {"job_id": job["id"], "candidate_id": c["id"]}
    assert (await client.post("/recruitment/applications", headers=owner, json=payload)).status_code == 400
    await open_job(client, owner, job)
    app = await post(client, owner, "/recruitment/applications", payload)
    assert (await client.post("/recruitment/applications", headers=owner, json=payload)).status_code == 409
    assert (await client.post(f"/recruitment/candidates?company_id={cid}", headers=owner, json={"first_name": "Same", "last_name": "Person", "email": "APPLICANT@example.com"})).status_code == 409
    invalid = await client.post(f"/recruitment/candidates/{c['id']}/cv", headers=owner, files={"file": ("cv.pdf", b"html", "application/pdf")})
    assert invalid.status_code == 400
    pdf = b"%PDF-1.4\nRecruitment test"
    uploaded = await client.post(f"/recruitment/candidates/{c['id']}/cv", headers=owner, files={"file": ("cv.pdf", pdf, "application/pdf")})
    assert uploaded.status_code == 200, uploaded.text
    download = await client.get(f"/recruitment/candidates/{c['id']}/cv", headers=manager)
    assert download.content == pdf
    hire_data = {"branch_id": bid, "date_joined": date.today().isoformat()}
    assert (await client.post(f"/recruitment/applications/{app['id']}/hire", headers=owner, json=hire_data)).status_code == 400
    await post(client, owner, f"/recruitment/applications/{app['id']}/stage", {"stage": "SHORTLISTED"}, 200)
    interview = await post(client, owner, "/recruitment/interviews", {
        "application_id": app["id"], "starts_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "interviewer_ids": [person["id"]]})
    feedback = {"rating": 4, "recommendation": "PROCEED", "comments": "Strong clinical experience"}
    assert (await client.post(f"/recruitment/interviews/{interview['id']}/feedback", headers=owner, json=feedback)).status_code == 403
    recorded = await post(client, manager, f"/recruitment/interviews/{interview['id']}/feedback", feedback, 200)
    assert recorded["status"] == "COMPLETED"
    offer = await post(client, owner, "/recruitment/offers", {
        "application_id": app["id"], "salary": "75000.00", "currency": "KES", "start_date": (date.today() + timedelta(days=10)).isoformat()})
    assert (await client.post(f"/recruitment/offers/{offer['id']}/status", headers=owner, json={"status": "ACCEPTED"})).status_code == 400
    await post(client, owner, f"/recruitment/offers/{offer['id']}/status", {"status": "ISSUED"}, 200)
    assert (await client.post(f"/recruitment/applications/{app['id']}/stage", headers=owner, json={"stage": "REJECTED", "note": "Reason"})).status_code == 400
    await post(client, owner, f"/recruitment/offers/{offer['id']}/status", {"status": "ACCEPTED"}, 200)
    other_company = await post(client, owner, "/companies", {"name": "Other company"})
    other_candidate = await candidate(client, owner, other_company["id"], "othercompany@example.com")
    assert (await client.post("/recruitment/applications", headers=owner, json={"job_id": job["id"], "candidate_id": other_candidate["id"]})).status_code == 404
    result = await post(client, owner, f"/recruitment/applications/{app['id']}/hire", hire_data, 200)
    assert result["employee_number"].startswith("EMP-")
    assert (await client.post(f"/recruitment/applications/{app['id']}/hire", headers=owner, json=hire_data)).status_code == 409
    employee = (await client.get(f"/employees/{result['employee_id']}", headers=owner)).json()
    assert employee["personal_email"] == c["email"]
    assert employee["first_name"] == c["first_name"]
    assert (await client.post(f"/recruitment/offers/{offer['id']}/status", headers=owner, json={"status": "WITHDRAWN", "note": "Reason"})).status_code == 400
    view = (await client.get(f"/recruitment/workspace?company_id={cid}", headers=owner)).json()
    assert view["applications"][0]["stage"] == "HIRED"
    assert any(e["action"] == "Employee created" for e in view["events"])
    assert "cv_data" not in view["candidates"][0]
    other_view = (await client.get(f"/recruitment/workspace?company_id={other_company['id']}", headers=owner)).json()
    assert other_view["jobs"] == [] and other_view["applications"] == []
    assert {c["id"] for c in other_view["candidates"]} == {other_candidate["id"]}
    # One opening is filled. An accepted second applicant still cannot overfill it.
    second = await candidate(client, owner, cid, "secondapplicant@example.com")
    second_app = await post(client, owner, "/recruitment/applications", {"job_id": job["id"], "candidate_id": second["id"]})
    second_offer = await post(client, owner, "/recruitment/offers", {"application_id": second_app["id"], "salary": "40000", "currency": "KES", "start_date": date.today().isoformat()})
    for status in ["ISSUED", "ACCEPTED"]:
        await post(client, owner, f"/recruitment/offers/{second_offer['id']}/status", {"status": status}, 200)
    assert (await client.post(f"/recruitment/applications/{second_app['id']}/hire", headers=owner, json=hire_data)).status_code == 400


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_recruitment_tenant_company_and_assignment_scope(client):
    w, owner = await workspace(client)
    other_w, other_owner = await workspace(client, "other-recruit@example.com")
    cid, other_cid = w["company"]["id"], other_w["company"]["id"]
    person, _, manager = await staff_login(client, owner, w, "Manager", "MANAGER")
    _, _, employee = await staff_login(client, owner, w, "Employee")
    _, _, hr = await staff_login(client, owner, w, "Recruiter", "HR")
    assert "recruitment.manage" in (await client.get("/access/me", headers=hr)).json()["permissions"]
    assigned = await vacancy(client, owner, cid, manager_id=person["id"])
    unassigned = await vacancy(client, owner, cid)
    foreign = await vacancy(client, other_owner, other_cid)
    c1 = await candidate(client, owner, cid)
    c2 = await candidate(client, owner, cid, "unassigned@example.com")
    foreign_c = await candidate(client, other_owner, other_cid)
    for j in [assigned, unassigned]: await open_job(client, owner, j)
    a1 = await post(client, owner, "/recruitment/applications", {"job_id": assigned["id"], "candidate_id": c1["id"]})
    a2 = await post(client, owner, "/recruitment/applications", {"job_id": unassigned["id"], "candidate_id": c2["id"]})
    await post(client, owner, "/recruitment/applications", {"job_id": unassigned["id"], "candidate_id": c1["id"]})
    view = await client.get(f"/recruitment/workspace?company_id={cid}", headers=manager)
    assert view.status_code == 200, view.text
    result = view.json()
    assert {j["id"] for j in result["jobs"]} == {assigned["id"]}
    assert {a["id"] for a in result["applications"]} == {a1["id"]}
    assert {c["id"] for c in result["candidates"]} == {c1["id"]}
    assert "notes" not in result["candidates"][0]
    assert result["offers"] == [] and result["events"] == []
    assert (await client.get(f"/recruitment/workspace?company_id={cid}", headers=employee)).status_code == 403
    assert (await client.get(f"/recruitment/workspace?company_id={other_cid}", headers=owner)).status_code == 403
    assert (await client.post(f"/recruitment/jobs/{foreign['id']}/status", headers=owner, json={"status": "OPEN"})).status_code == 404
    assert (await client.post("/recruitment/applications", headers=owner, json={"job_id": assigned["id"], "candidate_id": foreign_c["id"]})).status_code == 404
    assert (await client.post(f"/recruitment/applications/{a2['id']}/stage", headers=manager, json={"stage": "SHORTLISTED"})).status_code == 403
    assert (await client.post(f"/recruitment/candidates/{c2['id']}/cv", headers=manager, files={"file": ("cv.pdf", b"%PDF-1", "application/pdf")})).status_code == 403
    assert (await client.get(f"/recruitment/candidates/{c2['id']}/cv", headers=manager)).status_code == 404
    # Assignment to one interview permits that application, not every applicant for the vacancy.
    interview = await post(client, owner, "/recruitment/interviews", {"application_id": a2["id"], "starts_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "interviewer_ids": [person["id"]]})
    result = (await client.get(f"/recruitment/workspace?company_id={cid}", headers=manager)).json()
    assert {a["id"] for a in result["applications"]} == {a1["id"], a2["id"]}
    assert {i["id"] for i in result["interviews"]} == {interview["id"]}


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_closed_jobs_offer_expiry_and_invalid_references(client):
    w, owner = await workspace(client)
    foreign_w, foreign_owner = await workspace(client, "foreign-recruit@example.com")
    cid = w["company"]["id"]
    foreign_person, _, _ = await staff_login(client, foreign_owner, foreign_w, "Foreign", "MANAGER")
    invalid = await client.post(f"/recruitment/jobs?company_id={cid}", headers=owner, json={"title": "Role", "manager_id": foreign_person["id"]})
    assert invalid.status_code == 404
    job = await vacancy(client, owner, cid)
    c = await candidate(client, owner, cid)
    await open_job(client, owner, job)
    a = await post(client, owner, "/recruitment/applications", {"job_id": job["id"], "candidate_id": c["id"]})
    expired = await post(client, owner, "/recruitment/offers", {"application_id": a["id"], "salary": "30000", "currency": "KES", "start_date": date.today().isoformat(), "expires_on": (date.today() - timedelta(days=1)).isoformat()})
    assert (await client.post(f"/recruitment/offers/{expired['id']}/status", headers=owner, json={"status": "ISSUED"})).status_code == 400
    await post(client, owner, f"/recruitment/jobs/{job['id']}/status", {"status": "CLOSED", "note": "Filled externally"}, 200)
    assert (await client.post(f"/recruitment/applications/{a['id']}/stage", headers=owner, json={"stage": "SHORTLISTED"})).status_code == 400
    assert (await client.post(f"/recruitment/applications/{a['id']}/stage", headers=owner, json={"stage": "REJECTED"})).status_code == 400
    await post(client, owner, f"/recruitment/applications/{a['id']}/stage", {"stage": "REJECTED", "note": "Vacancy closed"}, 200)


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_demo_seed_is_guarded_idempotent_and_preserves_existing_records(client):
    from app.db.seed_recruitment_demo import seed_demo
    from app.db.session import get_session_maker
    from tests.test_tenancy import _kenya, _register
    from tests.conftest import auth_header
    w, owner = await workspace(client)
    async with get_session_maker()() as session:
        with pytest.raises(RuntimeError, match="outside East Africa Demo"):
            await seed_demo(session)
    country = await _kenya()
    demo = await _register(client, email="demo@example.com", tenant_name="East Africa Demo", company_name="Demo company", country_id=country.id)
    headers = auth_header(demo["access_token"])
    original = await vacancy(client, headers, demo["company"]["id"])
    async with get_session_maker()() as session:
        result = await seed_demo(session)
        await session.commit()
        assert result[0]["created"] is True
    async with get_session_maker()() as session:
        result = await seed_demo(session)
        await session.commit()
        assert result[0]["created"] is False
    view = (await client.get(f"/recruitment/workspace?company_id={demo['company']['id']}", headers=headers)).json()
    assert len(view["jobs"]) == 4
    assert next(j for j in view["jobs"] if j["id"] == original["id"])["title"] == original["title"]
    assert len(view["candidates"]) == 4 and len(view["applications"]) == 4
    assert view["offers"][0]["status"] == "ACCEPTED"
    assert {a["stage"] for a in view["applications"]} == {"APPLIED", "SHORTLISTED", "OFFER", "REJECTED"}
    assert (await client.get(f"/recruitment/workspace?company_id={w['company']['id']}", headers=owner)).json()["jobs"] == []
