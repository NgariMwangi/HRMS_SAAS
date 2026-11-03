"""End-to-end coverage for the replacement workflow and its authorization boundaries."""
import asyncio
from datetime import date, timedelta
import pytest
from tests.test_access import workspace, staff_login

BASE = "/performance/simple"


async def request(client, method, path, headers, body=None, expected=200):
    response = await client.request(method, BASE + path, headers=headers, json=body)
    assert response.status_code == expected, (path, response.text)
    return response.json()


async def setup(client, preparation="HR", weighted=False):
    w, hr = await workspace(client)
    manager, _, mh = await staff_login(client, hr, w, "Appraiser", "MANAGER")
    alice, _, ah = await staff_login(client, hr, w, "Appraisee")
    bob, _, bh = await staff_login(client, hr, w, "Colleague")
    for person in (alice, bob):
        response = await client.put(f"/employees/{person['id']}/supervisors", headers=hr, json={"supervisor_ids": [manager["id"]]})
        assert response.status_code == 200, response.text
    criteria = [dict(id="objective", section="OBJECTIVE", title="Customer retention", expected="Retain 90% of customers", evidence="Customer records", weight=100 if weighted else 0),
        dict(id="behaviour", section="BEHAVIOUR", title="Teamwork", expected="Share timely handovers")]
    cid = w["company"]["id"]
    template = await request(client, "POST", f"/templates?company_id={cid}", hr, dict(name="Sales staff", weighted=weighted, criteria=criteria), 201)
    period = date.today() - timedelta(days=120)
    review_data = dict(name="Half-year appraisal", start_date=str(period), end_date=str(period + timedelta(days=30)),
        employee_deadline=str(period + timedelta(days=40)), manager_deadline=str(period + timedelta(days=50)),
        acknowledgement_deadline=str(date.today() + timedelta(days=10)), template_id=template["id"], preparation=preparation, employee_ids=[alice["id"], bob["id"]])
    review = await request(client, "POST", f"/reviews?company_id={cid}", hr, review_data, 201)
    records = await request(client, "GET", f"/records?company_id={cid}&scope=manage", hr)
    return dict(w=w, hr=hr, manager=manager, mh=mh, alice=alice, ah=ah, bob=bob, bh=bh, cid=cid, template=template,
        review=review, review_data=review_data, records=records)


async def ready_and_publish(client, s):
    ready = []
    for r in s["records"]:
        ready.append(await request(client, "PUT", f"/records/{r['id']}/prepare", s["hr"], dict(version=r["version"], manager_id=r["manager_id"], criteria=r["criteria"], ready=True)))
    await request(client, "POST", f"/reviews/{s['review']['id']}/publish", s["hr"], dict(version=s["review"]["version"]))
    records = await request(client, "GET", f"/records?company_id={s['cid']}&scope=manage", s["hr"])
    return next(r for r in records if r["employee_id"] == s["alice"]["id"])


def assessment(record, manager=False, submit=True):
    return dict(version=record["version"], responses=[dict(criterion_id=c["id"], comment="Specific supporting evidence", rating=(4 if c["section"] == "OBJECTIVE" else 3) if manager else None) for c in record["criteria"]], achievements="Retained customers", summary="Good overall performance" if manager else "", submit=submit)


