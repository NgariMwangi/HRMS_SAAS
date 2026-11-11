from decimal import Decimal
import pytest
from tests.test_access import workspace, staff_login
from tests.test_platform import _admin_login


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_half_quarter_leave_balances_approval_and_validation(client):
    w, owner = await workspace(client)
    person, _, employee = await staff_login(client, owner, w, "PartialLeave")
    response = await client.post("/leave-types", headers=owner, json={"company_id":w["company"]["id"],
        "name":"Partial annual", "days":"1", "accrued":False, "day_basis":"WORKING"})
    assert response.status_code == 201, response.text
    leave_type = response.json()["id"]
    base = dict(employee_id=person["id"],leave_type_id=leave_type,start_on="2026-11-16",end_on="2026-11-16")
    half = await client.post("/leave-requests/hr", headers=owner, json={**base,"duration":"HALF_DAY","hr_action":"APPROVE_NOW"})
    assert half.status_code == 201, half.text
    assert Decimal(half.json()["days"]) == Decimal("0.5")
    quarter = await client.post("/leave-requests/self", headers=employee, json={**base,"start_on":"2026-11-17",
        "end_on":"2026-11-17","duration":"QUARTER_DAY","approval_mode":"HR_ONLY"})
    assert quarter.status_code == 201, quarter.text
    assert quarter.json()["status"] == "PENDING_HR" and Decimal(quarter.json()["days"]) == Decimal("0.25")
    params=dict(company_id=w["company"]["id"],employee_id=person["id"],leave_type_id=leave_type,year=2026)
    balances = await client.get("/leave-balances", headers=owner, params=params)
    data=balances.json()[0]
    assert Decimal(data["used"]) == Decimal("0.5") and Decimal(data["pending"]) == Decimal("0.25")
    assert Decimal(data["remaining"]) == Decimal("0.25")
    full = await client.post("/leave-requests/hr", headers=owner, json={**base,"start_on":"2026-11-18",
        "end_on":"2026-11-18","hr_action":"APPROVE_NOW"})
    assert full.status_code == 400
    cancelled = await client.post(f"/leave-requests/{quarter.json()['id']}/cancel", headers=owner)
    assert cancelled.status_code == 200
    admin = await _admin_login(client)
    platform = await client.post(f"/platform/tenants/{w['tenant']['id']}/leave-requests/hr", headers=admin,
        json={**base,"start_on":"2026-11-17","end_on":"2026-11-17","duration":"QUARTER_DAY","hr_action":"APPROVE_NOW"})
    assert platform.status_code == 201, platform.text
    assert Decimal(platform.json()["days"]) == Decimal("0.25")
    for change in [{"end_on":"2026-11-19","duration":"HALF_DAY"},
        {"start_on":"2026-11-21","end_on":"2026-11-21","duration":"QUARTER_DAY"},
        {"start_on":"2026-11-16","end_on":"2026-11-16","duration":"QUARTER_DAY"}]:
        rejected = await client.post("/leave-requests/hr", headers=owner,json={**base,"hr_action":"APPROVE_NOW",**change})
        assert rejected.status_code == 400, rejected.text
    invalid = await client.post("/leave-requests/hr",headers=owner,json={**base,"duration":"OTHER","hr_action":"APPROVE_NOW"})
    assert invalid.status_code == 422
