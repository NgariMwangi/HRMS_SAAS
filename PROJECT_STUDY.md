# HRMS SaaS project study

Reviewed on 5 October 2026. This is a source-code study, not certification of payroll legislation or a complete security audit.

## Architecture

- Frontend: React 18, TypeScript, React Router, Vite, custom shared UI/CSS, theme support and an installable PWA.
- Backend: FastAPI, Pydantic, async SQLAlchemy, asyncpg and Alembic.
- Infrastructure: PostgreSQL 16 and Redis 7 through Docker Compose. Redis is configured but has no application usage in the reviewed code.
- Organisation hierarchy: tenant → companies → branches → employees. Branch country supplies defaults for currency, timezone and holidays; payroll uses the branch country.
- Reference countries: Kenya, Uganda, Tanzania and Rwanda. Country availability and published payroll-pack availability are separate concerns.
- There are 38 sequential migration files, ending with default grants for the new HR permissions.

## Entry points and request flow

`frontend/src/main.tsx` boots the app; `frontend/src/App.tsx` defines tenant routes under `/app` and platform routes under `/admin`.

`WorkspaceContext.tsx` loads the current user, companies and branches, and maintains the selected organisation. `api.ts` handles JSON, multipart uploads, file previews, token storage and a single retry after refreshing an expired access token. Tenant and platform token pairs are stored separately in localStorage.

`backend/app/main.py` creates the FastAPI application, attaches CORS and audit middleware, and mounts `api/router.py`. Route modules validate requests and invoke helpers/services. Request-scoped database dependencies commit on success and roll back on errors.

Tenant JWTs carry a tenant ID. `api/deps.py` checks the active user and sets transaction-local `app.current_tenant_id`. Platform sessions set `app.is_platform_admin` and verify the active platform administrator. PostgreSQL row-level security policies and explicit ownership checks provide tenant isolation. Platform routes additionally validate which tenant owns the requested organisation or employee.

## Implemented business areas

| Area | Behaviour in the code |
| --- | --- |
| Registration and authentication | Creates trial tenant, owner, first company and branch; bcrypt password hashes; separate access/refresh JWTs for tenants and platform admins. |
| Organisation | Company and branch management, country defaults, departments and job titles. |
| Employees | Personal/contact information, employment dates/types, statutory identifiers, photos, next of kin, supervisors and employee login linkage. |
| Lifecycle | Hire history; suspension with pay treatment; reinstatement; role changes; termination; contract/intern extensions; rehire using the same or a new record; attachments. |
| Documents | Company categories, employee uploads, issued/expiry dates and previews; lifecycle documents are combined with uploaded documents. File bytes are stored in PostgreSQL. |
| Leave | Company leave types, working/calendar day counts, holidays, accrual, adjustments, pending reservations, balance checks, overlap checks, supervisor/HR decisions and cancellation. |
| Attendance | Employee clock-in/out, browser device binding, one-device-per-person rules for the day, branch-local work dates, HR roster/marking and approved-leave checks. |
| Payroll | Effective-dated compensation, gross-only or basic-plus-allowances structures, voluntary pension, benefits, other deductions, country packs, draft/recalculation and approval, persisted payslip lines/totals. |
| Platform administration | Tenant status/trial management, countries, payroll packs, tenant organisation/employee management, leave, attendance, payroll and audit logs. |
| Audit | Request outcome logging with common credential fields redacted. |

Payroll calculations use Decimal and currency rounding. Packs define percent, fixed and progressive-band components, constants and effective dates. Payroll runs select currently active employees and compensation/pack data effective at period end; employees without positive compensation are skipped. Approved periods cannot be recalculated through the creation service.

Shared frontend boards and components accept `apiBase` and scope props so tenant and platform screens can reuse employee, leave, attendance and payroll interfaces.

## Incomplete areas

- Performance, recruitment and reports currently render module placeholders.
- Integration cards have Configure buttons without a working configuration flow.
- Workspace roles UI now supports permission editing, custom role creation/deletion and user assignment through `/access`. The permission catalog covers existing HR operations as well as planned performance operations.
- `/access` is included in Vite's proxy paths and PWA API exclusions.
- Dashboard pending approvals is hardcoded to zero; notifications are an empty list, and some settings controls do not persist.
- Trial expiry is stored and extendable, but the reviewed authentication/request paths do not enforce the expiry date.
- Compose runs database/cache/backend services; it does not provide a frontend production host.

## Findings to address before expanding features