async def advance_to_hr(client, s, r):
    r = await request(client, "PUT", f"/records/{r['id']}/self-review", s["ah"], assessment(r))
    r = await request(client, "PUT", f"/records/{r['id']}/manager-review", s["mh"], assessment(r, True))
    r = await request(client, "PUT", f"/records/{r['id']}/discussion", s["mh"], dict(version=r["version"], meeting_date=str(date.today()), summary="Discussed evidence, strengths and support.", actions=[dict(id="training", title="Complete negotiation training", owner_id=s["alice"]["id"], due_date=str(date.today() + timedelta(days=30)))], submit=True))
    return r


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_independent_appraisal_workflow_privacy_scores_and_history(client):
    s = await setup(client, weighted=True)
    r = await ready_and_publish(client, s)
    # Draft self-review cannot be read by HR or the manager.
    draft = assessment(r, submit=False)
    draft["achievements"] = "PRIVATE DRAFT"
    r = await request(client, "PUT", f"/records/{r['id']}/self-review", s["ah"], draft)
    for headers in (s["hr"], s["mh"]):
        assert (await request(client, "GET", f"/records/{r['id']}", headers))["self_review"] == {}
    r = await advance_to_hr(client, s, r)
    employee_view = await request(client, "GET", f"/records/{r['id']}", s["ah"])
    assert employee_view["manager_review"] == employee_view["result"] == employee_view["discussion"] == {}
    assert all("previous" not in item for item in employee_view["history"])
    assert r["result"]["score"] == "3.70"
    other = await request(client, "GET", f"/records?company_id={s['cid']}&scope=my", s["bh"])
    assert other[0]["status"] == "SELF_REVIEW"  # No whole-company stage switch.
    # HR cannot edit manager ratings; it can publish or return them.
    await request(client, "PUT", f"/records/{r['id']}/manager-review", s["hr"], assessment(r, True), 403)
    r = await request(client, "POST", f"/records/{r['id']}/action", s["hr"], dict(version=r["version"], action="PUBLISH"))
    employee_view = await request(client, "GET", f"/records/{r['id']}", s["ah"])
    assert employee_view["result"]["score"] == "3.70"
    # HR cannot close prematurely, and disagreement still completes receipt.
    await request(client, "POST", f"/records/{r['id']}/action", s["hr"], dict(version=r["version"], action="CLOSE", reason="No reply"), 403)
    await request(client, "POST", f"/records/{r['id']}/action", s["ah"], dict(version=r["version"], action="ACKNOWLEDGE", agrees=False), 400)
    r = await request(client, "POST", f"/records/{r['id']}/action", s["ah"], dict(version=r["version"], action="ACKNOWLEDGE", agrees=False, reason="I disagree with the teamwork rating"))
    assert r["status"] == "COMPLETED" and r["acknowledgement"]["agrees"] is False
    await request(client, "PUT", f"/records/{r['id']}/manager-review", s["mh"], assessment(r, True), 403)
    r = await request(client, "PATCH", f"/records/{r['id']}/development", s["ah"], dict(version=r["version"], action_id="training", status="COMPLETED"))
    assert r["status"] == "COMPLETED" and r["discussion"]["actions"][0]["status"] == "COMPLETED"
    csv = await client.get(BASE + f"/export?company_id={s['cid']}", headers=s["hr"])
    assert csv.status_code == 200 and "3.70" in csv.text
    r = await request(client, "POST", f"/records/{r['id']}/action", s["hr"], dict(version=r["version"], action="REOPEN", reason="Correct supporting evidence"))
    assert r["status"] == "MANAGER_REVIEW" and r["result"] == {} and r["acknowledgement"] == {}
    assert any(h["action"] == "acknowledge" for h in r["history"])


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_preparation_assignments_templates_company_scope_and_concurrent_versions(client):
    s = await setup(client, preparation="MANAGER")
    records = s["records"]; r = next(r for r in records if r["employee_id"] == s["alice"]["id"])
    assert r["manager_id"] == s["manager"]["id"]
    assert (await request(client, "GET", f"/records?company_id={s['cid']}&scope=my", s["ah"])) == []
    await request(client, "GET", f"/records/{r['id']}", s["ah"], expected=404)
    await request(client, "POST", f"/reviews/{s['review']['id']}/publish", s["hr"], dict(version=s["review"]["version"]), 400)
    await request(client, "PUT", f"/records/{r['id']}/prepare", s["hr"], dict(version=r["version"], manager_id=s["alice"]["id"], criteria=r["criteria"], ready=True), 400)
    changed = [{**c, "expected": "Mary's individual target"} if c["section"] == "OBJECTIVE" else c for c in r["criteria"]]
    body = dict(version=r["version"], manager_id=r["manager_id"], criteria=changed, ready=True)
    # Two identical competing writes: one succeeds, one sees the newer version.
    responses = await asyncio.gather(*(client.put(BASE + f"/records/{r['id']}/prepare", headers=s["mh"], json=body) for _ in range(2)))
    assert sorted(resp.status_code for resp in responses) == [200, 409], [resp.text for resp in responses]
    r = next(resp.json() for resp in responses if resp.status_code == 200)
    bob = next(r for r in records if r["employee_id"] == s["bob"]["id"])
    assert (await request(client, "GET", f"/records/{bob['id']}", s["hr"]))["criteria"][0]["expected"] != "Mary's individual target"
    # Editing the reusable template does not rewrite a review snapshot or individual form.
    template = s["template"]
    await request(client, "PUT", f"/templates/{template['id']}?company_id={s['cid']}", s["hr"], dict(name="Changed template", weighted=False, criteria=[{**c, "title": "Changed"} for c in template["criteria"]], version=template["version"]))
    assert (await request(client, "GET", f"/records/{r['id']}", s["hr"]))["criteria"][0]["title"] == "Customer retention"
    foreign, fh = await workspace(client, "appraisal-foreign@example.com")
    await request(client, "GET", f"/records/{r['id']}", fh, expected=404)
    await request(client, "GET", f"/records?company_id={s['cid']}&scope=manage", fh, expected=403)
    await request(client, "GET", f"/templates?company_id={s['cid']}", s["ah"], expected=403)
    await request(client, "GET", f"/records?company_id={foreign['company']['id']}&scope=my", s["ah"], expected=403)
    # An employee in another company of the same tenant cannot be an appraiser.
    other = await client.post("/companies", headers=s["hr"], json={"name": "Other company"})
    from tests.test_leave_requests import _person
    branch = await client.post("/branches", headers=s["hr"], json={"company_id": other.json()["id"], "country_id": s["w"]["branch"]["country_id"], "name": "Other", "code": "OTHER"})
    outsider = await _person(client, s["hr"], other.json()["id"], branch.json()["id"], "OtherCompany", "other-company@example.com")
    await request(client, "PUT", f"/records/{r['id']}/prepare", s["hr"], dict(version=r["version"], manager_id=outsider["id"], criteria=r["criteria"], ready=True), 400)


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_returns_and_deadline_closure_preserve_employee_input(client):
    s = await setup(client)
    # Past acknowledgement deadline explicitly allows HR closure without forging receipt.
    data = {**s["review_data"], "acknowledgement_deadline": s["review_data"]["manager_deadline"], "version": s["review"]["version"]}
    s["review"] = await request(client, "PUT", f"/reviews/{s['review']['id']}?company_id={s['cid']}", s["hr"], data)
    r = await ready_and_publish(client, s)
    r = await request(client, "PUT", f"/records/{r['id']}/self-review", s["ah"], assessment(r))
    r = await request(client, "POST", f"/records/{r['id']}/action", s["mh"], dict(version=r["version"], action="RETURN_SELF", reason="Add supporting examples"))
    assert r["status"] == "SELF_REVIEW" and not r["self_review"].get("submitted_at")
    own = await request(client, "GET", f"/records/{r['id']}", s["ah"])
    assert own["self_review"]["achievements"] == "Retained customers"
    r = await advance_to_hr(client, s, r)
    r = await request(client, "POST", f"/records/{r['id']}/action", s["hr"], dict(version=r["version"], action="RETURN_MANAGER", reason="Clarify evidence"))
    assert r["status"] == "MANAGER_REVIEW"
    r = await request(client, "PUT", f"/records/{r['id']}/manager-review", s["mh"], assessment(r, True))
    r = await request(client, "PUT", f"/records/{r['id']}/manager-review", s["mh"], assessment(r, True, submit=False))
    assert r["status"] == "MANAGER_REVIEW" and r["result"] == {}
    await request(client, "PUT", f"/records/{r['id']}/discussion", s["mh"], dict(version=r["version"], meeting_date=str(date.today()), summary="Must resubmit ratings first", submit=True), 403)
    r = await request(client, "PUT", f"/records/{r['id']}/manager-review", s["mh"], assessment(r, True))
    r = await request(client, "PUT", f"/records/{r['id']}/discussion", s["mh"], dict(version=r["version"], meeting_date=str(date.today()), summary="Updated discussion", submit=True))
    r = await request(client, "POST", f"/records/{r['id']}/action", s["hr"], dict(version=r["version"], action="PUBLISH"))
    r = await request(client, "POST", f"/records/{r['id']}/action", s["hr"], dict(version=r["version"], action="CLOSE", reason="Employee did not respond after reminders"))
    assert r["status"] == "COMPLETED" and r["acknowledgement"]["received"] is False
    bob = (await request(client, "GET", f"/records?company_id={s['cid']}&scope=my", s["bh"]))[0]
    bob = await advance_to_hr(client, {**s, "ah": s["bh"], "alice": s["bob"]}, bob)
    bob = await request(client, "POST", f"/records/{bob['id']}/action", s["hr"], dict(version=bob["version"], action="PUBLISH"))
    bob = await request(client, "POST", f"/records/{bob['id']}/action", s["bh"], dict(version=bob["version"], action="ACKNOWLEDGE"))
    assert bob["review"]["status"] == "COMPLETED"


