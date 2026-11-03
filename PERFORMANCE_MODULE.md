> Historical documentation for the previous module. The replacement workflow is documented in [APPRAISALS.md](APPRAISALS.md).

# Employee performance management

The module is available at **Workspace → Performance**. It uses the existing
tenant authentication, employee records, supervisor relationships, permission
catalog, HRMS document storage, and audit log. It does not change payroll.

## Setup and daily use

1. Open **Configuration**, create a rating scale, then save company settings with
   that scale. The scale editor offers an editable five-level example; arbitrary
   numeric scales work too. Score bands must cover every two-decimal score without
   overlap or gaps, and each representative value must fall within its own band.
2. Add competencies. Leave their assignment selectors empty to apply them to the
   company, or select departments, job titles and/or employees. At least one
   matching competency is needed when the competency contribution is positive.
3. Create a cycle under **Cycles**. Choose annual, semiannual, quarterly,
   probation, or custom frequency, its performance period, and optional stage
   windows. Windows can continue after the performance period but must follow
   each other chronologically. Date windows are enforced on backend actions.
4. Assign the whole company, a branch, department, job title, or selected people.
   The first supervisor by existing supervisor order becomes the appraiser.
   HR can override that selection, assign a secondary reviewer, or use
   **Reassign appraiser** before manager submission. Reassignments require a
   reason and retain the previous draft in history.
5. Advance to **Goal setting**. Employees or authorized appraisers create goals,
   submit them, and the assigned appraiser approves or requests changes.
   Active KPI weights must total 100 before the cycle becomes active. Material
   revisions retain their old values in history and require fresh approval.
6. Advance to **Active** for progress, evidence and monthly/quarterly/midyear/ad
   hoc check-ins. Progress updates preserve the previous actual and percentage.
   Evidence uses existing employee documents, with appraisal authorization on
   downloads. Files are append-only, limited to ten per goal, and also count
   toward the existing forty-document employee limit.
7. Open **Self assessment**, then **Manager assessment**. Each has save-draft
   and submit actions. Submissions are locked until an authorized reopening.
   Employee and manager ratings/comments are separate. Managers see employee
   ratings alongside their own fields. Employees see manager and calibration
   information only when the cycle policy permits it.
8. Record the review meeting, perform calibration if enabled, obtain employee
   acknowledgement, and finalize. An employee can record **Disagrees** without
   preventing finalization: acknowledgement records receipt, not agreement.
   Required stages must finish before advancing; optional stages can be omitted.
9. Create development actions with owners and deadlines. They continue after
   finalization. PIPs have a separate restricted workspace, explicit activation,
   measurable objectives, reviews, extensions, and recorded outcomes. Scores
   only recommend consideration of a PIP; no PIP is created automatically.
10. Complete the cycle once all appraisals are finalized. An authorized reopening
    requires a reason, preserves the prior finalized record in domain history,
    reopens the cycle at the selected stage, and clears affected downstream work.

**Edit dates / deadlines** allows HR to extend a stage with an audited reason.
Once active, cycle names and performance periods cannot change; completed cycles
must be explicitly reopened first. Finalized appraisal data and evidence reject
ordinary edits, including attempts through existing document-delete endpoints.

## Scoring policy

All authoritative scores use Python `Decimal` on the backend. KPI ratings are
weighted by the active goal weights; competencies use relative competency
weights. Company contributions then combine those two scores. Final scores
round half-up to two decimal places and map to the cycle's rating bands. Component
scores display two decimals, while their contributions use full decimal precision.

For example, five KPI weights of **40, 20, 15, 10 and 15**, each rated **4.20**,
and competency ratings of **3.80**, with **70% / 30%** contributions, produce
**4.08 — Exceeds Expectations** on the offered example scale. Calibration stores
a separate score/reason and does not overwrite the original manager ratings or
pre-calibration score.

