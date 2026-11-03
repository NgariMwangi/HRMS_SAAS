from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_leave_requests import _person
from tests.test_tenancy import _kenya, _register


async def _tenant(client: AsyncClient, email: str) -> tuple[dict, str, str]:
    kenya = await _kenya()
    tenant = await _register(
        client,
        email=email,
        tenant_name=f"{email} co",
        company_name=f"{email} Ltd",
        country_id=kenya.id,
    )
    return auth_header(tenant["access_token"]), tenant["company"]["id"], tenant["branch"]["id"]


async def _salary(client: AsyncClient, headers: dict, employee_id: str, gross: str) -> None:
    pay = await client.post(
        f"/employees/{employee_id}/compensation",
        headers=headers,
        json={"effective_from": "2026-01-01", "structure": "GROSS_ONLY", "gross_amount": gross},
    )
    assert pay.status_code == 201, pay.text


async def _run(client: AsyncClient, headers: dict, company_id: str, branch_id: str, month: int, *, approve: bool) -> dict:
    last = {1: 31, 2: 28, 3: 31, 4: 30}[month]
    run = await client.post(
        "/payroll/runs",
        headers=headers,
        json={
            "company_id": company_id,
            "branch_id": branch_id,
            "period_start": f"2026-{month:02d}-01",
            "period_end": f"2026-{month:02d}-{last}",
        },
    )
    assert run.status_code == 201, run.text
    if approve:
        done = await client.post(f"/payroll/runs/{run.json()['id']}/approve", headers=headers)
        assert done.status_code == 200, done.text
        return done.json()
    return run.json()


