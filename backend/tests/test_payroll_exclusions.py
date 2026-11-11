from decimal import Decimal
import uuid
import pytest
from tests.test_access import workspace
from tests.test_leave_requests import _person
from tests.test_platform import _admin_login


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_payroll_exclusions_are_scoped_persisted_and_editable_on_rerun(client):
    w, owner = await workspace(client)
    company, branch = w["company"]["id"], w["branch"]["id"]
    a = await _person(client, owner, company, branch, "Included", "included@example.com")
    b = await _person(client, owner, company, branch, "Excluded", "excluded@example.com")
    foreign, foreign_owner = await workspace(client, "foreign-exclusions@example.com")
    outsider = await _person(client, foreign_owner, foreign["company"]["id"], foreign["branch"]["id"], "Other", "outside@example.com")
    for employee, gross in [(a, "100000"), (b, "50000")]:
        response = await client.post(f"/employees/{employee['id']}/compensation", headers=owner,
            json={"effective_from": "2026-01-01", "structure": "GROSS_ONLY", "gross_amount": gross})
        assert response.status_code == 201, response.text
    path = "/payroll/runs"
    body = dict(company_id=company, branch_id=branch, period_start="2026-03-01", period_end="2026-03-31")
    candidates = await client.get("/payroll/employees", headers=owner, params={"company_id": company,"branch_id": branch})
    assert candidates.status_code == 200
    assert {p["id"] for p in candidates.json()} == {a["id"], b["id"]}
    assert (await client.get("/payroll/employees", headers=foreign_owner, params={"company_id": company,"branch_id": branch})).status_code == 403
    result = await client.post(path, headers=owner, json={**body, "excluded_employee_ids": [b["id"],b["id"]]})
    assert result.status_code == 201, result.text
    run = result.json()
    assert run["excluded_employee_ids"] == [b["id"]]
    assert [p["employee_id"] for p in run["payslips"]] == [a["id"]]
    assert Decimal(run["gross_total"]) == Decimal("100000") and run["skipped"] == 0
    saved = (await client.get(f"{path}/{run['id']}", headers=owner)).json()
    assert saved["excluded_employee_ids"] == [b["id"]]
    # Omitted exclusions preserve a draft's choices, explicit [] re-includes everyone.
    repeated = await client.post(path, headers=owner, json=body)
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["excluded_employee_ids"] == [b["id"]]
    for invalid in [outsider["id"], str(uuid.uuid4())]:
        rejected = await client.post(path, headers=owner, json={**body, "excluded_employee_ids": [invalid]})
        assert rejected.status_code == 400, rejected.text
    unchanged = (await client.get(f"{path}/{run['id']}", headers=owner)).json()
    assert unchanged["excluded_employee_ids"] == [b["id"]] and len(unchanged["payslips"]) == 1
    cleared = await client.post(path, headers=owner, json={**body, "excluded_employee_ids": []})
    assert cleared.status_code == 201, cleared.text
    assert len(cleared.json()["payslips"]) == 2 and Decimal(cleared.json()["gross_total"]) == Decimal("150000")
    # A different period starts with no exclusions.
    next_month = await client.post(path, headers=owner, json={**body, "period_start":"2026-04-01", "period_end":"2026-04-30"})
    assert next_month.status_code == 201 and next_month.json()["excluded_employee_ids"] == []
    admin = await _admin_login(client)
    platform = f"/platform/tenants/{w['tenant']['id']}"
    listed = await client.get(platform + "/payroll/employees", headers=admin, params={"company_id": company,"branch_id": branch})
    assert listed.status_code == 200 and len(listed.json()) == 2
    switched = await client.post(platform + path, headers=admin, json={**body,"excluded_employee_ids":[a["id"]]})
    assert switched.status_code == 201, switched.text
    assert [p["employee_id"] for p in switched.json()["payslips"]] == [b["id"]]
    approved = await client.post(f"{path}/{run['id']}/approve", headers=owner)
    assert approved.status_code == 200
    assert (await client.post(path, headers=owner, json={**body,"excluded_employee_ids":[]})).status_code == 409
