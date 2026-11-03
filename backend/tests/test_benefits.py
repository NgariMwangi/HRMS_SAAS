from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.test_deductions import _run, _salary, _tenant
from tests.test_leave_requests import _person


def _benefit_lines(slip: dict) -> dict[str, Decimal]:
    return {line["name"]: Decimal(line["amount"]) for line in slip["lines"] if line["code"] == "BENEFIT"}


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_one_off_and_ranged_benefits_raise_gross_in_their_periods(client: AsyncClient) -> None:
    headers, company_id, branch_id = await _tenant(client, "benefits@example.com")
    person = await _person(client, headers, company_id, branch_id, "Wanjiru", "wanjiru.benefit@example.com")
    await _salary(client, headers, person["id"], "50000")

    commission = await client.post(
        "/benefit-types",
        headers=headers,
        json={"company_id": company_id, "name": "Commission"},
    )
    assert commission.status_code == 201, commission.text
    bonus = await client.post(
        "/benefit-types",
        headers=headers,
        json={"company_id": company_id, "name": "Bonus", "default_amount": "5000"},
    )
    assert bonus.status_code == 201, bonus.text
    assert Decimal(bonus.json()["default_amount"]) == Decimal("5000")
    duplicate = await client.post(
        "/benefit-types",
        headers=headers,
        json={"company_id": company_id, "name": "commission"},
    )
    assert duplicate.status_code == 409

    ranged = await client.post(
        f"/employees/{person['id']}/benefits",
        headers=headers,
        json={
            "benefit_type_id": commission.json()["id"],
            "note": "Q1 sales",
            "frequency": "RECURRING",
            "amount": "20000",
            "start_date": "2026-01-01",
            "end_date": "2026-02-28",
        },
    )
    assert ranged.status_code == 201, ranged.text
    assert ranged.json()["type_name"] == "Commission"
    one_off = await client.post(
        f"/employees/{person['id']}/benefits",
        headers=headers,
        json={
            "benefit_type_id": bonus.json()["id"],
            "frequency": "ONE_OFF",
            "amount": "5000",
            "start_date": "2026-02-10",
            "end_date": "2026-12-31",
        },
    )
    assert one_off.status_code == 201, one_off.text
    assert one_off.json()["end_date"] is None

    jan = await _run(client, headers, company_id, branch_id, 1, approve=True)
    jan_slip = jan["payslips"][0]
    assert _benefit_lines(jan_slip) == {"Commission – Q1 sales": Decimal("20000")}
    assert Decimal(jan_slip["gross"]) == Decimal("70000")
    feb = await _run(client, headers, company_id, branch_id, 2, approve=True)
    assert _benefit_lines(feb["payslips"][0]) == {
        "Commission – Q1 sales": Decimal("20000"),
        "Bonus": Decimal("5000"),
    }
    assert Decimal(feb["payslips"][0]["gross"]) == Decimal("75000")
    mar = await _run(client, headers, company_id, branch_id, 3, approve=False)
    assert _benefit_lines(mar["payslips"][0]) == {}
    assert Decimal(mar["payslips"][0]["gross"]) == Decimal("50000")

    listed = await client.get(f"/employees/{person['id']}/benefits", headers=headers)
    assert listed.status_code == 200, listed.text
    by_type = {row["type_name"]: row for row in listed.json()}
    assert Decimal(by_type["Commission"]["paid"]) == Decimal("40000")
    assert Decimal(by_type["Bonus"]["paid"]) == Decimal("5000")

    blocked = await client.delete(f"/employees/{person['id']}/benefits/{ranged.json()['id']}", headers=headers)
    assert blocked.status_code == 409
    in_use = await client.delete(f"/benefit-types/{commission.json()['id']}", headers=headers)
    assert in_use.status_code == 409


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_stopped_and_inactive_benefits(client: AsyncClient) -> None:
    headers, company_id, branch_id = await _tenant(client, "perks@example.com")
    person = await _person(client, headers, company_id, branch_id, "Kamau", "kamau.benefit@example.com")
    await _salary(client, headers, person["id"], "60000")

    allowance = await client.post(
        "/benefit-types",
        headers=headers,
        json={"company_id": company_id, "name": "Overtime"},
    )
    assert allowance.status_code == 201, allowance.text
    row = await client.post(
        f"/employees/{person['id']}/benefits",
        headers=headers,
        json={
            "benefit_type_id": allowance.json()["id"],
            "frequency": "RECURRING",
            "amount": "4000",
            "start_date": "2026-01-01",
        },
    )
    assert row.status_code == 201, row.text
    run = await _run(client, headers, company_id, branch_id, 1, approve=False)
    assert _benefit_lines(run["payslips"][0]) == {"Overtime": Decimal("4000")}

    benefit = row.json()
    stopped = await client.patch(
        f"/employees/{person['id']}/benefits/{benefit['id']}",
        headers=headers,
        json={
            "benefit_type_id": benefit["benefit_type_id"],
            "frequency": benefit["frequency"],
            "amount": benefit["amount"],
            "start_date": benefit["start_date"],
            "status": "STOPPED",
        },
    )
    assert stopped.status_code == 200, stopped.text
    rerun = await _run(client, headers, company_id, branch_id, 1, approve=False)
    assert _benefit_lines(rerun["payslips"][0]) == {}

    removed = await client.delete(f"/employees/{person['id']}/benefits/{benefit['id']}", headers=headers)
    assert removed.status_code == 204

    inactive = await client.patch(
        f"/benefit-types/{allowance.json()['id']}",
        headers=headers,
        json={"name": "Overtime", "is_active": False},
    )
    assert inactive.status_code == 200, inactive.text
    refused = await client.post(
        f"/employees/{person['id']}/benefits",
        headers=headers,
        json={
            "benefit_type_id": allowance.json()["id"],
            "frequency": "ONE_OFF",
            "amount": "1000",
            "start_date": "2026-01-15",
        },
    )
    assert refused.status_code == 400
    deleted = await client.delete(f"/benefit-types/{allowance.json()['id']}", headers=headers)
    assert deleted.status_code == 204

    other_headers, _, _ = await _tenant(client, "perks-outsider@example.com")
    hidden = await client.get(f"/employees/{person['id']}/benefits", headers=other_headers)
    assert hidden.status_code in (403, 404)