def _other_lines(slip: dict) -> dict[str, Decimal]:
    return {line["name"]: Decimal(line["amount"]) for line in slip["lines"] if line["code"] == "OTHER"}


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_loan_stops_when_total_recovered_and_one_off_hits_its_month(client: AsyncClient) -> None:
    headers, company_id, branch_id = await _tenant(client, "loans@example.com")
    person = await _person(client, headers, company_id, branch_id, "Otieno", "otieno.loan@example.com")
    await _salary(client, headers, person["id"], "100000")

    loan_type = await client.post(
        "/deduction-types",
        headers=headers,
        json={"company_id": company_id, "name": "Staff loan", "category": "PERSONAL"},
    )
    assert loan_type.status_code == 201, loan_type.text
    advance_type = await client.post(
        "/deduction-types",
        headers=headers,
        json={"company_id": company_id, "name": "Salary advance", "category": "PERSONAL"},
    )
    assert advance_type.status_code == 201, advance_type.text
    duplicate = await client.post(
        "/deduction-types",
        headers=headers,
        json={"company_id": company_id, "name": "staff LOAN", "category": "PERSONAL"},
    )
    assert duplicate.status_code == 409

    loan = await client.post(
        f"/employees/{person['id']}/deductions",
        headers=headers,
        json={
            "deduction_type_id": loan_type.json()["id"],
            "frequency": "RECURRING",
            "amount": "10000",
            "start_date": "2026-01-01",
            "total_amount": "25000",
            "reference": "LN-1",
        },
    )
    assert loan.status_code == 201, loan.text
    assert Decimal(loan.json()["balance"]) == Decimal("25000")
    advance = await client.post(
        f"/employees/{person['id']}/deductions",
        headers=headers,
        json={
            "deduction_type_id": advance_type.json()["id"],
            "frequency": "ONE_OFF",
            "amount": "3000",
            "start_date": "2026-02-15",
            "end_date": "2026-12-31",
            "total_amount": "99999",
        },
    )
    assert advance.status_code == 201, advance.text
    assert advance.json()["end_date"] is None
    assert advance.json()["total_amount"] is None

    jan = await _run(client, headers, company_id, branch_id, 1, approve=True)
    assert _other_lines(jan["payslips"][0]) == {"Staff loan (LN-1)": Decimal("10000")}
    feb = await _run(client, headers, company_id, branch_id, 2, approve=True)
    assert _other_lines(feb["payslips"][0]) == {
        "Staff loan (LN-1)": Decimal("10000"),
        "Salary advance": Decimal("3000"),
    }
    mar = await _run(client, headers, company_id, branch_id, 3, approve=True)
    assert _other_lines(mar["payslips"][0]) == {"Staff loan (LN-1)": Decimal("5000")}
    apr = await _run(client, headers, company_id, branch_id, 4, approve=False)
    assert _other_lines(apr["payslips"][0]) == {}

    slip = feb["payslips"][0]
    deducted = sum(Decimal(line["amount"]) for line in slip["lines"] if line["kind"] == "DEDUCTION")
    assert Decimal(slip["employee_deductions"]) == deducted
    assert Decimal(slip["net"]) == Decimal(slip["gross"]) - deducted

    listed = await client.get(f"/employees/{person['id']}/deductions", headers=headers)
    assert listed.status_code == 200, listed.text
    by_type = {row["type_name"]: row for row in listed.json()}
    assert Decimal(by_type["Staff loan"]["recovered"]) == Decimal("25000")
    assert Decimal(by_type["Staff loan"]["balance"]) == Decimal("0")
    assert Decimal(by_type["Salary advance"]["recovered"]) == Decimal("3000")

    blocked = await client.delete(f"/employees/{person['id']}/deductions/{loan.json()['id']}", headers=headers)
    assert blocked.status_code == 409
    in_use = await client.delete(f"/deduction-types/{loan_type.json()['id']}", headers=headers)
    assert in_use.status_code == 409


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_company_scheme_bulk_enrol_and_stop(client: AsyncClient) -> None:
    headers, company_id, branch_id = await _tenant(client, "welfare@example.com")
    amina = await _person(client, headers, company_id, branch_id, "Amina", "amina.welfare@example.com")
    john = await _person(client, headers, company_id, branch_id, "John", "john.welfare@example.com")
    await _salary(client, headers, amina["id"], "60000")
    await _salary(client, headers, john["id"], "60000")

    welfare = await client.post(
        "/deduction-types",
        headers=headers,
        json={"company_id": company_id, "name": "Welfare Kit", "category": "COMPANY", "default_amount": "500"},
    )
    assert welfare.status_code == 201, welfare.text
    picked = await client.post(
        f"/deduction-types/{welfare.json()['id']}/enrol",
        headers=headers,
        json={"start_date": "2026-01-01", "branch_id": branch_id, "employee_ids": [amina["id"]]},
    )
    assert picked.status_code == 200, picked.text
    assert picked.json() == {"enrolled": 1, "already_enrolled": 0}
    candidates = await client.get(
        f"/deduction-types/{welfare.json()['id']}/enrol",
        headers=headers,
        params={"branch_id": branch_id},
    )
    assert candidates.status_code == 200, candidates.text
    assert {row["employee_id"]: row["enrolled"] for row in candidates.json()} == {
        amina["id"]: True,
        john["id"]: False,
    }
    none_picked = await client.post(
        f"/deduction-types/{welfare.json()['id']}/enrol",
        headers=headers,
        json={"start_date": "2026-01-01", "employee_ids": []},
    )
    assert none_picked.status_code == 400
    enrol = await client.post(
        f"/deduction-types/{welfare.json()['id']}/enrol",
        headers=headers,
        json={"start_date": "2026-01-01", "branch_id": branch_id},
    )
    assert enrol.status_code == 200, enrol.text
    assert enrol.json() == {"enrolled": 1, "already_enrolled": 1}
    again = await client.post(
        f"/deduction-types/{welfare.json()['id']}/enrol",
        headers=headers,
        json={"start_date": "2026-01-01"},
    )
    assert again.json() == {"enrolled": 0, "already_enrolled": 2}

    run = await _run(client, headers, company_id, branch_id, 1, approve=False)
    for slip in run["payslips"]:
        assert _other_lines(slip) == {"Welfare Kit": Decimal("500")}

    john_rows = (await client.get(f"/employees/{john['id']}/deductions", headers=headers)).json()
    assert len(john_rows) == 1
    row = john_rows[0]
    stopped = await client.patch(
        f"/employees/{john['id']}/deductions/{row['id']}",
        headers=headers,
        json={
            "deduction_type_id": row["deduction_type_id"],
            "frequency": row["frequency"],
            "amount": row["amount"],
            "start_date": row["start_date"],
            "status": "STOPPED",
        },
    )
    assert stopped.status_code == 200, stopped.text
    rerun = await _run(client, headers, company_id, branch_id, 1, approve=False)
    lines = {slip["employee_id"]: _other_lines(slip) for slip in rerun["payslips"]}
    assert lines[amina["id"]] == {"Welfare Kit": Decimal("500")}
    assert lines[john["id"]] == {}

    removed = await client.delete(f"/employees/{john['id']}/deductions/{row['id']}", headers=headers)
    assert removed.status_code == 204

    other_headers, _, _ = await _tenant(client, "outsider@example.com")
    hidden = await client.patch(
        f"/deduction-types/{welfare.json()['id']}",
        headers=other_headers,
        json={"name": "Hijack", "category": "COMPANY"},
    )
    assert hidden.status_code in (403, 404)
