import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from app.db.session import get_session_maker
from app.models import Company, Employee, LeaveEmail, LeaveRequest, User
from app.services import leave_emails
from tests.test_access import workspace, staff_login


@pytest.fixture
def delivery(monkeypatch):
    monkeypatch.setattr(leave_emails, "get_settings", lambda: SimpleNamespace(brevo_api_key=SecretStr("test-only-key"),
        brevo_sender_email="sender@example.com",brevo_sender_name="HRMS",hrms_base_domain="hrms.example.com"))
    calls=[]
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self,url,**kwargs):
            calls.append(kwargs)
            return httpx.Response(201,json={"messageId":"test"})
    monkeypatch.setattr(leave_emails.httpx,"AsyncClient",Client)
    return calls


async def records():
    async with get_session_maker()() as session:
        await session.execute(text("SELECT set_config('app.is_platform_admin','true',true)"))
        return (await session.scalars(select(LeaveEmail).order_by(LeaveEmail.created_at,LeaveEmail.id))).all()


@pytest.mark.usefixtures("clean_tenant_tables")
@pytest.mark.parametrize("final_decision", ["APPROVED", "REJECTED"])
async def test_leave_events_are_queued_then_delivered_to_work_emails(client,delivery,final_decision):
    w,owner=await workspace(client)
    employee,_,employee_auth=await staff_login(client,owner,w,"LeaveMailer")
    supervisor,_,supervisor_auth=await staff_login(client,owner,w,"LeaveSupervisor",role="MANAGER")
    await workspace(client,"unrelated-owner@example.com")
    owner_email=(await client.get("/auth/me",headers=owner)).json()["email"]
    assigned=await client.put(f"/employees/{employee['id']}/supervisors",headers=owner,json={"supervisor_ids":[supervisor['id']]})
    assert assigned.status_code==200,assigned.text
    kind=await client.post("/leave-types",headers=owner,json={"company_id":w["company"]["id"],"name":"Annual emails","days":"21","accrued":False,"day_basis":"WORKING"})
    assert kind.status_code==201,kind.text
    body=dict(employee_id=employee["id"],leave_type_id=kind.json()["id"],start_on="2026-11-16",end_on="2026-11-16",
        duration="HALF_DAY")
    applied=await client.post("/leave-requests/self",headers=employee_auth,json=body)
    assert applied.status_code==201,applied.text
    request=applied.json();path=f"/leave-requests/{request['id']}"
    assert request["approval_mode"] == "SUPERVISOR_THEN_HR"
    assert request["status"] == "PENDING_SUPERVISOR"
    assert not delivery  # Queueing must not call Brevo inside the request transaction.
    queued=await records()
    assert len(queued)==3 and {r.status for r in queued}=={"PENDING"}
    assert {str(r.tenant_id) for r in queued}=={w["tenant"]["id"]}
    assert await leave_emails.deliver_pending()==3
    assert {call["json"]["to"][0]["email"] for call in delivery}=={employee["email"],supervisor["email"],owner_email}
    assert all(call["headers"]["api-key"]=="test-only-key" for call in delivery)
    assert all(str(request["days"]) in call["json"]["htmlContent"] for call in delivery)
    assert len({call["json"]["headers"]["IdempotencyKey"] for call in delivery})==3
    assert await leave_emails.deliver_pending()==0
    # A decline is a recommendation; the owner still owes a final response.
    decided=await client.post(path+"/supervisor-decision",headers=supervisor_auth,
        json={"supervisor_employee_id":supervisor["id"],"decision":"REJECTED","note":"Review <b>cover</b>"})
    assert decided.status_code==200 and decided.json()["status"]=="PENDING_HR",decided.text
    assert await leave_emails.deliver_pending()==2
    assert {call["json"]["to"][0]["email"] for call in delivery[3:]}=={supervisor["email"],owner_email}
    assert all("declined" in call["json"]["htmlContent"] for call in delivery[3:])
    assert all("&lt;b&gt;cover&lt;/b&gt;" in call["json"]["htmlContent"] for call in delivery[3:])
    final=await client.post(path+"/hr-decision",headers=owner,json={"decision":final_decision,"note":"Cover arranged"})
    assert final.status_code==200 and final.json()["status"]==final_decision,final.text
    assert await leave_emails.deliver_pending()==2
    assert {call["json"]["to"][0]["email"] for call in delivery[5:]}=={employee["email"],owner_email}
    assert all(("approved" if final_decision=="APPROVED" else "declined") in call["json"]["htmlContent"] for call in delivery[5:])
    assert (await client.post(path+"/hr-decision",headers=owner,json={"decision":"REJECTED"})).status_code==400
    assert len(await records())==7
    # The same event cannot be queued twice; rolled-back applications send nothing.
    async with get_session_maker()() as session:
        await session.execute(text("SELECT set_config('app.is_platform_admin','true',true)"))
        saved=await session.get(LeaveRequest,uuid.UUID(request["id"]))
        await leave_emails.queue(session,saved,"APPLIED")
        await session.commit()
    assert len(await records())==7
    from app.api.leave import create_self_request
    from datetime import date
    async with get_session_maker()() as session:
        await session.execute(text("SELECT set_config('app.is_platform_admin','true',true)"))
        actor=await session.scalar(select(User).where(User.employee_id==uuid.UUID(employee["id"])))
        await create_self_request(session,uuid.UUID(w["tenant"]["id"]),actor,uuid.UUID(employee["id"]),uuid.UUID(kind.json()["id"]),
            date(2026,11,18),date(2026,11,18),None,"HR_ONLY")
        await session.rollback()
    assert len(await records())==7 and await leave_emails.deliver_pending()==0


