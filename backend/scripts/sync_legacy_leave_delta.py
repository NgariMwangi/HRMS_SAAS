"""Reconcile the reviewed November 2026 legacy leave delta; rollback by default.

Run only against the authorized destination with protected source snapshots.
No credentials, emails, payroll calculations or account changes are performed.
"""
import argparse
import asyncio
import hashlib
import json
import mimetypes
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from app.db.session import get_session_maker, dispose_engine
from app.models import Employee, LeaveType, LeaveRequest, LeaveDecision, LeaveBalance, EmployeeDocument, DocumentCategory
from app.models.legacy_import import LegacyImportRecord
from app.services.leave_balances import entitled_days
from scripts.prepare_legacy_organization import legacy_id
from scripts.import_legacy_hrms import scrub

STATUS = dict(pending='PENDING_SUPERVISOR', pending_hr='PENDING_HR', approved='APPROVED', rejected='REJECTED', cancelled='CANCELLED')

def dt(v):
    return datetime.fromisoformat(v) if v else None

def values(r):
    return dict(employee_id=legacy_id('employees', r['employee_id']), leave_type_id=legacy_id('leave_types', r['leave_type_id']),
                start_on=date.fromisoformat(r['start_date']), end_on=date.fromisoformat(r['end_date']),
                days=Decimal(r['days_requested']), reason=r.get('reason'), status=STATUS[r['status']])

