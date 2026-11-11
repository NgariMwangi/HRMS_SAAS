from decimal import Decimal
from types import SimpleNamespace
import pytest
from app.services.payroll import payroll_skip_reason
from tests.test_access import workspace
from tests.test_leave_requests import _person
from tests.test_platform import _admin_login


@pytest.mark.parametrize("status,gross,reason", [
    ("ACTIVE", None, "No salary set for this pay period"),
    ("ACTIVE", "0", "Salary is zero or less"),
    ("ACTIVE", "-1", "Salary is zero or less"),
    ("SUSPENDED", "1000", "Employee status is suspended"),
    ("TERMINATED", None, "Employee status is terminated"),
    ("ACTIVE", "1000", None),
])
def test_actual_payroll_eligibility_reasons(status, gross, reason):
    pay = SimpleNamespace(computed_gross=Decimal(gross)) if gross is not None else None
    assert payroll_skip_reason(SimpleNamespace(status=status), pay) == reason


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_review_matches_salary_effective_date_and_actual_payroll(client):
    w, owner = await workspace(client)
    company, branch = w["company"]["id"], w["branch"]["id"]
    ready = await _person(client, owner, company, branch, "Ready", "ready@example.com")
    missing = await _person(client, owner, company, branch, "Missing", "missing@example.com")
    future = await _person(client, owner, company, branch, "Future", "future@example.com")
    for person, effective in [(ready, "2026-01-01"), (future, "2026-07-01")]:
        response = await client.post(f"/employees/{person['id']}/compensation", headers=owner,
            json={"effective_from": effective, "structure":"GROSS_ONLY", "gross_amount":"50000"})
        assert response.status_code == 201, response.text
    params = dict(company_id=company, branch_id=branch, period_end="2026-03-31")
    response = await client.get("/payroll/employees", headers=owner, params=params)
    assert response.status_code == 200, response.text
    people = {p["id"]:p for p in response.json()}
    assert people[ready["id"]]["eligible"] and people[ready["id"]]["skip_reason"] is None
    for person in [missing, future]:
        assert not people[person["id"]]["eligible"]
        assert people[person["id"]]["skip_reason"] == "No salary set for this pay period"
    admin = await _admin_login(client)
    platform = await client.get(f"/platform/tenants/{w['tenant']['id']}/payroll/employees", headers=admin, params=params)
    assert platform.status_code == 200 and platform.json() == response.json()
    later = await client.get("/payroll/employees", headers=owner, params={**params,"period_end":"2026-07-31"})
    assert next(p for p in later.json() if p["id"] == future["id"])["eligible"]
    run = await client.post("/payroll/runs", headers=owner, json={**params,"period_start":"2026-03-01"})
    assert run.status_code == 201, run.text
    assert [p["employee_id"] for p in run.json()["payslips"]] == [ready["id"]]
    assert run.json()["skipped"] == 2
