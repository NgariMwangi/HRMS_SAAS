from decimal import Decimal
import pytest
from tests.test_access import workspace
from tests.test_leave_requests import _person
from tests.test_deductions import _salary, _run
from tests.test_platform import _admin_login


@pytest.mark.parametrize("kind", ["benefit", "deduction"])
@pytest.mark.usefixtures("clean_tenant_tables")
async def test_inline_salary_titles_create_reuse_edit_and_remain_company_scoped(client,kind):
    w,owner=await workspace(client)
    company,branch=w["company"]["id"],w["branch"]["id"]
    a=await _person(client,owner,company,branch,"Inline","inline@example.com")
    b=await _person(client,owner,company,branch,"Reuse","reuse@example.com")
    await _salary(client,owner,a["id"],"100000")
    key=f"{kind}_type_id";catalog=f"/{kind}-types";path=f"/employees/{a['id']}/{kind}s"
    body=dict(title="  New adjustment  ",frequency="ONE_OFF",amount="1000",start_date="2026-03-01")
    if kind=="deduction":body["category"]="COMPANY"
    created=await client.post(path,headers=owner,json=body)
    assert created.status_code==201,created.text
    record=created.json();assert record["type_name"]=="New adjustment"
    repeated=await client.post(f"/employees/{b['id']}/{kind}s",headers=owner,json={**body,"title":"new ADJUSTMENT"})
    assert repeated.status_code==201,repeated.text
    assert repeated.json()[key]==record[key]
    types=(await client.get(catalog,headers=owner,params={"company_id":company})).json()
    assert len(types)==1
    if kind=="deduction":assert types[0]["category"]=="COMPANY"
    changed=await client.patch(path+f"/{record['id']}",headers=owner,json={**body,"title":"Updated title"})
    assert changed.status_code==200 and changed.json()["type_name"]=="Updated title",changed.text
    # Choosing another title does not rename the shared original for other staff.
    unchanged=(await client.get(f"/employees/{b['id']}/{kind}s",headers=owner)).json()
    assert unchanged[0]["type_name"]=="New adjustment"
    invalid=await client.post(path,headers=owner,json={**body,"title":"Rollback title","frequency":"RECURRING","start_date":"2026-03-05","end_date":"2026-03-01"})
    assert invalid.status_code==400,invalid.text
    types=(await client.get(catalog,headers=owner,params={"company_id":company})).json()
    assert "Rollback title" not in {item["name"] for item in types}
    for patch in [{"title":"   "},{"title":None},{key:record[key]}]:
        rejected=await client.post(path,headers=owner,json={**body,**patch})
        assert rejected.status_code==422,rejected.text
    inactive_body={"company_id":company,"name":"Inactive title","is_active":False}
    if kind=="deduction":inactive_body["category"]="PERSONAL"
    inactive=await client.post(catalog,headers=owner,json=inactive_body)
    assert inactive.status_code==201,inactive.text
    assert (await client.post(path,headers=owner,json={**body,"title":"Inactive title"})).status_code==400
    foreign,foreign_owner=await workspace(client,"inline-foreign@example.com")
    foreign_type_body={"company_id":foreign["company"]["id"],"name":"Foreign type"}
    if kind=="deduction":foreign_type_body["category"]="PERSONAL"
    foreign_type=await client.post(catalog,headers=foreign_owner,json=foreign_type_body)
    assert foreign_type.status_code==201,foreign_type.text
    supplied={k:v for k,v in body.items() if k!="title"}
    rejected=await client.post(path,headers=owner,json={**supplied,key:foreign_type.json()["id"]})
    assert rejected.status_code==400,rejected.text
    admin=await _admin_login(client)
    platform=await client.post(f"/platform/tenants/{w['tenant']['id']}{path}",headers=admin,json={**body,"title":"Platform title"})
    assert platform.status_code==201,platform.text
    run=await _run(client,owner,company,branch,3,approve=False)
    slip=next(p for p in run["payslips"] if p["employee_id"]==a["id"])
    lines={line["name"]:Decimal(line["amount"]) for line in slip["lines"]}
    assert lines["Updated title"]==Decimal("1000") and lines["Platform title"]==Decimal("1000")
