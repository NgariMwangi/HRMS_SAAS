import pytest
from tests.test_access import workspace, staff_login
from tests.test_platform import _admin_login


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_unapprove_preserves_run_and_reopens_rerun_with_access_checks(client, monkeypatch):
    w, owner = await workspace(client)
    person, _, employee = await staff_login(client, owner, w, "UnapproveEmployee")
    foreign, foreign_owner = await workspace(client, "foreign-unapprove@example.com")
    response = await client.post(f"/employees/{person['id']}/compensation", headers=owner,
        json={"effective_from":"2026-01-01", "structure":"GROSS_ONLY", "gross_amount":"100000"})
    assert response.status_code == 201, response.text
    body = dict(company_id=w["company"]["id"], branch_id=w["branch"]["id"],
        period_start="2026-03-01", period_end="2026-03-31")
    created = await client.post("/payroll/runs", headers=owner, json=body)
    assert created.status_code == 201, created.text
    run = created.json(); path = f"/payroll/runs/{run['id']}"
    slip = run["payslips"][0]
    own_pdf = f"/employee-portal/payslips/{slip['id']}/pdf"
    assert (await client.post(path + "/approve", headers=owner)).status_code == 200
    assert (await client.get(own_pdf, headers=employee)).status_code == 200
    assert (await client.post(path + "/unapprove", headers=employee)).status_code == 403
    assert (await client.post(path + "/unapprove", headers=foreign_owner)).status_code == 403
    assert (await client.post(path + "/unapprove")).status_code == 401
    result = await client.post(path + "/unapprove", headers=owner)
    assert result.status_code == 200, result.text
    draft = result.json()
    assert draft["status"] == "DRAFT" and len(draft["payslips"]) == len(run["payslips"])
    for saved, original in zip(draft["payslips"], run["payslips"]):
        assert {key:value for key,value in saved.items() if key != "lines"} == {key:value for key,value in original.items() if key != "lines"}
        assert {line["id"]:line for line in saved["lines"]} == {line["id"]:line for line in original["lines"]}
    assert draft["excluded_employee_ids"] == run["excluded_employee_ids"]
    assert draft["net_total"] == run["net_total"]
    assert (await client.get(own_pdf, headers=employee)).status_code == 404
    from app.api.routes import payslips
    async def send_draft(document):
        assert document["status"] == "DRAFT"
        return {"message":"Draft submitted"}
    monkeypatch.setattr(payslips, "send", send_draft)
    assert (await client.post(f"/payroll/payslips/{slip['id']}/email", headers=owner)).status_code == 200
    assert (await client.post(path + "/unapprove", headers=owner)).status_code == 200
    rerun = await client.post("/payroll/runs", headers=owner, json=body)
    assert rerun.status_code == 201 and rerun.json()["id"] == run["id"]
    assert (await client.post(path + "/approve", headers=owner)).status_code == 200
    admin = await _admin_login(client)
    platform = f"/platform/tenants/{w['tenant']['id']}{path}/unapprove"
    wrong = await client.post(f"/platform/tenants/{foreign['tenant']['id']}{path}/unapprove", headers=admin)
    assert wrong.status_code == 403, wrong.text
    final = await client.post(platform, headers=admin)
    assert final.status_code == 200 and final.json()["status"] == "DRAFT"
