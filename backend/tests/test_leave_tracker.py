import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from app.db.session import get_session_maker
from app.models import Employee, LeaveBalance, LeaveRequest, LeaveType
from tests.test_access import workspace, staff_login
from tests.test_reports import create, person


@pytest.mark.usefixtures('clean_tenant_tables')
async def test_tracker_balances_filters_exports_and_access(client):
    w, owner = await workspace(client)
    cid=w['company']['id']
    employee=await person(client,owner,w,'=Tracker')
    other=await person(client,owner,w,'Other')
    leave=await create(client,owner,'/leave-types',dict(company_id=cid,name='Annual',days=21,accrued=False))
    unlimited=await create(client,owner,'/leave-types',dict(company_id=cid,name='Unpaid',days=0,accrued=False))
    async with get_session_maker()() as s:
        base=dict(company_id=uuid.UUID(cid),employee_id=uuid.UUID(employee['id']),leave_type_id=uuid.UUID(leave['id']))
        s.add(LeaveBalance(**base,year=2026,extra_days=Decimal('2')))
        for status,days,year in [('APPROVED','0.5',2026),('PENDING_HR','0.25',2026),('REJECTED','5',2026),('APPROVED','8',2025)]:
            s.add(LeaveRequest(**base,start_on=date(year,3,2),end_on=date(year,3,2),days=Decimal(days),status=status,requested_as='HR',approval_mode='HR_ONLY'))
        p=await s.get(Employee,uuid.UUID(other['id']));p.status='TERMINATED'
        await s.commit()
    params=dict(company_id=cid,start_on='2026-01-01',end_on='2026-12-31')
    response=await client.get('/reports/leave-tracker',headers=owner,params=params)
    assert response.status_code==200,response.text
    report=response.json();assert report['total_rows']==1
    row=report['rows'][0];key=leave['id']
    assert row[key+'_entitled']=='23.00' and row[key+'_used']=='0.50' and row[key+'_remaining']=='22.25'
    assert row[unlimited['id']+'_remaining'] is None
    selected=await client.get('/reports/leave-tracker',headers=owner,params={**params,'leave_type_id':key,'q':'=Tracker'})
    assert len(selected.json()['tracker_types'])==1
    assert (await client.get('/reports/leave-tracker',headers=owner,params={**params,'q':'%'})).json()['rows']==[]
    book=await client.get('/reports/leave-tracker/xlsx',headers=owner,params={**params,'page_size':1})
    assert book.status_code==200,book.text
    sheet=load_workbook(io.BytesIO(book.content)).active
    assert sheet.freeze_panes=='C5' and sheet['B5'].data_type=='s'
    assert sheet['B5'].value.startswith('=Tracker')
    assert sheet['C5'].value==23 and sheet['D5'].value==.5 and sheet['E5'].value==22.25
    pdf=await client.get('/reports/leave-tracker/pdf',headers=owner,params=params)
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF')
    _,_,staff=await staff_login(client,owner,w,'TrackerStaff')
    assert (await client.get('/reports/leave-tracker/xlsx',headers=staff,params=params)).status_code==403
    foreign,foreign_owner=await workspace(client,'foreign-tracker@example.com')
    assert (await client.get('/reports/leave-tracker',headers=owner,params={**params,'company_id':foreign['company']['id']})).status_code==403
    assert (await client.get('/reports/leave-tracker',headers=owner,params={**params,'leave_type_id':str(uuid.uuid4())})).status_code==400
