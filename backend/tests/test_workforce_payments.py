import asyncio
from decimal import Decimal
import pytest
from tests.test_access import workspace, staff_login
from tests.test_leave_requests import _person
from tests.test_platform import _admin_login


async def salary(client, owner, employee_id):
    response = await client.post(f"/employees/{employee_id}/compensation", headers=owner,
        json={"effective_from": "2026-01-01", "structure": "BASIC_PLUS_ALLOWANCES", "basic_amount": "30000", "lines": []})
    assert response.status_code == 201, response.text


async def run(client, owner, w):
    response = await client.post("/payroll/runs", headers=owner, json={"company_id": w["company"]["id"],
        "branch_id": w["branch"]["id"], "period_start": "2026-04-01", "period_end": "2026-04-30"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_bank_settings_proration_permission_and_platform(client):
    w, owner = await workspace(client)
    person, _, employee_auth = await staff_login(client, owner, w, "Bank")
    endpoint = f"/employees/{person['id']}/pay-settings"
    assert (await client.get(endpoint, headers=employee_auth)).status_code == 403
    assert (await client.get("/workforce/consultants", headers=employee_auth, params={"company_id": w["company"]["id"]})).status_code == 403
    response = await client.patch(endpoint, headers=owner, json={"bank_name": " Bank ", "bank_account_number": "001234", "swift_code": " ", "prorate_payroll": False})
    assert response.status_code == 200, response.text
    assert response.json()["bank_account_number"] == "001234"
    assert response.json()["bank_name"] == "Bank"
    assert response.json()["swift_code"] is None
    # Financial fields never leak through the general employee list.
    general = await client.get(f"/employees/{person['id']}", headers=owner)
    assert "bank_account_number" not in general.json()
    assert (await client.patch(endpoint, headers=owner, json={"prorate_payroll": None})).status_code == 422
    await client.patch(f"/employees/{person['id']}", headers=owner, json={"date_joined": "2026-04-16"})
    await salary(client, owner, person["id"])
    assert Decimal((await run(client, owner, w))["payslips"][0]["basic"]) == Decimal("30000")
    await client.patch(endpoint, headers=owner, json={"prorate_payroll": True})
    assert Decimal((await run(client, owner, w))["payslips"][0]["basic"]) == Decimal("15000")
    _, other = await workspace(client, "other-bank@example.com")
    assert (await client.get(endpoint, headers=other)).status_code in (403, 404)
    admin = await _admin_login(client)
    response = await client.get(f"/platform/tenants/{w['tenant']['id']}{endpoint}", headers=admin)
    assert response.status_code == 200 and response.json()["bank_account_number"] == "001234"


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_consultant_fee_calculation_approval_and_payment_history(client):
    w, owner = await workspace(client)
    created = await client.post("/workforce/consultants", headers=owner, json={"company_id": w["company"]["id"],
        "branch_id": w["branch"]["id"], "consultant_number": "C001", "first_name": "Consultant", "last_name": "One",
        "start_date": "2026-04-16", "withholding_rate": "5", "bank_account_number": "00123"})
    assert created.status_code == 201, created.text
    person = created.json()
    fee = await client.post(f"/workforce/consultants/{person['id']}/fees", headers=owner,
        json={"effective_from": "2026-01-01", "monthly_fee": "30000", "other_allowances": "0"})
    assert fee.status_code == 201, fee.text
    calc = f"/workforce/consultants/{person['id']}/calculate"
    response = await client.post(calc, headers=owner, json={"month": "2026-04-01"})
    assert response.status_code == 200, response.text
    pay = response.json()
    assert Decimal(pay["gross"]) == Decimal("15000")
    assert Decimal(pay["withholding_tax"]) == Decimal("750")
    assert Decimal(pay["net"]) == Decimal("14250")
    payload = {"kind": "CONSULTANT", "target_id": pay["id"], "month": "2026-04-01", "paid_on": "2026-04-30",
        "method": "BANK", "reference": "REF001", "amount": "10000"}
    assert (await client.post("/workforce/payments", headers=owner, json=payload)).status_code == 400
    response = await client.post(f"/workforce/consultant-pay/{pay['id']}/approve", headers=owner)
    assert response.status_code == 200, response.text
    assert (await client.post(calc, headers=owner, json={"month": "2026-04-01"})).status_code == 409
    concurrent = await asyncio.gather(
        client.post("/workforce/payments", headers=owner, json=payload),
        client.post("/workforce/payments", headers=owner, json={**payload, "reference": "CONCURRENT"}),
    )
    assert sorted(result.status_code for result in concurrent) == [201, 409], [r.text for r in concurrent]
    response = next(result for result in concurrent if result.status_code == 201)
    payment = response.json()
    assert (await client.post("/workforce/payments", headers=owner, json={**payload, "reference": "OVER", "amount": "5000"})).status_code == 409
    assert (await client.post("/workforce/payments", headers=owner, json={**payload, "reference": payment["reference"], "amount": "100"})).status_code == 409
    response = await client.post(f"/workforce/payments/{payment['id']}/void", headers=owner, json={"reason": "Bank reversed transfer"})
    assert response.status_code == 200 and response.json()["status"] == "VOID"
    response = await client.post("/workforce/payments", headers=owner, json={**payload, "reference": "REPLACEMENT", "amount": "14250"})
    assert response.status_code == 201, response.text
    params = {"company_id": w["company"]["id"], "month": "2026-04-01"}
    targets = await client.get("/workforce/payment-targets", headers=owner, params=params)
    assert targets.status_code == 200, targets.text
    assert Decimal(targets.json()[0]["outstanding"]) == 0
    ledger = await client.get("/workforce/payments", headers=owner, params=params)
    assert len(ledger.json()) == 2
    _, other = await workspace(client, "other-consultant@example.com")
    assert (await client.get(f"/workforce/consultants/{person['id']}/fees", headers=other)).status_code == 404
    admin = await _admin_login(client)
    result = await client.get(f"/platform/tenants/{w['tenant']['id']}/workforce/payments", headers=admin, params=params)
    assert result.status_code == 200 and result.json() == ledger.json()


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_overtime_payroll_integration_and_payroll_payment_lock(client):
    w, owner = await workspace(client)
    person = await _person(client, owner, w["company"]["id"], w["branch"]["id"], "Overtime", "overtime@example.com")
    await salary(client, owner, person["id"])
    original = await run(client, owner, w)
    payload = {"employee_id": person["id"], "worked_dates": ["2026-04-10"], "days": "0.5", "daily_rate": "2000", "month": "2026-04-01"}
    response = await client.post("/workforce/overtime", headers=owner, json=payload)
    assert response.status_code == 201, response.text
    ot = response.json()
    assert Decimal(ot["amount"]) == Decimal("1000")
    assert (await client.post("/workforce/overtime", headers=owner, json=payload)).status_code == 409
    for _ in range(2):
        response = await client.post(f"/workforce/overtime/{ot['id']}/review", headers=owner, json={"decision": "APPROVED", "note": "Checked"})
        assert response.status_code == 200, response.text
    recalculated = await run(client, owner, w)
    assert Decimal(recalculated["gross_total"]) == Decimal("31000")
    assert len([line for line in recalculated["payslips"][0]["lines"] if line["code"] == "BENEFIT"]) == 1
    response = await client.post(f"/payroll/runs/{original['id']}/approve", headers=owner)
    assert response.status_code == 200, response.text
    response = await client.post("/workforce/payments", headers=owner, json={"kind": "PAYROLL", "target_id": recalculated["payslips"][0]["id"],
        "month": "2026-04-01", "paid_on": "2026-04-30", "method": "MPESA", "reference": "PAYROLL001", "amount": "1000"})
    assert response.status_code == 201, response.text
    assert (await client.post(f"/payroll/runs/{original['id']}/unapprove", headers=owner)).status_code == 409
    later = await client.post("/workforce/overtime", headers=owner, json={**payload, "worked_dates": ["2026-04-11"]})
    assert later.status_code == 201, later.text
    assert (await client.post(f"/workforce/overtime/{later.json()['id']}/review", headers=owner, json={"decision": "APPROVED"})).status_code == 409


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_external_benefit_payment_not_paid_again_in_payroll(client):
    w, owner = await workspace(client)
    person = await _person(client, owner, w["company"]["id"], w["branch"]["id"], "Benefit", "benefit@example.com")
    await salary(client, owner, person["id"])
    response = await client.post(f"/employees/{person['id']}/benefits", headers=owner, json={"title": "Reimbursement",
        "frequency": "ONE_OFF", "amount": "5000", "start_date": "2026-04-01", "status": "ACTIVE"})
    assert response.status_code == 201, response.text
    benefit = response.json()
    payload = {"kind": "BENEFIT", "target_id": benefit["id"], "month": "2026-04-01", "paid_on": "2026-04-04",
        "method": "BANK", "reference": "BENEFIT001", "amount": "5000"}
    response = await client.post("/workforce/payments", headers=owner, json=payload)
    assert response.status_code == 201, response.text
    prepaid_run = await run(client, owner, w)
    assert Decimal(prepaid_run["gross_total"]) == Decimal("35000")
    assert any(line["code"] == "PREPAID_BENEFIT" and Decimal(line["amount"]) == 5000 for line in prepaid_run["payslips"][0]["lines"])
    benefit_rows = await client.get(f"/employees/{person['id']}/benefits", headers=owner)
    assert benefit_rows.status_code == 200, benefit_rows.text
    assert Decimal(benefit_rows.json()[0]["paid"]) == Decimal("5000")
    voided = await client.post(f"/workforce/payments/{response.json()['id']}/void", headers=owner, json={"reason": "Transfer failed"})
    assert voided.status_code == 200, voided.text
    unpaid_run = await run(client, owner, w)
    assert Decimal(unpaid_run["gross_total"]) == Decimal("35000")
    assert Decimal(unpaid_run["net_total"]) - Decimal(prepaid_run["net_total"]) == Decimal("5000")
    assert (await client.post("/workforce/payments", headers=owner, json={**payload, "reference": "DOUBLE"})).status_code == 409