1. **Role enforcement gaps addressed.** Tenant HR mutations now require module permissions. Employee, document, lifecycle and leave visibility uses server-side scopes; employee self-service and manager reporting relationships are enforced. Frontend navigation and action controls use the permissions returned by `/access/me`.
2. **Tenant suspension does not immediately block existing access tokens.** Login and refresh reject inactive tenants; `get_tenant_db` checks user status but does not check tenant status. Access can continue until the access token expires unless another route independently checks tenant status.
3. **Custom roles now govern tenant HR actions.** Existing fixed tenant-role checks have been replaced by permission dependencies. Owners retain full access. Assignment and role mutations serialize within a tenant, protecting the last active owner and preventing assignment/deletion races. Module-only roles use limited employee summaries rather than requiring full-profile access.
4. **Refresh tokens are stateless.** Refresh issues a new pair, but there is no token persistence/revocation check in the reviewed implementation. Issuing a replacement does not itself invalidate the old refresh token.
5. **Payroll is not an attendance/lifecycle pay engine yet.** Run creation uses current ACTIVE status and full configured compensation. It does not apply historical employment eligibility, attendance deductions, suspension pay treatment or salary proration within the requested period.
6. **Number/version generation can race.** Employee numbers and payroll-pack versions are generated by reading the current maximum and incrementing it. Concurrent requests can conflict; database uniqueness can detect a collision but does not make allocation atomic.
7. **Database isolation needs a non-superuser verification.** Compose creates the application connection user via POSTGRES_USER, which normally creates a PostgreSQL superuser. Superusers bypass RLS, including forced RLS. Explicit tenant checks remain important; successful API isolation tests alone do not establish database-policy enforcement under the deployed role.
8. **Configuration/documentation drift.** `.env.example` points Redis at host port 6379 while Compose publishes 6380. App metadata still calls the system a Day 1 tenancy layer. Several older root-level frontend files coexist with active `pages/` versions; follow imports from App.tsx when making changes.

## Verification

- Existing backend suite collects 61 tests covering authentication, isolation, lifecycle, employee data, leave, attendance, payroll calculations, platform operations and demo seeding.
- Backend tests use a separately named `hrms_test` database and explicitly reject other database names before destructive cleanup.
- Frontend production build passed, including TypeScript checking and PWA service-worker generation. Vite required an approved run outside the sandbox because its build subprocess was initially denied.
- Backend suite passed: **61 tests in 311.20 seconds**, using `backend/.venv/Scripts/python.exe -m pytest -q`. This verifies the existing assertions, not the uncovered authorization gaps listed above. No dedicated access-role tests exist in the collected suite.

## Working conventions for future changes

- Derive tenant identity from authenticated claims, then validate all company/branch/employee relationships server-side.
- Update models, Alembic migrations, schemas, route/service behaviour, TypeScript types and both tenant/platform surfaces when a shared entity changes.
- Enforce authorization in the backend; UI filtering is only presentation.
- Preserve approved payroll history and effective-dated compensation.
- Verify time calculations against branch timezone and serialize datetimes consistently as UTC.
- Add new API prefixes to Vite proxy and PWA exclusions.
- Use the existing test database safety guard for integration tests.

## Role management follow-up

In Workspace → Roles, authorized owners/admins can create custom roles, edit built-in roles other than Owner, select grouped permissions, assign users and delete unused custom roles. Built-in roles cannot be deleted. Only an owner can assign or demote another owner; the last active owner cannot be demoted.

Defaults approved by the user: Owner/Admin have all permissions; HR manages HR operations without role administration; Managers have own-record access plus direct-report employee/leave visibility and supervisor leave decisions; Employees have their own records, documents, lifecycle, leave and attendance. Self-service leave checks the signed-in employee identity. Attendance has a separate self-service clock-in/out screen.

Migration `038_hr_permissions` backfills new grants for existing built-in roles once, preserving their earlier performance/access choices. Newly created tenants receive defaults lazily through `ensure_system_roles`; subsequent edits are not overwritten on login.

Backend authorization reads the current role and grants on each request; role changes do not require new tokens. Frontend access refreshes after changes, on navigation and window focus. The API remains authoritative if an already-open page has stale controls.

Validation for this follow-up: the full suite passed with 66 tests after the main changes; after adding module-specific summaries and additional coverage, all 10 focused access/leave/platform tests passed. These include eight new access tests. TypeScript and production/PWA builds passed. Visual browser verification could not run because no browser connection was available.

The local Docker backend was rebuilt and restarted. Database migration `038_hr_permissions` is applied; `/health` returns `ok`, and the running OpenAPI schema exposes the updated role and limited-summary routes.

The frontend development server was not running on port 5173. Its launch request was declined, so it remains stopped. Run `npm run dev` from `frontend` when ready to use Workspace → Roles.
