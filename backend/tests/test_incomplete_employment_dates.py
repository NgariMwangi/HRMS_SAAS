from datetime import date
from uuid import UUID

import pytest
from fastapi import HTTPException
from app.api.org import require_employment_period
from app.db.session import get_session_maker
from app.models import Employee
from tests.test_access import workspace
from tests.test_leave_requests import _person
from tests.test_platform import _admin_login


@pytest.mark.parametrize("employment_type", ["INTERN", "PROBATION"])
@pytest.mark.parametrize("start,end", [(None, None), (date(2026, 1, 1), None), (None, date(2026, 4, 1))])
def test_incomplete_dates_allowed_only_when_explicitly_repairing_existing_record(employment_type, start, end):
    require_employment_period(employment_type, start, end, allow_incomplete=True)
    with pytest.raises(HTTPException):
        require_employment_period(employment_type, start, end)
    with pytest.raises(HTTPException):
        require_employment_period(employment_type, date(2026, 4, 1), date(2026, 1, 1), allow_incomplete=True)


@pytest.mark.usefixtures("clean_tenant_tables")
@pytest.mark.parametrize("employment_type", ["INTERN", "PROBATION"])
async def test_owner_and_platform_can_edit_and_repair_migrated_dates(client, employment_type):
    w, owner = await workspace(client)
    person = await _person(client, owner, w["company"]["id"], w["branch"]["id"], "LegacyDates", "legacydates@example.com")
    async with get_session_maker()() as session:
        row = await session.get(Employee, UUID(person["id"]))
        row.employment_type = employment_type
        row.date_joined = None
        row.date_ended = None
        await session.commit()
    path = f"/employees/{person['id']}"
    response = await client.patch(path, headers=owner, json={"phone": "+254700123456"})
    assert response.status_code == 200, response.text
    assert response.json()["date_joined"] is None and response.json()["date_ended"] is None
    response = await client.patch(path, headers=owner, json={"employment_type": employment_type, "date_joined": "2026-01-01", "date_ended": None})
    assert response.status_code == 200, response.text
    assert response.json()["date_joined"] == "2026-01-01"
    admin = await _admin_login(client)
    platform_path = f"/platform/tenants/{w['tenant']['id']}{path}"
    response = await client.patch(platform_path, headers=admin, json={"last_name": "Updated"})
    assert response.status_code == 200, response.text
    response = await client.patch(platform_path, headers=admin, json={"date_ended": "2025-12-31"})
    assert response.status_code == 400
    response = await client.patch(platform_path, headers=admin, json={"date_ended": "2026-04-01"})
    assert response.status_code == 200, response.text
    # Once repaired, normal validation prevents removing required dates again.
    assert (await client.patch(path, headers=owner, json={"date_ended": None})).status_code == 400
    created = await client.post("/employees", headers=owner, json={"company_id": w["company"]["id"], "branch_id": w["branch"]["id"],
        "first_name": "New incomplete", "last_name": "Employee", "employment_type": employment_type})
    assert created.status_code == 400
