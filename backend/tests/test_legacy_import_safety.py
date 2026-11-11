import uuid
import pytest
from sqlalchemy import select, text
from app.db.session import get_session_maker
from app.models import EmployeeCompensation
from scripts.import_legacy_hrms import scrub
from tests.test_access import workspace
from tests.test_leave_requests import _person


def test_source_archive_redacts_credentials_inside_nested_json():
    value = {"password_hash": "secret", "details": '{"new_password":"private","name":"Kept"}'}
    assert scrub(value) == {"password_hash": "[redacted]", "details": {"new_password": "[redacted]", "name": "Kept"}}


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_historical_compensation_never_enables_future_payroll(client):
    w, owner = await workspace(client)
    person = await _person(client, owner, w["company"]["id"], w["branch"]["id"], "History", "history@example.com")
    saved = await client.post(f"/employees/{person['id']}/compensation", headers=owner,
        json={"effective_from": "2026-01-01", "structure": "GROSS_ONLY", "gross_amount": "30000"})
    assert saved.status_code == 201, saved.text
    async with get_session_maker()() as session:
        await session.execute(text("SELECT set_config('app.is_platform_admin','true',true)"))
        row = await session.get(EmployeeCompensation, uuid.UUID(saved.json()["id"]))
        row.is_historical = True
        await session.commit()
    rows = await client.get(f"/employees/{person['id']}/compensation", headers=owner)
    assert rows.status_code == 200 and rows.json() == []
    preview = await client.get("/payroll/employees", headers=owner, params={"company_id": w["company"]["id"], "branch_id": w["branch"]["id"], "period_end": "2026-11-30"})
    assert preview.status_code == 200 and preview.json()[0]["eligible"] is False
