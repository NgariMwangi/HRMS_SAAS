"""Company-scoped employee leave matrix, using the same rules as leave balances."""
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from app.models import Employee, LeaveBalance, LeaveRequest, LeaveType
from app.services.leave_balances import as_of_for_year, snapshot


async def build(session, company_id, year, people_filters, branch_id=None, leave_type_id=None):
    from app.services.reports import MAX_ROWS, column, decimal, fail, metric, name
    types = list((await session.scalars(select(LeaveType).where(LeaveType.company_id == company_id).order_by(LeaveType.sort_order, LeaveType.name))).all())
    if leave_type_id:
        if leave_type_id not in {t.id for t in types}:
            fail('Leave type does not belong to this company')
        types = [t for t in types if t.id == leave_type_id]
    query = select(Employee).where(*people_filters, Employee.status == 'ACTIVE').order_by(Employee.last_name, Employee.first_name, Employee.id)
    if branch_id:
        query = query.where(Employee.branch_id == branch_id)
    people = list((await session.scalars(query.limit(MAX_ROWS + 1))).all())
    if len(people) > MAX_ROWS:
        fail('Too many employees. Narrow the branch, department or search.', 422)
    ids = [p.id for p in people]
    type_ids = [t.id for t in types]
    adjustments = {(b.employee_id, b.leave_type_id): b.extra_days for b in (await session.scalars(select(LeaveBalance).where(
        LeaveBalance.company_id == company_id, LeaveBalance.employee_id.in_(ids), LeaveBalance.leave_type_id.in_(type_ids), LeaveBalance.year == year))).all()}
    totals = defaultdict(lambda: [Decimal(0), Decimal(0)])
    requests = (await session.scalars(select(LeaveRequest).where(LeaveRequest.company_id == company_id,
        LeaveRequest.employee_id.in_(ids), LeaveRequest.leave_type_id.in_(type_ids), LeaveRequest.start_on >= date(year, 1, 1),
        LeaveRequest.start_on <= date(year, 12, 31), LeaveRequest.status.in_(['APPROVED', 'PENDING_HR', 'PENDING_SUPERVISOR'])))).all()
    for r in requests:
        totals[r.employee_id, r.leave_type_id][0 if r.status == 'APPROVED' else 1] += r.days
    today = datetime.now(ZoneInfo('Africa/Nairobi')).date()
    rows = []
    total_used = Decimal(0)
    total_pending = Decimal(0)
    for p in people:
        row = dict(id=str(p.id), employee_id=str(p.id), employee_number=p.employee_number, employee=name(p))
        for t in types:
            used, pending = totals[p.id, t.id]
            balance = snapshot(p, t, year, adjustments.get((p.id, t.id), Decimal(0)), used, pending, as_of_for_year(year, today))
            key = str(t.id)
            row[key+'_entitled'] = None if balance.unlimited else decimal(balance.entitled + balance.extra)
            row[key+'_used'] = decimal(balance.used)
            row[key+'_remaining'] = None if balance.unlimited else decimal(balance.remaining)
            row[key+'_pending'] = decimal(balance.pending)
            total_used += used
            total_pending += pending
        rows.append(row)
    columns = [column('employee_number', 'Employee no.'), column('employee', 'Employee')]
    for t in types:
        columns.extend(column(str(t.id)+'_'+key, f'{t.name} - {label}', 'decimal') for key, label in [('entitled','Entitled'),('used','Used'),('remaining','Remaining')])
    return dict(rows=rows, columns=columns, total_rows=len(rows), tracker_types=[dict(id=str(t.id), name=t.name) for t in types],
        statuses=[], selected_status='ALL', breakdowns=[], year=year,
        summary=[metric('Active employees',len(people)), metric('Leave types',len(types)), metric('Approved days',total_used), metric('Pending days',total_pending)],
        note='Active employees only. Entitled includes HR adjustments and accrued days as of the selected year (today for the current year). Used includes approved applications starting in that year. Remaining also subtracts pending reservations. Blank entitlement and remaining mean unlimited leave. Fractional days are preserved.')


def xlsx_bytes(report):
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = 'Leave Tracker'
    ws.append([f"{report['company']} - Leave Tracker {report['year']}"])
    ws.append([report['branch'] + ' | ' + report['department']])
    ws.append(['Employee no.', 'Employee'] + [value for t in report['tracker_types'] for value in [t['name'], '', '']])
    ws.append(['', ''] + [value for _ in report['tracker_types'] for value in ['Entitled', 'Used', 'Remaining']])
    for i, _ in enumerate(report['tracker_types']):
        start = 3+i*3
        ws.merge_cells(start_row=3,start_column=start,end_row=3,end_column=start+2)
    for col in [1,2]:
        ws.merge_cells(start_row=3,start_column=col,end_row=4,end_column=col)
    for row in report['rows']:
        values=[]
        for c in report['columns']:
            v=row.get(c['key'])
            values.append(Decimal(v) if v is not None and c['kind']=='decimal' else v)
        ws.append(values)
        for cell in ws[ws.max_row]:
            if isinstance(cell.value,str): cell.data_type='s'  # Names cannot become Excel formulas.
            else: cell.number_format='0.##'
    accent=(report.get('theme_color') or '#4F46E5').lstrip('#')
    # Choose a legible foreground even for a company with a very light colour.
    rgb=[int(accent[i:i+2],16) for i in (0,2,4)]
    foreground='000000' if sum(a*b for a,b in zip(rgb,[.299,.587,.114]))>155 else 'FFFFFF'
    for row in ws.iter_rows(min_row=3,max_row=4):
        for c in row:
            c.fill=PatternFill('solid',fgColor=accent);c.font=Font(bold=True,color=foreground)
            c.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True)
    ws.column_dimensions['A'].width=20;ws.column_dimensions['B'].width=32
    for col in range(3,ws.max_column+1): ws.column_dimensions[get_column_letter(col)].width=15
    for row in ws.iter_rows(min_row=5):
        for c in row:
            if c.row%2: c.fill=PatternFill('solid',fgColor='F1F5F9')
            if isinstance(c.value,(int,float,Decimal)) and c.value<0: c.font=Font(color='B91C1C')
    ws.freeze_panes='C5'
    ws.auto_filter.ref=f'A4:{get_column_letter(ws.max_column)}{max(4,ws.max_row)}'
    ws.sheet_properties.pageSetUpPr.fitToPage=True
    ws.page_setup.orientation='landscape';ws.page_setup.fitToWidth=1;ws.page_setup.fitToHeight=0
    ws.print_title_rows='1:4'
    ws.append([report['note']])
    ws.cell(ws.max_row,1).alignment=Alignment(wrap_text=True)
    for row in ws:
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = 's'  # Includes company names and leave headings.
    out=BytesIO();wb.save(out)
    return out.getvalue()
