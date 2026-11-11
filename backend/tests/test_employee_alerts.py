from datetime import date
from types import SimpleNamespace
from app.services.employee_alerts import employee_alerts, upcoming_birthday
import pytest
from tests.test_access import workspace, staff_login


def person(**updates):
    return SimpleNamespace(**({"id": "one", "branch_id": "branch", "first_name": "Jane", "other_names": None, "last_name": "Doe", "status": "ACTIVE", "date_of_birth": None, "employment_type": "FULL_TIME", "date_ended": None} | updates))


def test_birthday_rollover_leap_day_and_window():
    assert upcoming_birthday(date(2000, 1, 2), date(2026, 12, 29)) == date(2027, 1, 2)
    assert upcoming_birthday(date(2000, 2, 29), date(2027, 2, 28)) == date(2027, 3, 1)
    today = date(2026, 11, 11)
    rows = [person(id=str(day), date_of_birth=date(2000, 11, day)) for day in (11, 25, 26)]
    rows.append(person(status="TERMINATED", date_of_birth=date(2000, 11, 11)))
    assert [r["days"] for r in employee_alerts(rows, today)["birthdays"]] == [0, 14]


def test_probation_due_upcoming_and_legacy_dates():
    rows = [person(id=str(day), employment_type="PROBATION", date_ended=date(2026, 11, day)) for day in (10, 11, 25, 26)]
    rows += [person(id="legacy", employment_type="PROBATION"), person(id="confirmed", date_ended=date(2026, 11, 10))]
    result = employee_alerts(rows, date(2026, 11, 11), {"legacy": date(2026, 11, 12)})
    assert [r["days"] for r in result["probation"]] == [-1, 0, 1, 14]
    assert all(r["employee_id"] != "confirmed" for r in result["probation"])


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_alert_endpoint_permissions_and_company_boundary(client):
    w, owner = await workspace(client)
    foreign, _ = await workspace(client, "alert-foreign@example.com")
    _, _, staff = await staff_login(client, owner, w, "AlertStaff")
    path = f"/employees/alerts?company_id={w['company']['id']}"
    result = await client.get(path, headers=owner)
    assert result.status_code == 200, result.text
    assert result.json()["window_days"] == 14
    assert (await client.get(path, headers=staff)).status_code == 403
    assert (await client.get(f"/employees/alerts?company_id={foreign['company']['id']}", headers=owner)).status_code == 403
