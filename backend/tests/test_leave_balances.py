from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient

from types import SimpleNamespace

from app.services.leave_balances import entitled_days, month_span
from tests.conftest import auth_header
from tests.test_leave_requests import _leave_type, _person
from tests.test_tenancy import _kenya, _register


def test_month_span_and_accrual() -> None:
    assert month_span(date(2026, 1, 1), date(2026, 12, 31)) == 12
    assert month_span(date(2026, 1, 1), date(2026, 9, 24)) == 8
    annual = SimpleNamespace(days=Decimal("21"), accrued=True, accrual_per_month=Decimal("1.75"))
    assert entitled_days(annual, date(2026, 1, 1), 2026, date(2026, 9, 24)) == Decimal("14.00")
    assert entitled_days(annual, None, 2026, date(2026, 9, 24)) == Decimal("21.00")
    custom = SimpleNamespace(days=Decimal("24"), accrued=True, accrual_per_month=Decimal("2"))
    assert entitled_days(custom, date(2026, 1, 1), 2026, date(2026, 9, 24)) == Decimal("16.00")
    sick = SimpleNamespace(days=Decimal("7"), accrued=False, accrual_per_month=Decimal("0"))
    assert entitled_days(sick, date(2026, 6, 1), 2026, date(2026, 9, 24)) == Decimal("7.00")


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_leave_balances_deduct_and_block(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="bal-a@example.com",
        tenant_name="Bal A",
        company_name="Bal A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="bal-b@example.com",
        tenant_name="Bal B",
        company_name="Bal B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    headers_b = auth_header(tenant_b["access_token"])
    company_a = tenant_a["company"]["id"]
    branch_a = tenant_a["branch"]["id"]

    person = await _person(client, headers_a, company_a, branch_a, "Amina", "amina@bal.example")
    annual = await _leave_type(client, headers_a, company_a, "Annual", "WORKING")
    unpaid = await client.post(
        "/leave-types",
        headers=headers_a,
        json={"company_id": company_a, "name": "Unpaid", "days": 0, "accrued": False, "day_basis": "WORKING"},
    )
    assert unpaid.status_code == 201, unpaid.text

    empty = await client.get(
        "/leave-balances",
        headers=headers_a,
        params={"company_id": company_a, "employee_id": person["id"], "leave_type_id": annual["id"], "year": 2026},
    )
    assert empty.status_code == 200, empty.text
    assert len(empty.json()) == 1
    assert float(empty.json()[0]["entitled"]) == 21
    assert float(empty.json()[0]["used"]) == 0
    assert float(empty.json()[0]["remaining"]) == 21

    stolen = await client.get(
        "/leave-balances",
        headers=headers_b,
        params={"company_id": company_a},
    )
    assert stolen.status_code in {403, 404}

    approved = await client.post(
        "/leave-requests/hr",
        headers=headers_a,
        json={
            "employee_id": person["id"],
            "leave_type_id": annual["id"],
            "start_on": "2026-06-01",
            "end_on": "2026-06-05",
            "hr_action": "APPROVE_NOW",
        },
    )
    assert approved.status_code == 201, approved.text
    used_days = float(approved.json()["days"])

    after = await client.get(
        "/leave-balances",
        headers=headers_a,
        params={"company_id": company_a, "employee_id": person["id"], "leave_type_id": annual["id"], "year": 2026},
    )
    assert float(after.json()[0]["used"]) == used_days
    assert float(after.json()[0]["remaining"]) == 21 - used_days

    blocked = await client.post(
        "/leave-requests/hr",
        headers=headers_a,
        json={
            "employee_id": person["id"],
            "leave_type_id": annual["id"],
            "start_on": "2026-07-01",
            "end_on": "2026-08-31",
            "hr_action": "APPROVE_NOW",
        },
    )
    assert blocked.status_code == 400
    assert "remain" in blocked.json()["detail"].lower()

    extra = await client.patch(
        "/leave-balances",
        headers=headers_a,
        json={"employee_id": person["id"], "leave_type_id": annual["id"], "year": 2026, "extra_days": 20},
    )
    assert extra.status_code == 200, extra.text
    assert float(extra.json()["extra"]) == 20
    assert float(extra.json()["remaining"]) == 21 - used_days + 20

    open_leave = await client.post(
        "/leave-requests/hr",
        headers=headers_a,
        json={
            "employee_id": person["id"],
            "leave_type_id": unpaid.json()["id"],
            "start_on": "2026-09-07",
            "end_on": "2026-09-08",
            "hr_action": "APPROVE_NOW",
        },
    )
    assert open_leave.status_code == 201, open_leave.text


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_leave_balances_hide_terminated_after_new_record_rehire(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant = await _register(
        client,
        email="bal-rehire@example.com",
        tenant_name="Bal Rehire",
        company_name="Bal Rehire Corp",
        country_id=kenya.id,
    )
    headers = auth_header(tenant["access_token"])
    company_id = tenant["company"]["id"]
    branch_id = tenant["branch"]["id"]
    person = await _person(client, headers, company_id, branch_id, "Amina", "amina@rehire.example")
    await _leave_type(client, headers, company_id)

    ended = await client.post(
        f"/employees/{person['id']}/lifecycle",
        headers=headers,
        json={"event_type": "TERMINATED", "reason": "Contract ended", "effective_on": "2026-06-01"},
    )
    assert ended.status_code == 200, ended.text
    rehired = await client.post(
        f"/employees/{person['id']}/lifecycle",
        headers=headers,
        json={
            "event_type": "REHIRED",
            "rehire_mode": "NEW_RECORD",
            "copy_from_previous": True,
            "effective_on": "2026-07-01",
            "email": "amina@rehire.example",
        },
    )
    assert rehired.status_code == 200, rehired.text
    current = rehired.json()["new_employee"]
    assert current is not None

    listed = await client.get("/leave-balances", headers=headers, params={"company_id": company_id, "year": 2026})
    assert listed.status_code == 200, listed.text
    people = {row["employee_id"] for row in listed.json()}
    assert current["id"] in people
    assert person["id"] not in people

    old = await client.get(
        "/leave-balances",
        headers=headers,
        params={"company_id": company_id, "employee_id": person["id"], "year": 2026},
    )
    assert old.status_code == 200
    assert {row["employee_id"] for row in old.json()} == {person["id"]}
