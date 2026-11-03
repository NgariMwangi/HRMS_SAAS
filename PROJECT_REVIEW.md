# Project review — 3 November 2026

## Scope and conclusion

Reviewed application entry points, deployment configuration, authentication and tenant dependencies, permission scopes, core HR routes, payroll services, newer performance/recruitment/reporting modules, employee self-service, company-domain isolation, migrations and test infrastructure. This is a source review with local verification, not a line-by-line audit, browser acceptance test or certification of statutory payroll rules.

The application has substantial implemented functionality. Its main risks are operational isolation, account/session lifecycle and payroll correctness under historical periods and concurrent requests. Address these before relying on it for unattended production payroll.

No application behavior was changed during this review. The October `PROJECT_STUDY.md` is historical and contains outdated module and verification descriptions.

## Architecture and feature map

| Layer | Implementation |
| --- | --- |
| Frontend | React 18, TypeScript, React Router, Vite; shared UI, theme and PWA support |
| Backend | FastAPI, Pydantic, asynchronous SQLAlchemy, asyncpg, Alembic |
| Data | PostgreSQL 16; tenant → company → branch → employee |
| Background processing | Separate performance reminder worker; in-app notifications, no email delivery |
| Hosting | Development Compose; public deployment overlay adds nginx frontend and Caddy with on-demand TLS |
| Migrations | 43 source migrations, ending at company domains |
| Redis | Configured service and dependency; no application use found in reviewed source |

Active frontend entry points are `frontend/src/main.tsx` and `frontend/src/App.tsx`. Follow imports into `pages/`, `layouts/` and `context/`; similarly named older files at the root of `src/` can mislead maintenance.

`WorkspaceContext.tsx` loads identity, permissions and organisation selections. `api.ts` manages separate tenant/platform tokens and refresh retries. The backend router mounts the feature APIs; database dependencies commit successful requests and roll back exceptions. Tenant dependencies set transaction-local tenant context; platform dependencies check active administrators and enable platform context.

Implemented areas include organisation administration, employees, supervisors, next of kin, lifecycle, documents, leave and balances, holidays, attendance, effective-dated compensation, payroll packs and payslips, role administration and audit logs. Performance includes staged reviews, goals, assessments, calibration, finalisation, development actions, PIPs and reminders. Recruitment includes vacancies, candidates/CVs, applications, interviews, offers and conversion to employees. General reports provide scoped data and CSV exports. The employee portal derives employee identity from the authenticated account. Company domains include automatic addresses, custom-domain DNS verification and company-bound query/write restrictions.

Useful existing safeguards include explicit ownership checks alongside RLS policies, permissions read from current database state, employee visibility scopes, request rollback on failure, Decimal-based payroll arithmetic, persisted payslip totals/lines, locked and versioned performance mutations, scoped recruitment access, and NetworkOnly service-worker handling for API paths. Tests cover API permission and company-domain boundaries; DNS verification tests mock DNS rather than exercising public records.

## Findings, ordered by priority

### 1. High: application database role bypasses row-level security

Evidence: `docker-compose.yml:7` creates `hrms` as the initial PostgreSQL user; `docker-compose.yml:44` uses it for the application connection. A read-only query against the configured local database returned `current_user=hrms`, `rolsuper=true`, `rolbypassrls=true`.

The database policies in `backend/app/db/rls_policies.sql` therefore do not enforce isolation for this connection. Explicit ownership checks still protect many routes; this finding does not establish a demonstrated cross-tenant API leak. It means the intended database defense is absent, and isolation tests using this role do not verify policy enforcement.

Use separate migration/bootstrap and application credentials. The application role needs neither superuser nor BYPASSRLS. Test both tenant and platform flows with that role: public login/registration, seeding and domain resolution use special access patterns, so simply removing privileges is not a complete implementation.

### 2. High: historical payroll uses current employee eligibility and full compensation

Evidence: `backend/app/services/payroll.py:433`, especially the current `Employee.status == "ACTIVE"` filter at line 467 and the calculation at line 505.

A former employee who worked during a prior pay period is omitted when that period is calculated after termination. A currently active employee is paid the full selected compensation without mid-period join/exit proration. Current suspension status excludes the employee without applying the stored suspension pay treatment. Compensation is selected at period end; attendance and lifecycle history do not determine earnings.

Define historical eligibility and period earnings, including paid suspensions, partial periods, salary changes and weekly/biweekly behavior. Cover those cases with explicit expected amounts before changing this service. Existing Decimal-based tax calculations do not solve employment-period eligibility.

### 3. High: payroll recalculation and approval do not serialize on the run

Evidence: `create_run` reads the existing run and checks DRAFT status without a row lock; `approve_run` at `backend/app/services/payroll.py:592` updates status without coordinating with recalculation. Tenant routes load and invoke these shared functions from `backend/app/api/routes/payroll.py`.

An approval can race with recalculation after the latter has read a draft. Recalculation deletes and rebuilds payslips and writes DRAFT status, so approved history is not reliably protected under concurrency. Database uniqueness prevents some duplicate rows but does not serialize these state transitions. This is a source-derived race; it was not reproduced with a concurrent load test.

Lock a stable branch/run resource, reload status under the lock, and use the same locking rule for approval and recalculation. Protect first creation when no run row exists, and test approval against recalculation in concurrent transactions.

