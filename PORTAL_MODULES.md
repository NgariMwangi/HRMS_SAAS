# Platform and employee module coverage

## Platform Admin

Open `/admin/tenants`, choose a tenant, then choose a module using its sidebar or tabs. Module selection is retained in the URL (`?tab=performance`, `?tab=recruitment`, `?tab=reports`, `?tab=access`). Select a company inside the module.

Existing company, branch, department, title, employee, document, attendance, leave, lifecycle and payroll administration remains available.

Performance oversight includes review periods and goal-entry rules, self-review dates, employee goals, check-ins, assessments, results, acknowledgement, development, improvement plans and follow-ups, configuration, completion reports and CSV export. Recruitment oversight includes vacancies, candidates and CV downloads, applications, interviews and panel feedback, offers and hiring history. These two platform views are read-only; assessments and hiring decisions are performed by authorized staff in the tenant workspace, preserving the existing actor attribution and workflow checks. Platform accounts are never impersonated as tenant employees.

Roles & permissions uses the same role editor and permission catalogue as the tenant workspace, with server validation, owner-role locking and last-active-owner safeguards. User forms include custom roles and employee-record linking. Linking a login to an employee enables the employee's portal pages, subject to their role permissions. Duplicate links and cross-tenant employee links are rejected. Platform audit requests retain the platform actor identity.

The platform activity popover links to the real audit log instead of presenting fictional notifications. External connections are described as unconfigured; no placeholder claims that integration services are active.

## Employee Portal

Open `/employee/login` and sign in with an employee-linked account. Each page is permission-controlled and scoped to the employee identified by the login.

| Module | Employee access |
| --- | --- |
| People | Personal profile, contact updates, emergency contacts |
| Attendance | Clock in/out and recorded history |
| Leave | Requests, approval progress, balances, holidays |
| Payroll | Approved personal payslips, printing/PDF |
| Documents | Own files and protected downloads |
| Lifecycle | Own employment history on a separate page |
| Performance | Separate links for goals, check-ins, self-review, results and development |
| Improvement plans | Own published plans, objectives, support and follow-up meetings; drafts remain internal |
| Development | Progress updates on actions owned by the employee in their own review |
| Recruitment | Assigned interview tasks, candidate details/CVs and personal feedback, when granted `recruitment.interview` |
| Notifications | Personal performance assignments and reminders |
| Account | Password change and Google linking/unlinking |

Company-wide General Reports remain restricted to authorized HR/report users. Employees use their personal attendance, leave, payslip and performance pages instead. Administrative organisation and company setup pages remain in the HR/platform portals.

Goals and self-review remain separate tasks. Employees enter goals only when the review's goal-entry setting allows it; the existing review dates and workflow rules continue to govern self-review submission. Review links always select one section, including links from notifications. Browser back/forward follows URL state.

Development updates use version checks and consistent workflow lock ordering. Employees cannot cancel, reopen, change ownership of or update someone else's action. Employee comments are saved separately from manager guidance. Published personal improvement plans expose an explicit field allowlist, not HR owner identities, approval history or internal draft records.

Google sign-in still requires an externally supplied Google OAuth client ID. Public recruitment applications, external integrations and automated billing are separate features that are not introduced by this portal update.

## Verification

`backend/tests/test_portal_modules.py` verifies platform module visibility, tenant/company isolation, protected CV downloads, read-only oversight, published employee plans, assigned development updates and conflicts, account linking, custom roles and last-owner protection. Existing employee portal, access, platform, recruitment and performance review suites are also run against the isolated `hrms_test` database. Frontend validation uses `npm run build`.
