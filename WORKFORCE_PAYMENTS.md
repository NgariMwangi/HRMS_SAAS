# Bank details, consultants, overtime and payments

Employee profiles and salary pages now include **Bank details and payroll
settings** for users with `payroll.manage`. Store the bank, branch, account number,
bank code and SWIFT code. Account numbers are text, preserving leading zeros.
These fields use separate protected endpoints and are not included in general
employee summaries. Account numbers are redacted from audit request summaries.
Employees cannot edit these financial settings through their contact profile.

The **Prorate salary** switch defaults on for all employees. Turn it off to retain
full monthly basic salary for a mid-period starter. Future starters remain
ineligible. Draft reruns use the current setting; approved snapshots do not change.
This allows the source HRMS's disabled-proration settings to be preserved during
a later import.

## Consultants

Open **Payroll → Consultants**. Add a consultant's identity, branch, bank account,
contract dates and agreed withholding rate. A rate must be explicitly entered;
the system does not choose a statutory rate. Consultants are separate from
employee records and do not receive employee login accounts automatically.

Choose **Fees** to add effective-dated monthly fees and allowances. Rates with a
new effective date preserve previous entries. Select a payroll month and choose
**Calculate month** for an individual consultant. This creates or recalculates a
draft pay record. It uses the latest applicable fee, snapshots branch currency,
name, payable days, gross, withholding rate/tax and net. Withholding is gross times
the entered percentage; employee statutory payroll components are not applied.
Consultant fees and allowances are prorated together when proration is enabled,
including partial contract start/end months. Full months receive 30/30.

Approve the draft before recording payments. Approved consultant pay cannot be
recalculated. Existing fee history cannot be reinterpreted in another currency:
create a new consultant record when changing to a branch with a different
currency. This first version calculates consultants individually, not in a batch,
and does not yet generate a separate consultant payslip PDF.

## Overtime

Open **Payroll → Overtime**. Payroll managers enter the employee, worked dates,
number of days (fractions supported), agreed daily rate, reason and payroll month.
The amount is days times daily rate, rounded to the branch currency. The rate is
entered by HR; this module does not assume a statutory overtime rate. Duplicate
pending/approved requests covering a worked date are rejected.

Payroll managers approve, decline or cancel pending requests. Approval creates
exactly one one-off employee benefit in the selected month. Repeated approval is
idempotent. Rerun an existing draft payroll to include it. An approved payroll must
be reopened first. The request preserves its original branch and currency;
approval is blocked if the employee's payment currency has since changed.
Overtime then follows the existing earnings/tax/payslip flow. Requests are managed
by HR in this version; employee self-service and separate supervisor approval are
not added by these changes.

## Payment history

Open **Payroll → Payment history**. Choose the payroll month, then an approved
employee payslip, approved consultant pay, or a benefit not yet included in
payroll. Record the amount, actual payment date, method, unique company payment
reference and optional note. **This records an already-made payment; it does not
send money or connect to a bank or M-Pesa.**

Employee/consultant pay supports partial settlements. The payable amount and
currency come from server-side snapshots. Payments exceeding the remaining
balance and reused references are rejected. Company/target row locks serialize
concurrent settlement attempts. The month filter refers to the earning/payroll
month; the actual payment date can be different.

Direct benefit payments must settle the full scheduled amount. Payroll still
includes the benefit as earnings for its existing tax rules, then adds an
**Already paid** deduction, preventing a second payment. A large advance can
produce a negative net balance to recover. Benefits already included in a draft
or approved payroll must be settled through that payslip instead. Benefits with
payment history cannot be edited/deleted. An approved payroll accounting for a
direct benefit payment must be reopened before that payment can be voided.

Void an incorrect payment with a reason. Its original amount/reference remain in
the ledger and the outstanding balance becomes payable again. Voids never delete
history. Payroll with payslip payment history cannot be unapproved/recalculated,
even after voiding; preserve those snapshots and make separate corrections.

## Scope, deployment and migration

These screens and endpoints require `payroll.manage`. Platform administrators can
open them from the tenant payroll panel. All records are tenant/company scoped,
with database row-level security and company-domain restrictions. Financial
fields remain separate from general personnel endpoints.

Migrations: `048_employee_bank`, `049_workforce_payments`,
`050_overtime_currency`. They have been applied to the local development database.
For a manually run backend, run `python -m alembic upgrade head` from `backend`
using its environment before starting it. The backend Docker startup already
runs migrations automatically.

The old HRMS database has now been transferred to the live SaaS, with migrations
through `052_closed_overtime`. Historical employee/consultant financial snapshots,
leave, salaries, bank details and source login hashes were reconciled and imported.
Original fields and source metadata are owner-readable under Payroll > Imported
history. See `SERVER_MIGRATION_STATUS.md` for verified counts, backups and missing
source-file references. No historical payroll was recalculated.
