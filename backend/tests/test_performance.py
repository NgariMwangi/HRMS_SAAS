from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.schemas.performance import CycleInput, ScaleInput, SettingsInput
from app.services.performance_scoring import automatic_rating, calculate, rating_for
from tests.test_access import staff_login, workspace

LEVELS = [
    {"value": "1", "label": "Unsatisfactory", "minimum": "1", "maximum": "1.99"},
    {"value": "2", "label": "Needs Improvement", "minimum": "2", "maximum": "2.99"},
    {"value": "3", "label": "Meets Expectations", "minimum": "3", "maximum": "3.99"},
    {"value": "4", "label": "Exceeds Expectations", "minimum": "4", "maximum": "4.49"},
    {"value": "5", "label": "Outstanding", "minimum": "4.50", "maximum": "5"},
]


def test_decimal_scoring_and_validation():
    goals = [SimpleNamespace(id=str(index), weight=Decimal(weight), title="KPI") for index, weight in enumerate([40, 20, 15, 10, 15])]
    config = {"kpi_weight": "70", "competency_weight": "30", "auto_scoring": False, "rating_scale": {"levels": LEVELS}}
    ratings = {"goals": [{"id": str(index), "rating": "4.2"} for index in range(5)], "competencies": [{"id": "c", "rating": "3.8"}]}
    scores = calculate(goals, [{"id": "c", "name": "Leadership", "weight": "1"}], ratings, config)
    assert scores["pre_calibration"] == "4.08"
    assert scores["pre_calibration_rating"] == "Exceeds Expectations"
    assert rating_for("4.5", LEVELS) == "Outstanding"
    with pytest.raises(ValueError):
        SettingsInput(kpi_weight=60, competency_weight=30)
    with pytest.raises(ValueError):
        ScaleInput(name="overlap", levels=[{"value": 1, "label": "a", "minimum": 0, "maximum": 2}, {"value": 2, "label": "b", "minimum": 2, "maximum": 3}])
    with pytest.raises(ValueError):
        CycleInput(name="Bad", start_date="2026-12-01", end_date="2026-01-01")


@pytest.mark.parametrize("direction,target,actual,progress", [("HIGHER_IS_BETTER", 0, 0, 0), ("HIGHER_IS_BETTER", 0, 10, 0), ("LOWER_IS_BETTER", 10, 0, 0), ("LOWER_IS_BETTER", 0, 1, 0), ("TARGET_IS_BEST", 0, 0, 0), ("TARGET_IS_BEST", -10, -10, 0), ("MILESTONE", 0, None, 100)])
def test_automatic_scoring_edges(direction, target, actual, progress):
    definition = {"measurement": "NUMBER", "direction": direction, "target": str(target), "scoring_cap": "120"}
    score = automatic_rating(definition, actual, progress, LEVELS)
    assert Decimal(1) <= score <= Decimal(5)
    other_scale = [{"minimum": "0", "maximum": "49.99", "label": "Low"}, {"minimum": "50", "maximum": "100", "label": "High"}]
    assert Decimal(0) <= automatic_rating(definition, actual, progress, other_scale) <= Decimal(100)


async def setup_cycle(client, headers, company_id, **settings):
    scale = await client.post(f"/performance/rating-scales?company_id={company_id}", headers=headers, json={"name": "Five levels", "levels": LEVELS})
    assert scale.status_code == 201, scale.text
    response = await client.put(f"/performance/settings?company_id={company_id}", headers=headers, json={"rating_scale_id": scale.json()["id"], **settings})
    assert response.status_code == 200, response.text
    competency = await client.post(f"/performance/competencies?company_id={company_id}", headers=headers, json={"name": "Leadership", "indicators": ["Supports colleagues"]})
    assert competency.status_code == 201, competency.text
    cycle = await client.post(f"/performance/cycles?company_id={company_id}", headers=headers, json={"name": "2026 Annual", "start_date": "2026-01-01", "end_date": "2026-12-31"})
    assert cycle.status_code == 201, cycle.text
    return cycle.json(), competency.json()