### 4. Medium: suspension does not invalidate existing central-host access

Evidence: `backend/app/api/deps.py:63–89` validates the active user and tenant ID but does not load and validate tenant status. Login and refresh check tenant status separately.

An already issued access token can continue using generic tenant routes on the central address until expiration, normally ten minutes. Company-domain resolution checks tenant status and employee-portal dependencies have additional checks, so this finding concerns paths through the shared dependency that lack those extra checks.

Enforce active tenant status in the common tenant dependency and test an existing token immediately after suspension.

### 5. Medium: refresh replacement and password changes do not revoke sessions

Evidence: `backend/app/api/routes/auth.py:171–224` validates the supplied refresh JWT and issues another pair without storing or consuming its identifier. `backend/app/core/security.py` generates a `jti` but has no session/revocation lookup. Employee password changes replace the hash in `backend/app/api/routes/employee_portal.py:182`.

The original refresh token remains reusable until expiry. Changing a password does not invalidate existing tokens; a holder can continue refreshing while the account remains active. Frontend sign-out clears local storage but does not revoke server-side sessions. The test named `test_refresh_rotates_tokens_and_rejects_wrong_use` checks that replacement values differ, not that the old refresh token is rejected.

Persist refresh sessions with rotation/reuse detection, or introduce a server-checked session version. Define revocation for password changes, administrator resets and logout, then test those behaviors.

### 6. Medium: trial expiration is stored but not enforced

Evidence: `trial_ends_at` is written during registration and extended by platform administration, but searches of backend source found no request/login check against that date. Domain resolution also checks status rather than expiry.

An ACTIVE trial tenant can continue beyond the advertised trial date. Define expiry behavior and enforce it centrally, allowing deliberate exceptions for renewal/account management.

### 7. Medium: generated identifiers can collide under concurrent creation

Evidence: `backend/app/api/org.py:46` reads employee numbers and increments the maximum suffix. `backend/app/services/payroll.py:83` reads the highest payroll-pack version and adds one.

Two requests can allocate the same value. Employee creation maps integrity conflicts to a client error, but allocation itself is not atomic; pack creation also lacks an allocation retry in the reviewed path. Use a sequence, locked counter or bounded transaction retry scoped to the company/country. Employee-number generation additionally loads every existing number on each allocation.

### 8. Medium for public use: base Compose contains fixed credentials and public ports

Evidence: `docker-compose.yml` hardcodes the JWT secret, initial platform-admin password and database credentials, and publishes PostgreSQL, Redis and backend ports without a loopback bind.

The public overlay improves this: JWT/admin/TLS secrets are required from the environment, internal ports bind to loopback, and Google cookies become secure. Those protections depend on using both Compose files. The database still uses the privileged role described above.

Keep the deployment commands explicit, make public configuration fail closed, and separate application database credentials. Merely placing JWT/admin values in `.env` does not override their hardcoded values in the base Compose file.

## Product and maintenance gaps

- `frontend/src/pages/app/Integrations.tsx` renders Configure buttons without handlers or configuration workflows.
- `frontend/src/pages/app/Dashboard.tsx:96` hardcodes pending approvals to zero.
- Performance notifications are now wired into the tenant shell; the older study's description of an empty notification list is outdated.
- Some list APIs return full collections. Payroll run listing eagerly loads all payslips and their lines; reporting applies pagination after generating up to 50,000 rows. These paths will become expensive as organisations grow.
- The frontend build reports a 522.54 kB main JavaScript chunk (139.62 kB gzip) and mixed static/dynamic imports for `RolesSettings.tsx`, preventing that import from creating its own chunk.
- No frontend automated-test script or browser test suite was found in the reviewed project configuration. Backend integration tests provide significant coverage, but frontend build success does not verify user interactions.
- No `.git` repository is present in this workspace, so tracked state and a change diff could not be inspected.

## Verification

- `npm.cmd run build`: passed TypeScript, Vite production compilation and PWA service-worker generation. The initial sandbox run failed on Node filesystem access; the approved retry completed successfully.
- `docker compose config --quiet`: passed for the base configuration; Docker warned that the sandbox could not read the user's Docker client configuration. No containers were changed.
- `python -m alembic heads`: reports the single head `043_company_domains`.
- Read-only database-role query: confirmed the configured local application's superuser and RLS-bypass privileges.
- `backend/.venv/Scripts/python.exe -m pytest -q`: **113 passed in 625.98 seconds (10 minutes 25 seconds)**. The fixture redirects integration work into `hrms_test` and refuses destructive cleanup against other database names. Passing assertions do not cover all risks identified above, particularly privileged-role RLS bypass and payroll state-transition races.
- No browser interaction, public-domain/TLS deployment, adversarial penetration test, statutory-rule verification or payroll race reproduction was performed.

## Suggested implementation order

1. Establish a non-privileged application database role and run isolation tests with it.
2. Make tenant suspension and session revocation authoritative in shared request checks.
3. Serialize payroll state transitions and add meaningful concurrency coverage.
4. Define historical payroll and period-pay rules, then implement and test them.
5. Enforce trial expiration and make generated identifiers atomic.
6. Complete visible product controls, add targeted browser coverage and improve large-list loading.