Automatic scoring is optional. A manually supplied manager rating takes
precedence. Otherwise higher-is-better uses actual/target, lower-is-better uses
target/actual, target-is-best uses distance from target, and milestones use
progress. Achievement maps linearly from the scale minimum to maximum at the
goal's configurable achievement cap (default 120%). Qualitative goals require
manual ratings; boolean actuals must be 0 or 1. Zero-target and zero-actual rules
are explicit in `performance_scoring.py`; negative numeric targets require
target-is-best or manual scoring. When manager submission is optional, saved
manager ratings take precedence over self-ratings; automatic measurable goals
can finalize without manual submission when all required policy steps permit it.

## Data and authorization

Migration **039_performance**, after **038_hr_permissions**, adds fifteen
performance tables with foreign keys, indexes, participant/appraisal uniqueness,
state/version/date/weight/progress constraints, and forced tenant RLS policies.
Existing employee/company data is not rewritten. The migration has a tested
downgrade that removes performance tables and retains ordinary HRMS documents.

Cycle settings and rating scales are snapshots. Participant names, company,
branch, department, job title and appraiser context are captured at assignment,
so later personnel edits do not rewrite historical appraisals. Ratings, review
details, competency definitions and other bounded structured snapshots are
validated schemas stored as JSON; goals, progress, evidence, development actions,
PIPs, reviews, notifications and events have their own records.

All supplied references are checked against the company/tenant. Own/team/all
view permissions scope reads. Assessment/approval actions require the assigned
appraiser or an authorized user with company-wide performance access and the
relevant action permission; employees cannot assess or approve themselves.
Current direct-report visibility does not grant assessment rights to an
appraisal assigned to another appraiser. PIP details require `manage_pip` and
are removed from appraisal history for users without that permission.

Critical writes lock the cycle/appraisal and validate optimistic record versions.
Competing requests cannot silently overwrite one another. Domain events are
append-only and also write the existing AuditLog. CSV exports escape spreadsheet
formula prefixes. The PWA uses network-only handling for `/performance`.

## Reports and notifications

The dashboard includes participant and stage completion, final scores, rating
distribution, department/branch/manager summaries, goal achievement, competency
averages, development progress, overdue actions and PIP status. CSV exports
include completion and final ratings. Employee profiles link performance history.

Notifications persist in-app and appear in the workspace bell and Performance's
Notifications tab. Assignment, goal approval, submissions, cycle stages,
acknowledgement readiness, finalization, and development ownership generate
deduplicated notices. Authorized calibration/finalization users receive work
notifications. Deadline reminders cover assessments, development actions and PIP
reviews, using stable event keys to avoid repeated notices for one deadline.

Docker Compose starts an hourly `performance-reminders` worker after the backend
is healthy. The worker handles active tenants and uses an active authorized
user in each tenant. Its interval can be configured with
`PERFORMANCE_REMINDER_INTERVAL_SECONDS` (minimum 300 seconds). HR can also use
**Send due-date reminders**, or run this command from the backend directory:

```powershell
.venv\Scripts\python.exe -m app.services.performance_reminders
```

There is no existing email delivery infrastructure, so no email is sent.

## Run and verify

```powershell
docker compose up -d --build backend performance-reminders
cd frontend
npm run dev
```

Outside Docker, run `alembic upgrade head` from the backend with the intended
database configured. Do not downgrade a database containing appraisals you need
to retain. Test fixtures enforce the separate `hrms_test` database.

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
```

`tests/test_performance.py` covers the John/Mary 4.08 walkthrough, ownership,
tenant/company reference attacks, weights, progress/evidence, independent
assessments, privacy, calibration, disagreement, finalization/reopening, PIPs,
history, automatic/optional scoring, deadlines, configuration snapshots and
simultaneous progress updates. The existing access suite checks route permission
dependencies too. The repository has no frontend test runner; TypeScript and
production builds are the automated frontend checks.

Reusable goal templates are an optional future extension; they are not needed
for the implemented appraisal workflow. Browser-based visual verification still
requires an available browser session.

Verification on implementation: all **80 backend tests passed**; the frontend
TypeScript check and Vite/PWA production build passed; migration 039 successfully
downgraded to 038 and upgraded again on the isolated test database. The full
suite also covers the existing HR, payroll, document and authorization features.
Final reopening/privacy/numeric validation changes were checked again with the
eleven performance tests and the frontend production build.
