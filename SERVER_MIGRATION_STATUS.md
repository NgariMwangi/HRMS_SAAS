# Live SaaS migration completed - 11 November 2026

Server: `37.60.242.201`; deployment: `/root/apps/HRMS_SAAS`.
Destination database: `hrms` in `hrms-saas-postgres-1`, still bound to loopback
port 5433. Source: `hrms_kenya1`. Source records were never modified.

## Organization and owner preserved

Workspace: Nexgen (`3373eeb5-77e2-4932-b3e8-c9cda9a8052f`).
Existing Nexgen company: `323324db-0fab-46aa-9912-bc9165f8ac52`.
Existing Head Office: `87bbf174-ccbb-4abe-93b6-a82b1d5a0961`.
Existing owner: `b22e083f-be20-4a44-a189-c511e2a021c9`.
The owner's email, role and password hash were preserved.

The user confirmed BOTH Uganda and Tanzania. Nexgen now has Head Office,
Uganda (UGX) and Tanzania (TZS). WashFlow Kenya Limited is in the same workspace,
with Head Office, Thindigua, Embakasi, Parklands and Buruburu. Total: two companies,
eight branches, one workspace.

## Imported live

| Data | Destination count |
|---|---:|
| Employees | 111 (Nexgen 74, WashFlow 37) |
| Login accounts | 101 (existing owner + 100 unchanged source password hashes) |
| Departments / job titles | 14 / 51 |
| Source salary versions | 104 |
| Historical-only compensation references | 101 |
| Employee deductions / positive benefit schedules | 117 / 145 |
| Leave types / requests / balances | 13 / 132 / 126 |
| Employee supervisor links | 103 |
| Lifecycle history entries | 210 |
| Employee payslips | 452 |
| Branch payroll runs | 62 (split from 30 source company/country runs) |
| Consultants / consultant pay snapshots | 2 / 16 |
| Payment ledger entries | 130 |
| Closed overtime requests | 3 |
| Retained source records | 12,010 |
| Available referenced upload files | 3 leave attachments |

Migrations applied through `052_closed_overtime`. The frontend, backend and
reminder worker were rebuilt and deployed. All employee and consultant gross,
deduction and net snapshots reconcile exactly to source values. No historical
taxes were recalculated. Historical-only compensation is excluded from salary
editing, payroll eligibility and current/future payroll calculations.

The source data snapshot was captured at `2026-11-11T11:55:14.310815+00:00`
(14:55 EAT). A subsequent full source-table comparison found no changes before
production import. This was a one-time transfer, not a synchronization service.
Do not continue entering new business records in both systems expecting sync.

## Rehearsal and validation

Two isolated destination clones were used: `hrms_migration_stage_20261111` and
`hrms_migration_final_20261111`. The complete transactional import and API
verification passed before live import. Live verification then passed as well:
all 452 employee snapshots and 100 imported password hashes match, both company
employee lists and leave balances load, the employee portal works, owner-only
source history access is enforced, and Kenya/Uganda/Tanzania sample PDFs render.
No actual emails were sent by the migration or verification scripts.

Local regression checks passed (17 payroll/workforce/organization tests and 15
safety/calculation tests). The frontend production build passed; existing bundle
size and RolesSettings import warnings remain.

## Retained differences and limitations

- Fourteen referenced upload files were already missing from the source's current
  storage: three employee photos and eleven older leave attachments. Their
  original references are preserved in imported history. The three available
  leave attachments were copied into employee documents. Missing files require
  an older source upload backup to restore; no file content was fabricated.
- One zero-value benefit schedule is retained in imported history rather than
  becoming a positive-amount payable benefit.
- Closed source overtime had no recorded rate or amount; these values remain
  null and display as not recorded. No invented overtime payment was created.
- One duplicate job-title label was disambiguated with its source code, retaining
  both original job-title identities and their employee links.
- Source bank data is in employee bank settings; extra source fields such as
  addresses, passport details and employer metadata remain owner-readable in
  **Payroll > Imported history**. Source audit/statutory/configuration records
  are retained there instead of inventing new SaaS activities or rate packs.
- Existing owner access was preserved. Assigned legacy supervisors received only
  scoped team-leave review capability in addition to employee permissions.
  The legacy finance reviewer was imported conservatively; its broader payroll
  approval/management permissions require owner review in workspace roles.
- Target leave balances preserve source closing balances before pending-leave
  reservations. The SaaS reserves pending leave separately and follows its own
  configured accrual policy after the migration cutover.

## Backups and operational artifacts

Protected directory: `/root/backups/hrms-saas-migration-20261111T113810Z`.

Initial and final source dumps, original SaaS database/code/images, the confirmed
organization mapping, the consistent JSON snapshot, the source upload copy,
rehearsal reports, and live import/verification logs are retained there. Database
backups include `saas-final-before-business-import.dump` and
`saas-after-complete-import.dump`; custom-format backup listings were verified.
These artifacts contain sensitive business data and must remain root-restricted.
No operational passwords or database credentials are stored in this document.

The importer (`backend/scripts/import_legacy_hrms.py`) defaults to a complete
rollback rehearsal. It rejects a nonempty destination, keeps financial snapshots,
uses deterministic origin IDs, redacts archived credentials and preserves the
existing owner. Reapplying an identical already-imported snapshot is a no-op;
a different snapshot is rejected rather than silently overwriting live records.
