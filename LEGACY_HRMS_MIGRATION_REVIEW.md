# Existing HRMS migration review

Migration completion update: the live database transfer has now completed,
including both Uganda and Tanzania, under the existing workspace. See
`SERVER_MIGRATION_STATUS.md` for verified counts, backups and source-file
limitations. The remainder of this document records the original pre-migration
review and is not the current deployment status.

Implementation update: employee bank fields and a proration switch, active
consultant/fee/pay records, HR-managed overtime and a payment ledger have now
been added. See `WORKFORCE_PAYMENTS.md` for the implemented scope and deployment.
The findings below describe the original review; these additions do not perform
the migration or remove the need for reconciliation and an importer.

Reviewed 11 November 2026. Source code: `C:\Users\USER\Desktop\hrms`.
Source database: `hrms_kenya1`. Inspection used read-only transactions; no source
or destination business records were changed. Counts are a point-in-time inventory.
This is a review, not an executable importer or a completed transfer.

## Source inventory

| Records | Count |
|---|---:|
| Companies / employer profiles | 2 / 2 |
| Branches | 8 |
| Employees | 111 |
| Login accounts | 101 |
| Departments / job titles | 14 / 51 |
| Salary records / allowance assignments | 104 / 11 |
| Employee benefit schedules / payment records | 146 / 1 |
| Employee deductions | 117 |
| Payroll runs / employee payroll items | 30 / 452 |
| Statutory remittance snapshots | 1,700 |
| Payroll exclusions | 3 |
| Leave types / requests / balances | 13 / 130 / 126 |
| Employee assignment history | 210 |
| Consultants / compensation / payroll items | 2 / 2 / 16 |
| Overtime requests | 3 |
| Audit logs | 8,385 |

Nexgen FuelWorks has 74 employees and three branches (Kenya, Uganda, Tanzania).
WashFlow Kenya Limited has 37 employees and five Kenyan branches. Attendance,
employee documents, casual workers/payments, saved reports, and notifications
currently have zero rows. Local uploads may still contain photos or leave
attachments; inspect actual production files before deciding there is nothing
to copy.

## Mapping

| Source | SaaS destination / treatment |
|---|---|
| companies + employers | Explicit tenant/company mapping; merge employer contact and registration fields where supported |
| branches | branches with country/currency foreign keys resolved from codes |
| departments, job_titles | Company-scoped catalogues, after checking required branch scope |
| employees | employees; integer IDs mapped to UUIDs |
| middle_name, hire_date, termination_date | other_names, date_joined, date_ended |
| national_id, kra_pin, nssf_number, nhif_number | id_number, pin_number, nssf_no, shif_no |
| email, secondary_email | Work email, personal email; preserve login email independently |
| manager_id | employee_supervisors, populated after all employee IDs exist |
| users + user_roles | users plus SaaS access roles; explicit privilege mapping |
| employee_salaries + employee_allowances | Effective-dated employee_compensation and employee_pay_lines |
| employee_deductions | deduction_types and employee_deductions; preserve remaining balances |
| employee_benefits | benefit_types and employee_benefits; distinguish already-paid one-offs |
| payroll_runs + payroll_items | Branch-specific payroll_runs, payroll_payslips and payroll_payslip_lines |
| payroll_run_exclusions | Mapped employee UUIDs on the appropriate branch run |
| leave_types | leave_types with explicit accrual/day-basis mapping |
| leave_requests | leave_requests and separate supervisor/HR leave_decisions |
| leave_balances | Reconciled extra_days adjustments, not direct closing_balance copies |
| employee_assignment_history | Convert supported changes to lifecycle events; preserve complete source segments in an archive |
| public_holidays | Map company/country scopes and deduplicate target seeded holidays |
| audit_logs | Preserve original audit archive and origin IDs; do not invent SaaS activity |

## Differences requiring handling

1. **Destination identity and isolation.** The source uses integer keys and
   company-based isolation; SaaS uses UUIDs and tenant/company isolation. Maintain
   durable source-system/table/ID to destination UUID mappings. Decide whether the
   two companies share a workspace or have separate tenants. Match existing SaaS
   companies, branches, employee records and globally unique login emails before
   inserting; avoid creating duplicates. The target database and intended company
   IDs have not yet been selected or compared in this review.

2. **Employee completeness.** Four employees have no work email and one has no
   employee number. Work email may remain blank, but notifications then cannot be
   delivered. Generate an agreed stable number for the missing number. Source
   numbers are unique per branch; target requires company-wide uniqueness. No
   company-wide number collisions were found. Aggregate checks also found no
   duplicate work emails after case/whitespace normalization, or duplicate active
   national ID/NSSF/SHIF values under the tested source rules. Revalidate lengths,
   whitespace, statuses and destination conflicts in an importer dry run.

