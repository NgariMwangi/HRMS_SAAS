# Simple performance appraisals

This replaces the normal workspace performance experience. Existing performance records and their database tables are retained; old appraisal links open a read-only archive. Legacy APIs remain available for compatibility with historical integrations and existing archived data. New reviews use `/performance/simple` and migration `044_simple_appraisals`.

## HR setup

1. Open **Performance → Templates**. Create a reusable form for a department/job. Start with the supplied example, then write clear work objectives and working-behaviour standards.
2. Open **Manage appraisals → Create review**. Enter the performance period, employee deadline, manager/discussion deadline and acknowledgement deadline. Select a template and participants. Branch, department and name filters help with selection.
3. Choose whether HR or assigned managers prepare individual objectives. Save the draft. Supervisors are suggested as appraisers, but HR must resolve missing assignments.
4. Open each participant's form. Add/edit/remove individual objectives, specify expected results, evidence and optional due dates. Copy objectives from another participant when useful. These changes never alter the shared template or other employees' forms.
5. Confirm the appraiser and mark the form ready. Managers can prepare forms assigned to them when the review delegates preparation to managers; HR retains appraiser assignment and publication control.
6. Review the participant count, readiness, performance period and deadlines, then publish. Every participant needs an active employee login with self-review permission, and every appraiser needs an active linked login with manager-assessment permission. Publication creates notifications and opens each employee's self-review.

The performance period describes the work assessed; completion deadlines can follow that period. Objectives should reflect expectations already communicated to the employee, not surprise targets introduced retrospectively. A draft review uses one template, with individual tailoring. Different groups can have separate reviews. Template edits affect future reviews, not existing snapshots.

## Independent employee workflow

**Employee self-review → Manager assessment → Discussion → HR review → Acknowledgement → Completed**

- Employees write criterion responses, achievements, challenges and support needs. Drafts remain private until submission. Employees do not supply scores in this version.
- Only the assigned appraiser, holding manager-assessment permission, can enter manager ratings/comments. General HR visibility does not let someone impersonate the manager or silently change ratings.
- Managers can return a submitted self-review with a reason. The employee's existing input is retained for correction. Manager drafts and results remain hidden from the employee until HR publishes them.
- Once the manager submits ratings, they record the meeting, differing views and development actions with owners/deadlines. Saving a revision to submitted manager ratings returns that appraisal to manager assessment and clears the old result until fresh submission.
- HR checks the completed assessment and discussion, then publishes it or returns it to the manager with a reason.
- Employees acknowledge receipt, with agreement or disagreement. Disagreement requires a comment and does not block completion. HR may close without acknowledgement only after the acknowledgement deadline, recording a reason rather than inventing employee receipt.
- Completed appraisals reject normal assessment edits. Authorized HR can reopen with a reason; previous assessment/result snapshots are retained in stored history and domain audit logs, while the live appraisal returns to manager assessment and hides the old published result. Employee self-review is retained.
- Development action progress can continue after completion without reopening the appraisal.
- A review completes automatically when every employee appraisal is completed. HR never advances a company-wide assessment stage.

Deadlines flag overdue work and drive reminders; they do not prevent late submissions. Completed reviews keep their participant names, department, job title, appraiser context and form snapshot.

## Scoring

The fixed scale is 1 Significantly below expectations, 2 Partly meets expectations, 3 Meets expectations, 4 Exceeds expectations, 5 Significantly exceeds expectations. Every manager rating needs a supporting comment at submission.

Within objectives, choose equal weights or weights totaling 100%. Behaviours always have equal weight. If both sections exist, objectives contribute 70% and behaviours 30%; a single section contributes 100%. These rules are stated in the template and employee form. Scores use backend Decimal arithmetic and round half-up to two decimals. Overall rating bands use midpoint boundaries 1.50, 2.50, 3.50 and 4.50.

## Access, reporting and notifications

The replacement uses existing permission keys: `performance.manage_cycles` for templates/setup, `view_own` and `self_assess` for employees, `view_team`/`assess_team` for assigned appraisers, `view_all` for company-wide reading, `finalize` for HR publication/closure, `reopen_appraisal` for correction and `view_reports` for summaries/CSV export. An employee cannot rate or HR-finalize their own appraisal.

Report-only users receive status/context and published scores, not private assessment narratives. CSV export includes published results and escapes spreadsheet formula prefixes. Platform oversight is read-only. Requests explicitly validate tenant and company ownership, and all three new tables have forced tenant RLS plus company-domain policies.

Notifications reuse the existing in-app notification service and link to the new appraisal. The existing hourly worker also processes overdue replacement appraisals; reminder keys are deduplicated per appraisal, stage and deadline. No email is sent.

Mutations lock the review first and then the employee record, and require the current record version. Competing or stale saves return 409 instead of silently overwriting one another. There are no bulk stage transitions, calibration requirements, rating-scale setup or automatic target-to-rating formulas in the new workflow. Existing improvement-plan data remains separate from the core appraisal process.

## Installation and checks

For Docker, rebuild the two application services; backend startup applies the additive migration:

```powershell
docker compose up -d --build --no-deps backend performance-reminders
```

For a local Python server, run `alembic upgrade head` from `backend` before restarting it. Run `npm run dev` in `frontend` for the development UI, or rebuild the frontend container for public hosting. This change does not publish a hosted Site.

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run build
```

The replacement workflow tests exercise independent progression, submission privacy, fixed-scale weighted scores, appraiser and company boundaries, template snapshots, competing saves, correction loops, acknowledgement/disagreement, deadline closure, reopening and post-completion development progress. The older tests continue checking legacy behavior and the rest of the HRMS.

## Verification on 3 November 2026

- Final frontend TypeScript, production build and PWA generation passed. Existing warnings about the main bundle size and `RolesSettings` imports remain.
- Full backend regression run: 116 passed; one route-permission declaration guard failed before its fix. After adding explicit permission dependencies, all five replacement-workflow tests and that guard passed together (6 passed in 39.03 seconds). These checks include report-only privacy, company-domain isolation, publication account checks and reminder deduplication.
- Local Docker backend and reminder worker were rebuilt and restarted. The live database is at `044_simple_appraisals`; `/health` returns `ok`; OpenAPI exposes 16 replacement endpoint paths. The route-permission guard also passed inside the running backend container. The reminder worker completed its startup pass without an error.
- Browser interaction/visual verification was unavailable because this environment has no connected browser tool. No frontend development server was started, and no external hosting was changed.