@pytest.mark.parametrize("linked,work,expected",[(False,None,"owner-account@example.com"),
    (True,"owner-work@example.com","owner-work@example.com"),(True,None,None)])
async def test_owner_work_email_and_explicit_account_fallback(linked,work,expected):
    tenant,identity,person_id,company_id=[uuid.uuid4() for _ in range(4)]
    owner=SimpleNamespace(tenant_id=tenant,role="OWNER",status="ACTIVE",employee_id=person_id if linked else None,email="owner-account@example.com")
    person=SimpleNamespace(company_id=company_id,status="ACTIVE",email=work)
    company=SimpleNamespace(tenant_id=tenant)
    class Session:
        async def get(self,model,key):return {User:owner,Employee:person,Company:company}[model]
    row=SimpleNamespace(recipient_kind="owner",recipient_id=identity,tenant_id=tenant)
    assert await leave_emails.recipient_email(Session(),row)==expected


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_missing_work_email_blocks_and_recovers_without_personal_fallback(client,delivery):
    w,owner=await workspace(client)
    person,_,auth=await staff_login(client,owner,w,"NoWorkEmail")
    response=await client.patch(f"/employees/{person['id']}",headers=owner,json={"email":None,"personal_email":"private@example.com"})
    assert response.status_code==200
    kind=await client.post("/leave-types",headers=owner,json={"company_id":w["company"]["id"],"name":"Email recovery","days":"21","accrued":False})
    request=await client.post("/leave-requests/self",headers=auth,json={"employee_id":person["id"],"leave_type_id":kind.json()["id"],
        "start_on":"2026-11-16","end_on":"2026-11-16"})
    assert request.status_code==201,request.text
    assert request.json()["approval_mode"] == "HR_ONLY"
    assert request.json()["status"] == "PENDING_HR"
    await leave_emails.deliver_pending()
    rows=await records();blocked=next(row for row in rows if row.purpose=="application_confirmation")
    assert blocked.status=="BLOCKED" and all(call["json"]["to"][0]["email"]!="private@example.com" for call in delivery)
    await client.patch(f"/employees/{person['id']}",headers=owner,json={"email":"fixed-work@example.com"})
    async with get_session_maker()() as session:
        await session.execute(text("SELECT set_config('app.is_platform_admin','true',true)"))
        row=await session.get(LeaveEmail,blocked.id);row.next_attempt_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        await session.commit()
    assert await leave_emails.deliver_pending()==1
    assert delivery[-1]["json"]["to"][0]["email"]=="fixed-work@example.com"


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_delivery_failures_retry_only_when_safe(client,delivery,monkeypatch):
    w,owner=await workspace(client)
    person,_,auth=await staff_login(client,owner,w,"DeliveryFailure")
    kind=await client.post("/leave-types",headers=owner,json={"company_id":w["company"]["id"],"name":"Delivery failures","days":"21","accrued":False})
    applied=await client.post("/leave-requests/self",headers=auth,json={"employee_id":person["id"],"leave_type_id":kind.json()["id"],
        "start_on":"2026-11-16","end_on":"2026-11-16","approval_mode":"HR_ONLY"})
    assert applied.status_code==201,applied.text
    rows=await records();identity=rows[0].id
    mode=None
    async def fail(self,url,**kwargs):
        if mode=="connect":raise httpx.ConnectError("private transport detail")
        if mode=="read":raise httpx.ReadTimeout("private transport detail")
        return httpx.Response(mode,text="private provider detail")
    monkeypatch.setattr(leave_emails.httpx.AsyncClient,"post",fail)
    for mode,expected in [(429,"PENDING"),(401,"FAILED"),(503,"UNCERTAIN"),("connect","PENDING"),("read","UNCERTAIN")]:
        async with get_session_maker()() as session:
            await session.execute(text("SELECT set_config('app.is_platform_admin','true',true)"))
            for row in (await session.scalars(select(LeaveEmail))).all():
                row.status="PENDING" if row.id==identity else "SENT"
                row.attempts=0;row.next_attempt_at=datetime.now(timezone.utc)-timedelta(seconds=1)
            await session.commit()
        assert await leave_emails.deliver_pending(limit=1)==1
        row=next(row for row in await records() if row.id==identity)
        assert row.status==expected and row.attempts==1
        assert "private" not in row.last_error
        assert await leave_emails.deliver_pending()==0
