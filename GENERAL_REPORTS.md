# General Reports

Open `/app/reports` or the **Reports** sidebar section. Each report has its own URL, filters, summaries, breakdowns, record table and CSV export:

- `/app/reports/headcount`
- `/app/reports/payroll`
- `/app/reports/attendance`
- `/app/reports/leave`
- `/app/reports/movement`

Select a company in the workspace header. Report filters can select **All branches** or a particular branch, department, status/change type, and employee name or number. Activity reports default to this month; quick ranges include last month, this quarter and this year. **Apply filters** updates the results. **Reset** restores defaults. Headcount is a current snapshot and does not use historical date filters.

Summaries and breakdowns include the complete filtered selection. Tables display 50 records per page. **Export CSV** exports all matching records, not just the visible page. Exports preserve decimal amounts and escape potential spreadsheet formulas in human-entered text. The API limits activity periods to 730 days and report selections to 50,000 records; narrow filters for larger datasets.

## What the reports mean

| Report | Date selection and calculations |
| --- | --- |
| Headcount | Current employee records and stored employment statuses. Groups by current department, branch and employment type. Includes active, suspended and terminated records unless filtered. |
| Payroll | Full saved payslips for runs whose **period end** falls within the selected dates. Approved runs are the default; drafts or all statuses can be selected. Totals remain separate by currency and use saved payroll amounts. Employee name/number and branch come from the payroll records; department filtering uses the employee's current department. |
| Attendance | Recorded attendance entries by work date and recorded branch. Missing entries are not counted as absences. Completed clock hours require both clock-in and clock-out. Current employee department is used for department filtering. |
| Leave | Requests overlapping the selected dates. Days represent the full stored request totals, not a prorated portion of a request. Summaries distinguish approved request days and pending requests. Branch and department use the current employee record. |
| Employee movement | Lifecycle events by effective date. Branch/department filters match either side of recorded changes, with current assignment as fallback for legacy events lacking those fields. Includes hire, rehire, suspension, reinstatement, role change, termination and extension. Private event notes and attachments are excluded. |

Reports do not infer historical headcount from current records, change payroll calculations, or modify employee data.

## Access

Migration `042_general_reports` grants `reports.view` to existing Owner/Admin/HR roles once. New tenants receive it through the permission catalog. Managers and Employees do not receive company reports by default. Custom roles can receive the permission in Roles settings, but each report also requires access to its source module:

| Report | Additional required permission (any listed) |
| --- | --- |
| Headcount | `people.view_all`, `people.manage` |
| Payroll | `payroll.manage` |
| Attendance | `attendance.manage` |
| Leave | `leave.view_all`, `leave.manage` |
| Employee movement | `lifecycle.view_all`, `lifecycle.manage` |

Report catalog, individual reports and CSV exports enforce permission checks on the server. Company ownership is checked against the authenticated tenant, and branch/department references must belong to that company. Report responses use `Cache-Control: no-store`. `/reports` is included in the Vite API proxy, service-worker navigation exclusions and network-only API handling.

Platform administrators can open the tenant's **More** section, choose the reporting company and use the same report interface. Platform endpoints under `/platform/tenants/{tenant_id}/reports` enforce platform authentication and tenant/company boundaries.

## Validation

`backend/tests/test_reports.py` covers current headcount, branch/department/search filters, pagination, complete CSV export, formula escaping, empty results, invalid input, live permission revocation, payroll confidentiality, tenant/company isolation, platform access, recorded attendance after transfer, missing clock-out, overlapping leave, historical movement, preserved payroll snapshots and separate KES/UGX totals. Existing access tests also run.

Run `python -m pytest tests/test_reports.py tests/test_access.py -q` from the backend using the existing test-database guard. Run `npm run build` from the frontend.

Existing demo records are used; this feature creates no demo records or changes to Performance or Recruitment. If a current-month report is empty, choose **This year** and apply the filters.
