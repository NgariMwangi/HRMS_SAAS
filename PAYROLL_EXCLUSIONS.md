# Exclude employees from a payroll run

Select a period and click **Run payroll** (or **Rerun** on a draft). A review panel opens before any payroll calculation. Search by name or employee number and tick the employees to exclude, then choose **Confirm payroll run** or **Confirm rerun**. Cancel leaves the run unchanged.

Exclusions apply only to that company, branch and period. A draft rerun preselects its saved exclusions; untick people or use **Clear exclusions** to include them again. New periods start with no exclusions. Approved runs remain locked. Employee status and salary records are unchanged, and excluded people receive no payslip in that run. Missing-salary skips remain separate from deliberate exclusions.

The same review is available in tenant payroll and platform tenant payroll. Employee choices come from payroll-authorized endpoints, and the backend rejects exclusion IDs outside the selected company/branch.

Deployment requires migration `046_payroll_exclusions`, plus updated backend and frontend. Docker applies migrations on backend startup. For local Python, run `python -m alembic upgrade head` inside `backend`.

API: `POST /payroll/runs` accepts `excluded_employee_ids`. An explicit empty array clears exclusions; omitting the field preserves an existing draft's list. Run responses persist and return this list. `GET /payroll/employees?company_id=...&branch_id=...` supplies active employee IDs/names/numbers for the review. Platform equivalents use `/platform/tenants/{tenant_id}`.