3. **Fields absent from SaaS employee records.** 107 employees have bank account
   details. The SaaS Employee model has no bank account fields. Gender, marital
   status, nationality, passport, address and several probation/contract details
   also lack direct fields. Add proper destination support or preserve them in a
   clearly identified legacy archive; never silently discard them. Emergency
   contacts can map to next-of-kin only without inventing a relationship.

4. **Passwords and roles.** All 101 accounts use Werkzeug scrypt hashes. Current
   SaaS verify_password already supports this format, so hashes can be copied
   unchanged without knowing passwords. Existing sessions will not transfer.
   Source roles include 99 EMPLOYEE assignments, one ADMIN and one
   FINANCE_PAYROLL_APPROVER. Do not turn source superusers into platform admins
   automatically. Select workspace owners and map finance permissions explicitly.
   Three accounts are not linked to employee profiles. Preserve inactive status;
   review password-change/lockout flags because destination fields differ.

5. **Historical payroll.** Source runs are company/country/month scoped; target
   runs are branch/period scoped. Resolve each item's branch at that historical
   month using assignment history rather than only today's branch. Source
   history spans January-August 2026 and includes draft, approved and paid runs.
   Target has only DRAFT and APPROVED. Preserve paid/finance metadata separately
   and agree status mapping. Import original financial snapshots rather than
   recalculating old taxes with current packs. Link valid compensation snapshots,
   currency and pack references, preserving source rule provenance separately.
   Some source runs may have no employee items; report rather than silently drop.

6. **Payroll reconciliation.** All 452 employee payroll items have earnings and
   deductions JSON. For 23, gross minus net differs from the simple sum of PAYE,
   NSSF, SHIF, housing levy and other_deductions columns. This is not proof of bad
   data: source payroll_engine also includes pension deduction lines. Reconcile
   complete JSON lines, top-level amounts and statutory snapshots for each item;
   stop import on unexplained differences. Four salary records contain fixed
   employee pension amounts. Do not count statutory snapshots twice as deductions.

7. **Salary and allowances.** Source has both fixed salary allowance columns and
   separate dated employee_allowances. Reconstruct changes at every effective
   date, including allowance end dates, and follow source calculation rules to
   avoid double counting. SaaS compensation rows do not directly model every
   source allowance's end date or taxable/pensionable flags. Twenty-one employees
   have prorate_payroll disabled; the new SaaS joining-date calculation has no
   such switch. Make that policy difference explicit before live payroll.

8. **Benefits/deductions.** All 117 source deductions currently use fixed amounts;
   percent deduction support is unnecessary for this dataset. Remaining balances
   must become opening outstanding amounts at cutover, accounting for imported
   recovery history. Of 146 benefits, 139 are taxable/pensionable one-offs, six
   are taxable/pensionable monthly schedules and one is neither taxable nor
   pensionable. SaaS currently treats benefits as taxable/pensionable cash income,
   so the exceptional benefit requires explicit support or archival treatment.
   Source also records one separate benefit payment: do not schedule it to pay
   again after transfer.

9. **Leave.** There are 96 approved requests, 29 pending supervisor review, two
   pending HR review and three rejected. Preserve request days and decision
   timestamps/actors. Source stores opening/accrued/used/adjusted/closing values;
   SaaS calculates entitlement/usage and stores extra_days. Reconcile remaining
   leave per person/type/year at an agreed cutover date after importing approved
   requests; otherwise used leave may be deducted twice. Source unlimited/manual
   and other policy flags also need explicit treatment. Import directly through
   a controlled importer so historical requests do not queue new leave emails.

10. **Unsupported records.** Consultants and consultant payroll, overtime requests,
    statutory remittance tracking and some source approval/payment workflow
    fields have no direct equivalent found in the inspected SaaS models. Preserve
    them in an accessible archive or extend the SaaS before claiming a complete
    migration. Local and server file storage are separate from database rows.

## Proposed transfer sequence

1. Select the destination SaaS database, tenants/companies and owner accounts.
   Agree the cutover date and treatment of unsupported fields and records.
2. Create a source backup and destination backup; rehearse against a staging copy.
3. Build an idempotent importer with read-only source access, explicit source IDs,
   a dry-run report, safe company boundaries and conflict detection. Keep source
   credentials outside repository files and generated reports.
4. Import organization and catalogue records, employees, logins and supervisors;
   then salary/allowance schedules, deductions, benefits, history and files.
5. Import historical payroll snapshots and leave requests/decisions, reconcile
   outstanding deductions and leave balances, and preserve unsupported records.
6. Verify per-company/per-branch counts, every payroll item's earnings/deductions/
   net, monthly aggregate totals, leave balances, account roles and login behavior.
   Check both portals and sample PDFs; suppress migration-time outgoing emails.
7. Stop source writes for the final transfer window, apply any changes since the
   rehearsal, reconcile again and switch users. Retain source read-only for audit
   and rollback. Do not merge by employee name alone or restore source tables over
   the SaaS schema.

No importer or production transfer has been executed as part of this review.
