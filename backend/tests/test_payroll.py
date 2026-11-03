from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_leave_requests import _person
from tests.test_platform import _admin_login
from tests.test_tenancy import _kenya, _register, _uganda


def _month() -> tuple[str, str]:
    start = date(2026, 3, 1)
    return start.isoformat(), date(2026, 3, 31).isoformat()


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_platform_payroll_packs_for_east_africa(client: AsyncClient) -> None:
    admin = await _admin_login(client)
    kenya = await _kenya()
    listed = await client.get("/platform/payroll-packs", headers=admin, params={"country_id": str(kenya.id)})
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert rows
    assert rows[0]["status"] == "PUBLISHED"
    detail = await client.get(f"/platform/payroll-packs/{rows[0]['id']}", headers=admin)
    assert detail.status_code == 200
    codes = {item["code"] for item in detail.json()["components"]}
    assert {"PAYE", "NSSF_I", "NSSF_II", "SHIF", "HOUSING"} <= codes
    tenant = await _register(
        client,
        email="pack-tenant@example.com",
        tenant_name="Pack Co",
        company_name="Pack Co Ltd",
        country_id=kenya.id,
    )
    forbidden = await client.get("/platform/payroll-packs", headers=auth_header(tenant["access_token"]))
    assert forbidden.status_code == 403


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_gross_and_basic_plus_allowances_payroll_run(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant = await _register(
        client,
        email="pay-ke@example.com",
        tenant_name="Pay KE",
        company_name="Pay KE Ltd",
        country_id=kenya.id,
    )
    headers = auth_header(tenant["access_token"])
    company_id = tenant["company"]["id"]
    branch_id = tenant["branch"]["id"]
    settings = await client.put(
        "/payroll/settings",
        headers=headers,
        params={"company_id": company_id, "branch_id": branch_id},
        json={"frequency": "MONTHLY", "salary_structure": "GROSS_ONLY"},
    )
    assert settings.status_code == 200, settings.text
    assert settings.json()["country_code"] == "KE"
    assert settings.json()["currency_code"] == "KES"
    assert settings.json()["pack_status"] == "PUBLISHED"

    amina = await _person(client, headers, company_id, branch_id, "Amina", "amina.pay@example.com")
    john = await _person(client, headers, company_id, branch_id, "John", "john.pay@example.com")
    start, end = _month()
    pay = await client.post(
        f"/employees/{amina['id']}/compensation",
        headers=headers,
        json={"effective_from": "2026-01-01", "structure": "GROSS_ONLY", "gross_amount": "100000"},
    )
    assert pay.status_code == 201, pay.text
    assert Decimal(pay.json()["computed_gross"]) == Decimal("100000")
    mixed = await client.post(
        f"/employees/{john['id']}/compensation",
        headers=headers,
        json={
            "effective_from": "2026-01-01",
            "structure": "BASIC_PLUS_ALLOWANCES",
            "basic_amount": "50000",
            "lines": [
                {"name": "Housing", "amount": "20000"},
                {"name": "Transport", "amount": "10000"},
            ],
        },
    )
    assert mixed.status_code == 201, mixed.text
    assert Decimal(mixed.json()["computed_gross"]) == Decimal("80000")

    run = await client.post(
        "/payroll/runs",
        headers=headers,
        json={"company_id": company_id, "branch_id": branch_id, "period_start": start, "period_end": end},
    )
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["status"] == "DRAFT"
    assert body["country_code"] == "KE"
    assert len(body["payslips"]) == 2
    amina_slip = next(row for row in body["payslips"] if row["employee_id"] == amina["id"])
    john_slip = next(row for row in body["payslips"] if row["employee_id"] == john["id"])
    assert Decimal(amina_slip["gross"]) == Decimal("100000.00")
    assert Decimal(john_slip["gross"]) == Decimal("80000.00")
    john_codes = {line["code"]: Decimal(line["amount"]) for line in john_slip["lines"]}
    assert john_codes["NSSF_I"] == Decimal("540.00")
    assert john_codes["NSSF_II"] == Decimal("4260.00")
    assert john_codes["NSSF_I_ER"] == Decimal("540.00")
    assert john_codes["NSSF_II_ER"] == Decimal("4260.00")
    assert Decimal(amina_slip["net"]) < Decimal(amina_slip["gross"])
    codes = {line["code"] for line in amina_slip["lines"]}
    assert {"GROSS", "PAYE", "NSSF_I", "NSSF_II", "SHIF", "HOUSING"} <= codes
    assert Decimal(next(line["amount"] for line in amina_slip["lines"] if line["code"] == "NSSF_I")) == Decimal("540.00")
    assert Decimal(next(line["amount"] for line in amina_slip["lines"] if line["code"] == "NSSF_II")) == Decimal("5460.00")
    assert Decimal(next(line["amount"] for line in amina_slip["lines"] if line["code"] == "NSSF_I_ER")) == Decimal("540.00")
    assert Decimal(next(line["amount"] for line in amina_slip["lines"] if line["code"] == "NSSF_II_ER")) == Decimal("5460.00")
    assert Decimal(next(line["amount"] for line in amina_slip["lines"] if line["code"] == "SHIF")) == Decimal("2750.00")
    assert Decimal(next(line["amount"] for line in amina_slip["lines"] if line["code"] == "HOUSING")) == Decimal("1500.00")
    assert Decimal(next(line["amount"] for line in amina_slip["lines"] if line["code"] == "TAXABLE")) == Decimal("89750.00")

    again = await client.post(
        "/payroll/runs",
        headers=headers,
        json={"company_id": company_id, "branch_id": branch_id, "period_start": start, "period_end": end},
    )
    assert again.status_code == 201, again.text
    assert again.json()["id"] == body["id"]
    assert again.json()["status"] == "DRAFT"
    assert len(again.json()["payslips"]) == 2

    raised = await client.patch(
        f"/employees/{amina['id']}/compensation/{pay.json()['id']}",
        headers=headers,
        json={"effective_from": "2026-01-01", "structure": "GROSS_ONLY", "gross_amount": "120000"},
    )
    assert raised.status_code == 200, raised.text
    rerun = await client.post(
        "/payroll/runs",
        headers=headers,
        json={"company_id": company_id, "branch_id": branch_id, "period_start": start, "period_end": end},
    )
    assert rerun.status_code == 201, rerun.text
    amina_again = next(row for row in rerun.json()["payslips"] if row["employee_id"] == amina["id"])
    assert Decimal(amina_again["gross"]) == Decimal("120000.00")

    approved = await client.post(f"/payroll/runs/{body['id']}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    blocked = await client.post(
        "/payroll/runs",
        headers=headers,
        json={"company_id": company_id, "branch_id": branch_id, "period_start": start, "period_end": end},
    )
    assert blocked.status_code == 409


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_uganda_branch_uses_uganda_pack(client: AsyncClient) -> None:
    kenya = await _kenya()
    uganda = await _uganda()
    tenant = await _register(
        client,
        email="pay-ug@example.com",
        tenant_name="Pay UG",
        company_name="Pay UG Ltd",
        country_id=kenya.id,
    )
    headers = auth_header(tenant["access_token"])
    company_id = tenant["company"]["id"]
    branch = await client.post(
        "/branches",
        headers=headers,
        json={"company_id": company_id, "country_id": str(uganda.id), "name": "Kampala", "code": "KLA"},
    )
    assert branch.status_code == 201, branch.text
    branch_id = branch.json()["id"]
    person = await _person(client, headers, company_id, branch_id, "Sara", "sara.ug@example.com")
    await client.post(
        f"/employees/{person['id']}/compensation",
        headers=headers,
        json={"effective_from": "2026-01-01", "structure": "GROSS_ONLY", "gross_amount": "2000000"},
    )
    start, end = _month()
    run = await client.post(
        "/payroll/runs",
        headers=headers,
        json={"company_id": company_id, "branch_id": branch_id, "period_start": start, "period_end": end},
    )
    assert run.status_code == 201, run.text
    assert run.json()["country_code"] == "UG"
    slip = run.json()["payslips"][0]
    codes = {line["code"]: Decimal(line["amount"]) for line in slip["lines"]}
    assert "SHIF" not in codes
    assert "SDL" not in codes
    assert codes["NSSF"] == Decimal("100000")
    assert codes["NSSF_ER"] == Decimal("200000")
    assert codes["TAXABLE"] == Decimal("2000000")
    assert codes["PAYE"] == Decimal("502000")

    july = await client.post(
        "/payroll/runs",
        headers=headers,
        json={
            "company_id": company_id,
            "branch_id": branch_id,
            "period_start": "2026-07-01",
            "period_end": "2026-07-31",
        },
    )
    assert july.status_code == 201, july.text
    july_codes = {line["code"]: Decimal(line["amount"]) for line in july.json()["payslips"][0]["lines"]}
    assert july_codes["NSSF"] == Decimal("100000")
    assert july_codes["TAXABLE"] == Decimal("2000000")
    assert july_codes["PAYE"] == Decimal("488250")


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_salary_can_be_corrected_and_superseded(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant = await _register(
        client,
        email="pay-edit@example.com",
        tenant_name="Pay Edit",
        company_name="Pay Edit Ltd",
        country_id=kenya.id,
    )
    headers = auth_header(tenant["access_token"])
    company_id = tenant["company"]["id"]
    branch_id = tenant["branch"]["id"]
    person = await _person(client, headers, company_id, branch_id, "Ida", "ida.pay@example.com")
    created = await client.post(
        f"/employees/{person['id']}/compensation",
        headers=headers,
        json={"effective_from": "2026-01-01", "structure": "GROSS_ONLY", "gross_amount": "90000"},
    )
    assert created.status_code == 201, created.text
    salary_id = created.json()["id"]
    fixed = await client.patch(
        f"/employees/{person['id']}/compensation/{salary_id}",
        headers=headers,
        json={"effective_from": "2026-01-01", "structure": "GROSS_ONLY", "gross_amount": "95000"},
    )
    assert fixed.status_code == 200, fixed.text
    assert Decimal(fixed.json()["computed_gross"]) == Decimal("95000")
    raised = await client.post(
        f"/employees/{person['id']}/compensation",
        headers=headers,
        json={"effective_from": "2026-04-01", "structure": "GROSS_ONLY", "gross_amount": "110000"},
    )
    assert raised.status_code == 201, raised.text
    listed = await client.get(f"/employees/{person['id']}/compensation", headers=headers)
    assert listed.status_code == 200
    assert [row["effective_from"] for row in listed.json()] == ["2026-04-01", "2026-01-01"]
    assert Decimal(listed.json()[0]["computed_gross"]) == Decimal("110000")
    assert Decimal(listed.json()[1]["computed_gross"]) == Decimal("95000")


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_kenya_voluntary_pension_splits_at_relief_cap(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant = await _register(
        client,
        email="pay-pension@example.com",
        tenant_name="Pay Pension",
        company_name="Pay Pension Ltd",
        country_id=kenya.id,
    )
    headers = auth_header(tenant["access_token"])
    company_id = tenant["company"]["id"]
    branch_id = tenant["branch"]["id"]
    person = await _person(client, headers, company_id, branch_id, "Wanjiru", "wanjiru.pay@example.com")
    created = await client.post(
        f"/employees/{person['id']}/compensation",
        headers=headers,
        json={
            "effective_from": "2026-01-01",
            "structure": "GROSS_ONLY",
            "gross_amount": "200000",
            "voluntary_pension": "40000",
            "pension_scheme": " Britam ",
        },
    )
    assert created.status_code == 201, created.text
    assert Decimal(created.json()["voluntary_pension"]) == Decimal("40000")
    assert created.json()["pension_scheme"] == "Britam"

    start, end = _month()
    run = await client.post(
        "/payroll/runs",
        headers=headers,
        json={"company_id": company_id, "branch_id": branch_id, "period_start": start, "period_end": end},
    )
    assert run.status_code == 201, run.text
    lines = {line["code"]: line for line in run.json()["payslips"][0]["lines"]}
    nssf = Decimal(lines["NSSF_I"]["amount"]) + Decimal(lines["NSSF_II"]["amount"])
    assert nssf == Decimal("6480")
    assert Decimal(lines["VOL_PENSION"]["amount"]) == Decimal("23520")
    assert Decimal(lines["VOL_PENSION_POST"]["amount"]) == Decimal("16480")
    assert lines["VOL_PENSION"]["name"] == "Britam (before tax)"
    shif = Decimal(lines["SHIF"]["amount"])
    housing = Decimal(lines["HOUSING"]["amount"])
    assert Decimal(lines["TAXABLE"]["amount"]) == Decimal("200000") - nssf - shif - housing - Decimal("23520")

    cleared = await client.patch(
        f"/employees/{person['id']}/compensation/{created.json()['id']}",
        headers=headers,
        json={
            "effective_from": "2026-01-01",
            "structure": "GROSS_ONLY",
            "gross_amount": "200000",
            "voluntary_pension": "0",
            "pension_scheme": "Britam",
        },
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["voluntary_pension"] is None
    assert cleared.json()["pension_scheme"] is None
