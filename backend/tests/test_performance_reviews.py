from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from tests.test_access import workspace, staff_login
from tests.test_performance import setup_cycle

@pytest.mark.usefixtures("clean_tenant_tables")
async def test_review_goal_permissions_and_separate_self_window(client):
    data, hr = await workspace(client, "review-owner@example.com")
    company = data["company"]["id"]
    person, _, employee = await staff_login(client, hr, data, "ReviewEmployee")
    manager_person, _, manager = await staff_login(client, hr, data, "ReviewManager", "MANAGER")
    await setup_cycle(client, hr, company)
    today = datetime.now(ZoneInfo("Africa/Nairobi")).date()
    payload = {"name": "Simple review", "start_date": str(today - timedelta(days=10)), "end_date": str(today + timedelta(days=100)), "goal_entry_roles": ["HR"], "windows": {"SELF_ASSESSMENT": {"start": str(today + timedelta(days=1)), "end": str(today + timedelta(days=10))}}}
    response = await client.post(f"/performance/reviews?company_id={company}", headers=hr, json=payload)
    assert response.status_code == 201, response.text
    review = response.json()
    response = await client.post(f"/performance/reviews/{review['id']}/participants", headers=hr, json={"employee_ids": [person["id"]], "manager_id": manager_person["id"]})
    appraisal = response.json()[0]["appraisal_id"]
    async def action(kind):
        rows = (await client.get(f"/performance/reviews?company_id={company}", headers=hr)).json()
        current = next(row for row in rows if row["id"] == review["id"])
        return await client.post(f"/performance/reviews/{review['id']}/action", headers=hr, json={"version": current["version"], "status": kind})
    assert (await action("START")).status_code == 200
    goal_payload = {"title": "Deliver work", "weight": 100, "target": 100, "start_date": payload["start_date"], "due_date": payload["end_date"]}
    for actor in (employee, manager):
        assert (await client.post(f"/performance/appraisals/{appraisal}/goals", headers=actor, json=goal_payload)).status_code == 403
    response = await client.post(f"/performance/appraisals/{appraisal}/goals", headers=hr, json=goal_payload)
    assert response.status_code == 201, response.text
    goal = response.json()
    response = await client.post(f"/performance/goals/{goal['id']}/actions/submit", headers=hr, json={"version": goal["version"], "status": ""})
    goal = response.json()
    assert (await client.post(f"/performance/goals/{goal['id']}/actions/approve", headers=manager, json={"version": goal["version"], "status": ""})).status_code == 200
    assert (await action("TRACK")).status_code == 200
    assert (await action("SELF_REVIEW")).status_code == 409
    rows = (await client.get(f"/performance/reviews?company_id={company}", headers=hr)).json()
    current = next(row for row in rows if row["id"] == review["id"])
    assert current["status"] == "ACTIVE"
    payload["windows"]["SELF_ASSESSMENT"]["start"] = str(today)
    response = await client.put(f"/performance/reviews/{review['id']}", headers=hr, json={**payload, "version": current["version"], "reason": "Open scheduled self-review today"})
    assert response.status_code == 200, response.text
    result = await action("SELF_REVIEW")
    assert result.status_code == 200, result.text
    assert (await action("MANAGER_REVIEW")).status_code == 409
