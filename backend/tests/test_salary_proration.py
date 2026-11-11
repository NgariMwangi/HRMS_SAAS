from datetime import date
from decimal import Decimal

import pytest

from app.services.payroll_calc import calculate_payslip, salary_days
from tests.test_payroll_calc import _basic_plus, _gross, _kenya_nssf_pack
from tests.test_access import workspace
from tests.test_leave_requests import _person


@pytest.mark.parametrize("start,end,joined,expected", [
    ("2026-04-01", "2026-04-30", "2026-04-16", 15),
    ("2026-03-01", "2026-03-31", "2026-03-16", 16),
    ("2026-03-01", "2026-03-31", "2026-03-31", 1),
    ("2026-02-01", "2026-02-28", "2026-02-15", 14),
    ("2028-02-01", "2028-02-29", "2028-02-15", 15),
    ("2026-02-01", "2026-02-28", "2026-02-01", 30),
    ("2026-03-01", "2026-03-31", "2026-03-01", 30),
    ("2026-03-01", "2026-03-31", None, 30),
    ("2026-03-01", "2026-03-31", "2026-04-01", 0),
])
def test_calendar_days(start, end, joined, expected):
    assert salary_days(date.fromisoformat(start), date.fromisoformat(end),
                       date.fromisoformat(joined) if joined else None) == expected


@pytest.mark.parametrize("mixed", [True, False])
def test_prorated_salary_preserves_rate_and_recalculates_deductions(mixed):
    pay = _basic_plus("30000", [("Transport", "5000")]) if mixed else _gross("30000")
    pack = _kenya_nssf_pack()
    result = calculate_payslip(pack, pay, payable_days=15)
    gross = Decimal("20000" if mixed else "15000")
    assert result["gross"] == gross
    assert result["basic"] == (Decimal("15000") if mixed else None)
    assert result["employee_deductions"] == gross * Decimal("0.06")
    assert result["net"] == gross * Decimal("0.94")
    assert pay.computed_gross == Decimal("35000" if mixed else "30000")
    earnings = [line for line in result["lines"] if line["kind"] == "EARNING" and line["code"] not in {"GROSS", "TAXABLE"}]
    assert sum(line["amount"] for line in earnings) == gross
    assert "15/30 days" in earnings[0]["name"]


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_new_starter_run_review_rerun_and_next_month(client):
    w, owner = await workspace(client)
    company, branch = w["company"]["id"], w["branch"]["id"]
    for name, joined in [("Starter", "2026-04-16"), ("Future", "2026-05-01")]:
        person = await _person(client, owner, company, branch, name, f"{name.lower()}@example.com")
        updated = await client.patch(f"/employees/{person['id']}", headers=owner, json={"date_joined": joined})
        assert updated.status_code == 200, updated.text
        saved = await client.post(f"/employees/{person['id']}/compensation", headers=owner,
            json={"effective_from": "2026-01-01", "structure": "BASIC_PLUS_ALLOWANCES",
                  "basic_amount": "30000", "lines": [{"name": "Transport", "amount": "5000"}]})
        assert saved.status_code == 201, saved.text
    params = dict(company_id=company, branch_id=branch, period_end="2026-04-30")
    review = await client.get("/payroll/employees", headers=owner, params=params)
    assert review.status_code == 200, review.text
    assert next(p for p in review.json() if p["id"] == person["id"])["skip_reason"] == "Joining date is after this pay period"
    payload = {**params, "period_start": "2026-04-01"}
    for _ in range(2):
        response = await client.post("/payroll/runs", headers=owner, json=payload)
        assert response.status_code == 201, response.text
        run = response.json()
        assert run["skipped"] == 1
        assert len(run["payslips"]) == 1
        assert Decimal(run["payslips"][0]["basic"]) == Decimal("15000")
        assert Decimal(run["gross_total"]) == Decimal("20000")
    response = await client.post("/payroll/runs", headers=owner,
        json={**payload, "period_start": "2026-05-01", "period_end": "2026-05-31"})
    assert response.status_code == 201, response.text
    assert all(Decimal(p["basic"]) == Decimal("30000") for p in response.json()["payslips"])