async def main(args):
    old = json.loads(Path(args.baseline).read_text())
    raw = Path(args.current).read_bytes()
    current = json.loads(raw)
    mapping = json.loads(Path(args.mapping).read_text())
    tenant = UUID(mapping['tenant_id'])
    before = {r['id']: r for r in old['tables']['leave_requests']}
    after = {r['id']: r for r in current['tables']['leave_requests']}
    # Explicit reviewed scope: any additional business changes require a new review.
    assert set(after)-set(before) == {148,149,150,151}
    assert set(before)-set(after) == {143}
    changed = {i for i in before.keys() & after.keys() if any(before[i].get(k) != after[i].get(k) for k in
               ['status','supervisor_reviewed_by_id','supervisor_notes','review_notes','reviewed_by_id'])}
    assert changed == {83,100,103,140,141,147}
    report = dict(mode='APPLY' if args.apply else 'ROLLBACK', added=[], updated=[], cancelled=[], balances=[], documents=[], conflicts=[], already_current=[])
    async with get_session_maker()() as s:
        await s.execute(text("SELECT set_config('app.is_platform_admin','true',true)"))
        await s.execute(text('LOCK TABLE leave_requests, leave_decisions, leave_balances, legacy_import_records IN SHARE ROW EXCLUSIVE MODE'))
        archives = {(a.source_table,a.source_id): a for a in (await s.scalars(select(LegacyImportRecord).where(LegacyImportRecord.tenant_id == tenant))).all()}

        def archive(table, r, company, destination_table=None, destinations=None):
            key = (table,str(r['id']))
            a = archives.get(key)
            if a is None:
                a = LegacyImportRecord(id=legacy_id('archive', f"{table}/{r['id']}"), tenant_id=tenant,
                    company_id=company, source=old['source'], source_table=table, source_id=str(r['id']),
                    destination_table=destination_table, destination_ids=destinations or [])
                s.add(a); archives[key] = a
            a.payload = scrub(r)
            a.snapshot_sha256 = hashlib.sha256(raw).hexdigest()

        async def actor(source_id):
            if source_id is None: return None
            a = archives.get(('users',str(source_id)))
            assert a and a.destination_ids, f'Missing actor mapping {source_id}'
            return UUID(a.destination_ids[0])

        for i in sorted(changed | (set(after)-set(before)) | (set(before)-set(after))):
            target = await s.get(LeaveRequest, legacy_id('leave_requests',i))
            source = after.get(i)
            if source is None:
                if target is None or target.status == 'CANCELLED':
                    report['already_current'].append(i); continue
                if any(getattr(target,k) != v for k,v in values(before[i]).items()):
                    report['conflicts'].append(f'leave {i}: SaaS edited; source deletion not applied'); continue
                target.status = 'CANCELLED'
                a=archives[('leave_requests',str(i))]
                a.payload = dict(a.payload, incremental_source_deleted=True)
                report['cancelled'].append(i)
                continue
            wanted = values(source)
            employee = await s.get(Employee,wanted['employee_id'])
            assert employee is not None
            company = UUID(mapping['companies'][str(next(r['company_id'] for r in current['tables']['employees'] if r['id']==source['employee_id']))])
            assert employee.company_id == company, f'Employee transferred for leave {i}; review required'
            if target is not None:
                if target.company_id != company: raise ValueError('Company mismatch')
                if any(getattr(target,k) != v for k,v in wanted.items()):
                    if i not in before or any(getattr(target,k) != v for k,v in values(before[i]).items()):
                        report['conflicts'].append(f'leave {i}: SaaS and legacy differ'); continue
                    for k,v in wanted.items(): setattr(target,k,v)
                    report['updated'].append(i)
                else: report['already_current'].append(i)
            else:
                assert i not in before, f'Previously imported leave {i} missing in SaaS'
                duplicate = await s.scalar(select(LeaveRequest.id).where(LeaveRequest.employee_id==employee.id,
                    LeaveRequest.leave_type_id==wanted['leave_type_id'], LeaveRequest.start_on==wanted['start_on'],
                    LeaveRequest.end_on==wanted['end_on'], LeaveRequest.status!='CANCELLED'))
                assert duplicate is None, f'Possible duplicate SaaS application for source {i}'
                target=LeaveRequest(id=legacy_id('leave_requests',i), company_id=company, **wanted,
                    requested_as='EMPLOYEE', approval_mode='SUPERVISOR_THEN_HR', requested_by_employee_id=employee.id,
                    created_at=dt(source['created_at']))
                s.add(target); await s.flush(); report['added'].append(i)
            for step,actor_key,time_key,note_key in [('SUPERVISOR','supervisor_reviewed_by_id','supervisor_reviewed_at','supervisor_notes'),('HR','reviewed_by_id','reviewed_at','review_notes')]:
                if not source.get(time_key): continue
                identity=legacy_id('leave_decisions',f'{i}/{step}')
                decision=await s.get(LeaveDecision,identity)
                decision_values=dict(step=step, decision='REJECTED' if source['status']=='rejected' and (step=='HR' or not source.get('reviewed_at')) else 'APPROVED',
                    actor_user_id=await actor(source.get(actor_key)), note=source.get(note_key), created_at=dt(source[time_key]))
                if decision is None:
                    s.add(LeaveDecision(id=identity, company_id=company, leave_request_id=target.id, **decision_values))
                else:
                    assert all(getattr(decision,k)==v for k,v in decision_values.items()), f'Decision conflict {i}/{step}'
            archive('leave_requests',source,company,'leave_requests',[str(target.id)])
            file=source.get('document_path')
            doc_id=legacy_id('leave_documents',i)
            if file and await s.get(EmployeeDocument,doc_id) is None:
                root=Path(args.uploads).resolve(); path=(root/file).resolve()
                assert path.is_relative_to(root) and path.is_file(), f'Missing document {i}'
                category=await s.scalar(select(DocumentCategory).where(DocumentCategory.company_id==company,DocumentCategory.system_key=='PERSONAL'))
                assert category is not None
                s.add(EmployeeDocument(id=doc_id, company_id=company, employee_id=employee.id,category_id=category.id,
                    filename=path.name, content_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                    file_bytes=path.read_bytes(), note=f'Imported attachment for legacy leave request #{i}', created_at=dt(source['created_at'])))
                report['documents'].append(i)
        await s.flush()
        # Only these source balances changed. Preserve every unrelated SaaS adjustment,
        # including the corrected Alex annual balance and SaaS-only leave requests.
        old_balances={r['id']:r for r in old['tables']['leave_balances']}
        old_people={r['id']:r for r in old['tables']['employees']}
        old_types={r['id']:r for r in old['tables']['leave_types']}
        from types import SimpleNamespace
        for row in current['tables']['leave_balances']:
            i=row['id']
            if i not in {27,42,70,127,128}: continue
            employee=await s.get(Employee,legacy_id('employees',row['employee_id']))
            category=await s.get(LeaveType,legacy_id('leave_types',row['leave_type_id']))
            assert employee and category and employee.company_id==category.company_id
            balance=await s.scalar(select(LeaveBalance).where(LeaveBalance.employee_id==employee.id,LeaveBalance.leave_type_id==category.id,LeaveBalance.year==row['year']))
            source_usage=sum((Decimal(r['days_requested']) for r in after.values() if r['employee_id']==row['employee_id'] and r['leave_type_id']==row['leave_type_id'] and r['status']=='approved' and int(r['start_date'][:4])==row['year']),Decimal(0))
            assert source_usage == Decimal(row['used']), f'Source usage mismatch {i}'
            as_of=datetime.fromisoformat(current['captured_at']).date()
            wanted=Decimal(row['closing_balance'])+source_usage-entitled_days(category,employee.date_joined,row['year'],as_of)
            if balance and balance.extra_days != wanted:
                if i not in old_balances:
                    report['conflicts'].append(f'balance {i}: existing SaaS adjustment'); continue
                prior=old_balances[i]; prior_type=old_types[row['leave_type_id']]
                legacy_type=SimpleNamespace(days=Decimal(prior_type['days_per_year']),accrued=prior_type['accrues_monthly'],accrual_per_month=Decimal(prior_type.get('days_per_month') or 0))
                prior_usage=sum((Decimal(r['days_requested']) for r in before.values() if r['employee_id']==row['employee_id'] and r['leave_type_id']==row['leave_type_id'] and r['status']=='approved' and int(r['start_date'][:4])==row['year']),Decimal(0))
                joined=old_people[row['employee_id']].get('hire_date')
                expected=Decimal(prior['closing_balance'])+prior_usage-entitled_days(legacy_type,date.fromisoformat(joined) if joined else None,row['year'],datetime.fromisoformat(old['captured_at']).date())
                if balance.extra_days != expected:
                    report['conflicts'].append(f'balance {i}: SaaS edited; adjustment retained'); continue
            if balance is None:
                balance=LeaveBalance(id=legacy_id('leave_balances',i),company_id=employee.company_id,employee_id=employee.id,leave_type_id=category.id,year=row['year'],extra_days=wanted);s.add(balance)
            else: balance.extra_days=wanted
            archive('leave_balances',row,employee.company_id,'leave_balances',[str(balance.id)])
            report['balances'].append(dict(source_id=i,extra_days=str(wanted)))
        # New source audit history is archived, never replayed as a live action.
        n=0
        for row in current['tables']['audit_logs']:
            if ('audit_logs',str(row['id'])) not in archives:
                cid=row.get('company_id')
                archive('audit_logs',row,UUID(mapping['companies'][str(cid)]) if cid else None);n+=1
        report['archived_audit_records']=n
        await s.flush()
        if report['conflicts']: raise ValueError(json.dumps(report,default=str))
        if args.apply: await s.commit()
        else: await s.rollback()
    print(json.dumps(report,indent=2))
    await dispose_engine()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['baseline','current','mapping','uploads']:p.add_argument('--'+name,required=True)
    p.add_argument('--apply',action='store_true')
    asyncio.run(main(p.parse_args()))