def test_fixed_scale_scoring_validation():
    from types import SimpleNamespace
    from app.services.appraisals import score, validate_form
    from fastapi import HTTPException
    criteria = [dict(id="a", section="OBJECTIVE", title="Sales", expected="20 customers", weight="60"), dict(id="b", section="OBJECTIVE", title="Retention", expected="90%", weight="40"), dict(id="c", section="BEHAVIOUR", title="Teamwork", expected="Timely handovers")]
    validate_form(criteria, True)
    record = SimpleNamespace(criteria=criteria, manager_review=dict(responses=[dict(criterion_id="a", rating=5), dict(criterion_id="b", rating=3), dict(criterion_id="c", rating=4)]))
    assert score(record, SimpleNamespace(template_snapshot={"weighted": True}))["score"] == "4.14"
    with pytest.raises(HTTPException):
        validate_form([{**criteria[0], "weight": "30"}, criteria[1]], True)


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_report_only_privacy_domain_scope_publication_accounts_and_reminders(client):
    import uuid
    from app.db.session import get_session_maker
    from app.models import User
    from app.services.appraisals import reminders
    s = await setup(client)
    users = (await client.get("/access/users", headers=s["hr"])).json()
    manager_user = next(u for u in users if u["employee_id"] == s["manager"]["id"])
    bob_user = next(u for u in users if u["employee_id"] == s["bob"]["id"])
    viewer = (await client.post("/access/roles", headers=s["hr"], json={"name": "Appraisal summaries", "permissions": ["performance.view_reports"]})).json()
    await client.patch(f"/access/users/{manager_user['id']}", headers=s["hr"], json={"role": viewer["key"]})
    for r in s["records"]:
        await request(client, "PUT", f"/records/{r['id']}/prepare", s["hr"], dict(version=r["version"], manager_id=r["manager_id"], criteria=r["criteria"], ready=True))
    await request(client, "POST", f"/reviews/{s['review']['id']}/publish", s["hr"], dict(version=s["review"]["version"]), 400)
    await client.patch(f"/access/users/{manager_user['id']}", headers=s["hr"], json={"role": "MANAGER"})
    await request(client, "POST", f"/reviews/{s['review']['id']}/publish", s["hr"], dict(version=s["review"]["version"]))
    records = await request(client, "GET", f"/records?company_id={s['cid']}&scope=manage", s["hr"])
    r = next(r for r in records if r["employee_id"] == s["alice"]["id"])
    await client.patch(f"/access/users/{bob_user['id']}", headers=s["hr"], json={"role": viewer["key"]})
    r = await advance_to_hr(client, s, r)
    summaries = await request(client, "GET", f"/results?company_id={s['cid']}", s["bh"])
    assert all(item["manager_review"] == item["self_review"] == item["result"] == {} for item in summaries)
    await request(client, "GET", f"/records/{r['id']}", s["bh"], expected=404)
    await request(client, "GET", f"/records?company_id={s['cid']}&scope=manage", s["bh"], expected=403)
    r = await request(client, "POST", f"/records/{r['id']}/action", s["hr"], dict(version=r["version"], action="PUBLISH"))
    summaries = await request(client, "GET", f"/results?company_id={s['cid']}", s["bh"])
    summary = next(item for item in summaries if item["id"] == r["id"])
    assert summary["result"]["score"] == "3.70" and summary["manager_review"] == {}
    # Reminder keys are stable, even though the employee record may have been saved repeatedly.
    async with get_session_maker()() as session:
        actor = await session.get(User, uuid.UUID(s["w"]["user"]["id"]))
        first = await reminders(session, actor, uuid.UUID(s["cid"]))
        second = await reminders(session, actor, uuid.UUID(s["cid"]))
        assert first["notifications_created"] >= 1 and second["notifications_created"] == 0
        await session.commit()
    domains = (await client.get(f"/domains?company_id={s['cid']}", headers=s["hr"])).json()
    bound = {**s["hr"], "Host": domains[0]["hostname"]}
    assert (await request(client, "GET", f"/records/{r['id']}", bound))["id"] == r["id"]
    other_company = (await client.post("/companies", headers=s["hr"], json={"name": "Isolated company"})).json()
    await request(client, "GET", f"/records?company_id={other_company['id']}&scope=manage", bound, expected=403)