async def advance(client, headers, cycle_id, stage):
    # Get current optimistic version from list.
    from app.db.session import get_session_maker
    from app.models.performance import PerformanceCycle
    import uuid
    async with get_session_maker()() as session:
        cycle = await session.get(PerformanceCycle, uuid.UUID(cycle_id))
        version = cycle.version
    response = await client.post(f"/performance/cycles/{cycle_id}/transition", headers=headers, json={"version": version, "status": stage})
    assert response.status_code == 200, response.text


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_complete_appraisal_history_security_and_locking(client):
    data, owner = await workspace(client, "performance-owner@example.com")
    company = data["company"]["id"]
    john, john_user, employee = await staff_login(client, owner, data, "John")
    mary, mary_user, manager = await staff_login(client, owner, data, "Mary", "MANAGER")
    outsider, _, outsider_headers = await staff_login(client, owner, data, "Outside", "MANAGER")
    response = await client.put(f"/employees/{john['id']}/supervisors", headers=owner, json={"supervisor_ids": [mary["id"]]})
    assert response.status_code == 200, response.text
    cycle, competency = await setup_cycle(client, owner, company, require_calibration=True, employee_view_manager=False, pip_threshold="3")
    response = await client.post(f"/performance/cycles/{cycle['id']}/participants", headers=owner, json={"employee_ids": [john["id"]]})
    assert response.status_code == 201, response.text
    appraisal_id = response.json()[0]["appraisal_id"]
    assert response.json()[0]["manager_id"] == mary["id"]
    assert (await client.post(f"/performance/cycles/{cycle['id']}/participants", headers=owner, json={"employee_ids": [john["id"]]})).json() == []
    assert (await client.get(f"/performance/appraisals/{appraisal_id}", headers=outsider_headers)).status_code == 404
    assert (await client.post(f"/performance/cycles/{cycle['id']}/transition", headers=owner, json={"version": 1, "status": "ACTIVE"})).status_code == 409
    await advance(client, owner, cycle["id"], "GOAL_SETTING")
    goals = []
    for index, weight in enumerate([40, 20, 15, 10, 15]):
        response = await client.post(f"/performance/appraisals/{appraisal_id}/goals", headers=employee, json={"title": f"KPI {index}", "weight": weight, "target": 100, "start_date": "2026-01-01", "due_date": "2026-12-31"})
        assert response.status_code == 201, response.text
        goal = response.json()
        response = await client.post(f"/performance/goals/{goal['id']}/actions/submit", headers=employee, json={"version": goal["version"], "status": ""})
        assert response.status_code == 200, response.text
        pending = response.json()
        assert (await client.post(f"/performance/goals/{goal['id']}/actions/approve", headers=employee, json={"version": pending["version"], "status": ""})).status_code == 403
        approved = await client.post(f"/performance/goals/{goal['id']}/actions/approve", headers=manager, json={"version": pending["version"], "status": ""})
        assert approved.status_code == 200, approved.text
        goals.append(approved.json())
        if index == 0:
            invalid = await client.post(f"/performance/cycles/{cycle['id']}/transition", headers=owner, json={"version": 2, "status": "ACTIVE"})
            assert invalid.status_code == 400, invalid.text
    await advance(client, owner, cycle["id"], "ACTIVE")
    progress = await client.post(f"/performance/goals/{goals[0]['id']}/progress", headers=employee, json={"version": goals[0]["version"], "progress": 80, "actual": 95, "comment": "Achieved strong results"})
    assert progress.status_code == 200, progress.text
    assert (await client.post(f"/performance/goals/{goals[0]['id']}/progress", headers=employee, json={"version": goals[0]["version"], "progress": 90, "comment": "stale"})).status_code == 409
    history = await client.get(f"/performance/goals/{goals[0]['id']}/progress", headers=employee)
    assert history.json()[0]["details"]["previous"]["progress"] == "0.00"
    evidence = await client.post(f"/performance/goals/{goals[0]['id']}/evidence", headers=employee, files={"file": ("evidence.txt", b"evidence", "text/plain")})
    assert evidence.status_code == 201, evidence.text
    assert (await client.get(f"/performance/evidence/{evidence.json()['id']}/download", headers=outsider_headers)).status_code == 404
    assert (await client.get(f"/performance/evidence/{evidence.json()['id']}/download", headers=employee)).content == b"evidence"
    assert (await client.post(f"/performance/appraisals/{appraisal_id}/check-ins", headers=employee, json={"meeting_date": "2026-06-01", "achievements": "Progress", "goal_ids": [goals[0]["id"]]})).status_code == 201
    await advance(client, owner, cycle["id"], "SELF_ASSESSMENT")
    detail = (await client.get(f"/performance/appraisals/{appraisal_id}", headers=employee)).json()
    self_payload = {"version": detail["version"], "goals": [{"id": goal["id"], "rating": "4.5", "comment": "Employee view"} for goal in goals], "competencies": [{"id": competency["id"], "rating": "4"}], "summary": "My independent self-assessment"}
    response = await client.post(f"/performance/appraisals/{appraisal_id}/submit-self-assessment", headers=employee, json=self_payload)
    assert response.status_code == 200, response.text
    assert (await client.put(f"/performance/appraisals/{appraisal_id}/self-assessment", headers=employee, json={**self_payload, "version": response.json()["version"]})).status_code == 409
    await advance(client, owner, cycle["id"], "MANAGER_ASSESSMENT")
    detail = (await client.get(f"/performance/appraisals/{appraisal_id}", headers=manager)).json()
    manager_payload = {"version": detail["version"], "goals": [{"id": goal["id"], "rating": "4.2"} for goal in goals], "competencies": [{"id": competency["id"], "rating": "3.8"}], "summary": "Independent manager assessment"}
    response = await client.post(f"/performance/appraisals/{appraisal_id}/submit-manager-assessment", headers=manager, json=manager_payload)
    assert response.status_code == 200, response.text
    assert response.json()["scores"]["pre_calibration"] == "4.08"
    assert response.json()["self_assessment"]["summary"] == self_payload["summary"]
    own_detail = (await client.get(f"/performance/appraisals/{appraisal_id}", headers=employee)).json()
    assert own_detail["manager_assessment"] == {} and own_detail["scores"] == {}
    assert own_detail["manager_submitted"] is True
    await advance(client, owner, cycle["id"], "REVIEW")
    response = await client.get(f"/performance/appraisals/{appraisal_id}", headers=manager)
    response = await client.post(f"/performance/appraisals/{appraisal_id}/review", headers=manager, json={"version": response.json()["version"], "meeting_date": "2026-10-05", "summary": "Discussed goals", "attendees": ["John", "Mary"]})
    assert response.status_code == 200, response.text
    await advance(client, owner, cycle["id"], "CALIBRATION")
    response = await client.get(f"/performance/appraisals/{appraisal_id}", headers=owner)
    assert (await client.post(f"/performance/appraisals/{appraisal_id}/calibrate", headers=owner, json={"version": response.json()["version"], "score": "4.08", "reason": ""})).status_code == 422
    response = await client.post(f"/performance/appraisals/{appraisal_id}/calibrate", headers=owner, json={"version": response.json()["version"], "score": "4.08", "reason": "Consistent across department"})
    assert response.status_code == 200, response.text
    assert response.json()["scores"]["pre_calibration"] == "4.08"
    response = await client.post(f"/performance/appraisals/{appraisal_id}/acknowledge", headers=employee, json={"version": response.json()["version"], "status": "DISAGREES", "comments": "Received, with disagreement"})
    assert response.status_code == 200, response.text
    await advance(client, owner, cycle["id"], "FINALIZATION")
    response = await client.get(f"/performance/appraisals/{appraisal_id}", headers=owner)
    response = await client.post(f"/performance/appraisals/{appraisal_id}/finalize", headers=owner, json={"version": response.json()["version"]})
    assert response.status_code == 200, response.text
    assert response.json()["scores"]["final"] == "4.08"
    assert response.json()["scores"]["final_rating"] == "Exceeds Expectations"
    assert (await client.post(f"/performance/goals/{goals[1]['id']}/progress", headers=employee, json={"version": goals[1]["version"], "progress": 100, "comment": "late"})).status_code == 409
    from app.db.session import get_session_maker
    from app.models.performance import GoalEvidence
    from sqlalchemy import select
    import uuid
    async with get_session_maker()() as session:
        document_id = await session.scalar(select(GoalEvidence.document_id).where(GoalEvidence.id == uuid.UUID(evidence.json()["id"])))
    assert (await client.delete(f"/employees/{john['id']}/documents/{document_id}", headers=owner)).status_code == 409
    development = await client.post(f"/performance/appraisals/{appraisal_id}/development-actions", headers=manager, json={"title": "Leadership training", "owner_id": john["id"], "due_date": "2027-06-30", "action": "Complete training"})
    assert development.status_code == 201, development.text
    dashboard = (await client.get(f"/performance/dashboard?company_id={company}", headers=owner)).json()
    assert dashboard["average_score"] == "4.08" and dashboard["finalized"] == 1
    assert (await client.get(f"/performance/pips?company_id={company}", headers=manager)).status_code == 403
    assert (await client.get(f"/performance/reports/export?company_id={company}", headers=owner)).status_code == 200
    await advance(client, owner, cycle["id"], "COMPLETED")
    # Original employee name/context remain intact after personnel changes.
    assert (await client.patch(f"/employees/{john['id']}", headers=owner, json={"first_name": "Changed"})).status_code == 200
    assert (await client.get(f"/performance/appraisals/{appraisal_id}", headers=employee)).json()["participant"]["context"]["employee_name"].startswith("John")
    reopen = await client.post(f"/performance/appraisals/{appraisal_id}/reopen", headers=owner, json={"version": response.json()["version"], "reason": "Correct meeting record", "stage": "REVIEW"})
    assert reopen.status_code == 200, reopen.text
    assert reopen.json()["manager_assessment"]["submitted_at"]
    assert reopen.json()["scores"]["pre_calibration"] == "4.08" and "calibrated" not in reopen.json()["scores"]
    assert reopen.json()["review"] == {}
    assert any(item["action"] == "finalized" for item in reopen.json()["events"])
    finalized_event = next(item for item in reopen.json()["events"] if item["action"] == "finalized")
    assert finalized_event["details"]["participant"]["context"]["employee_name"].startswith("John")
    assert finalized_event["details"]["cycle"]["name"] == "2026 Annual"
    reopen = await client.post(f"/performance/appraisals/{appraisal_id}/reopen", headers=owner, json={"version": reopen.json()["version"], "reason": "Corrected manager evidence", "stage": "MANAGER_ASSESSMENT"})
    assert reopen.status_code == 200, reopen.text
    assert not reopen.json()["manager_assessment"].get("submitted_at")
    assert reopen.json()["self_assessment"]["submitted_at"]
    assert (await client.get(f"/performance/notifications?company_id={company}", headers=employee)).json()


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_cross_company_tenant_references_and_pip_workflow(client):
    data, owner = await workspace(client, "performance-scope@example.com")
    other, foreign = await workspace(client, "performance-foreign@example.com")
    person, _, employee = await staff_login(client, owner, data, "Scope")
    manager, _, _ = await staff_login(client, owner, data, "Appraiser", "MANAGER")
    foreign_person, _, _ = await staff_login(client, foreign, other, "Foreign")
    company = data["company"]["id"]
    cycle, _ = await setup_cycle(client, owner, company)
    assert (await client.post(f"/performance/cycles/{cycle['id']}/participants", headers=owner, json={"employee_ids": [foreign_person["id"]]})).status_code == 404
    assert (await client.post(f"/performance/cycles/{cycle['id']}/participants", headers=foreign, json={"employee_ids": [foreign_person["id"]]})).status_code == 404
    from tests.test_tenancy import _kenya
    country = await _kenya()
    second = await client.post("/companies", headers=owner, json={"name": "Second company"})
    assert second.status_code == 201, second.text
    assert (await client.post(f"/performance/competencies?company_id={second.json()['id']}", headers=owner, json={"name": "Bad assignment", "employee_ids": [person["id"]]})).status_code == 404
    pip = await client.post(f"/performance/pips?company_id={company}", headers=owner, json={"employee_id": person["id"], "manager_id": manager["id"], "hr_owner_id": data["user"]["id"], "start_date": "2026-10-01", "end_date": "2026-12-31", "reason": "Improve delivery", "issues": "Late reports", "objectives": [{"title": "Timeliness", "expected_standard": "By fifth day", "target": "All reports"}]})
    assert pip.status_code == 201, pip.text
    assert (await client.get(f"/performance/pips?company_id={company}", headers=employee)).status_code == 403
    response = await client.patch(f"/performance/pips/{pip.json()['id']}", headers=owner, json={"version": pip.json()["version"], "status": "ACTIVE", "reason": "HR approved"})
    assert response.status_code == 200, response.text
    review = await client.post(f"/performance/pips/{pip.json()['id']}/reviews", headers=owner, json={"meeting_date": "2026-10-05", "notes": "First review", "objective_progress": ["On track"]})
    assert review.status_code == 201, review.text
    response = await client.patch(f"/performance/pips/{pip.json()['id']}", headers=owner, json={"version": response.json()["version"], "status": "SUCCESSFUL", "reason": "Standards met", "outcome": "Delivered on time"})
    assert response.status_code == 200, response.text
    assert (await client.post(f"/performance/pips/{pip.json()['id']}/reviews", headers=owner, json={"meeting_date": "2026-10-05", "notes": "After closure"})).status_code == 409
    assert (await client.post(f"/performance/reminders?company_id={company}", headers=owner)).status_code == 200
    assert (await client.post(f"/performance/reminders?company_id={company}", headers=owner)).json()["notifications_created"] == 0


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_optional_stages_deadlines_snapshots_and_concurrent_updates(client):
    import asyncio
    from datetime import date, timedelta
    data, owner = await workspace(client, "performance-optional@example.com")
    person, _, employee = await staff_login(client, owner, data, "Optional")
    manager, _, _ = await staff_login(client, owner, data, "OptionalManager", "MANAGER")
    company = data["company"]["id"]
    original, _ = await setup_cycle(client, owner, company, kpi_weight="100", competency_weight="0", auto_scoring=True, require_self=False, require_manager=False, require_review=False, require_acknowledgement=False)
    current = date.today()
    payload = {"name": "Optional cycle", "frequency": "CUSTOM", "start_date": str(current - timedelta(days=60)), "end_date": str(current + timedelta(days=365)), "windows": {"SELF_ASSESSMENT": {"start": str(current + timedelta(days=10)), "end": str(current + timedelta(days=20))}}}
    cycle = (await client.post(f"/performance/cycles?company_id={company}", headers=owner, json=payload)).json()
    assigned = await client.post(f"/performance/cycles/{cycle['id']}/participants", headers=owner, json={"employee_ids": [person["id"]], "manager_id": manager["id"]})
    assert assigned.status_code == 201, assigned.text
    appraisal_id = assigned.json()[0]["appraisal_id"]
    await advance(client, owner, cycle["id"], "GOAL_SETTING")
    goal = await client.post(f"/performance/appraisals/{appraisal_id}/goals", headers=employee, json={"title": "Automatic KPI", "weight": "100", "target": "100", "start_date": str(current - timedelta(days=30)), "due_date": str(current + timedelta(days=100))})
    assert goal.status_code == 201, goal.text
    goal = goal.json()
    response = await client.post(f"/performance/goals/{goal['id']}/actions/submit", headers=employee, json={"version": goal["version"], "status": ""})
    assert response.status_code == 200, response.text
    response = await client.post(f"/performance/goals/{goal['id']}/actions/approve", headers=owner, json={"version": response.json()["version"], "status": ""})
    assert response.status_code == 200, response.text
    goal_version = response.json()["version"]
    await advance(client, owner, cycle["id"], "ACTIVE")
    results = await asyncio.gather(*[client.post(f"/performance/goals/{goal['id']}/progress", headers=employee, json={"version": goal_version, "progress": progress, "actual": "120", "comment": "Concurrent update"}) for progress in [80, 100]])
    assert sorted(response.status_code for response in results) == [200, 409]
    await advance(client, owner, cycle["id"], "SELF_ASSESSMENT")
    detail = (await client.get(f"/performance/appraisals/{appraisal_id}", headers=employee)).json()
    denied = await client.put(f"/performance/appraisals/{appraisal_id}/self-assessment", headers=employee, json={"version": detail["version"], "goals": [], "competencies": []})
    assert denied.status_code == 409 and "allowed dates" in denied.text
    # Repeated reminders are idempotent for the same deadline.
    await advance(client, owner, cycle["id"], "MANAGER_ASSESSMENT")
    await advance(client, owner, cycle["id"], "REVIEW")
    await advance(client, owner, cycle["id"], "FINALIZATION")
    # Editing the source scale/settings cannot rewrite a cycle snapshot.
    levels = [{**level, "label": f"New {level['label']}"} for level in LEVELS]
    scale_id = original["config"]["rating_scale"]["id"]
    assert (await client.put(f"/performance/rating-scales/{scale_id}", headers=owner, json={"name": "Updated scale", "levels": levels})).status_code == 200
    assert (await client.put(f"/performance/settings?company_id={company}", headers=owner, json={"rating_scale_id": scale_id, "kpi_weight": "0", "competency_weight": "100"})).status_code == 200
    detail = (await client.get(f"/performance/appraisals/{appraisal_id}", headers=owner)).json()
    response = await client.post(f"/performance/appraisals/{appraisal_id}/finalize", headers=owner, json={"version": detail["version"]})
    assert response.status_code == 200, response.text
    assert response.json()["scores"]["final"] == "5.00"
    assert response.json()["scores"]["final_rating"] == "Outstanding"
    assert response.json()["cycle"]["config"]["kpi_weight"] == "100"
