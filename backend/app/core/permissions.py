"""Permission catalog and the default grants for the built-in roles.

Permissions are stored per tenant role in access_role_permissions. This module is the
source of truth for which permission keys exist and what new tenants start with.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Permission:
    key: str
    label: str
    group: str


CATALOG: tuple[Permission, ...] = (
    Permission("domains.manage", "Manage company domains", "Organisation"),
    Permission("reports.view", "View and export general HR reports", "Reports"),
    Permission("recruitment.manage", "Manage vacancies, candidates, offers and hiring", "Recruitment"),
    Permission("recruitment.view_assigned", "View assigned vacancies and applications", "Recruitment"),
    Permission("recruitment.interview", "Submit feedback for assigned interviews", "Recruitment"),
    Permission("people.update_own_contact", "Update own contact and emergency details", "People"),
    Permission("payroll.view_own", "View own approved payslips", "Payroll"),
    Permission("access.manage_roles", "Manage roles and user access", "Access"),
    Permission("organization.manage", "Manage companies, branches, departments and job titles", "Organisation"),
    Permission("people.view_all", "View all employee records", "People"),
    Permission("people.view_own", "View own employee record", "People"),
    Permission("people.view_team", "View direct reports' employee records", "People"),
    Permission("people.manage", "Create and update employee records and logins", "People"),
    Permission("documents.view_all", "View company and employee documents", "Documents"),
    Permission("documents.view_own", "View own employee documents", "Documents"),
    Permission("documents.manage", "Manage document categories and employee files", "Documents"),
    Permission("lifecycle.view_all", "View all employee lifecycle records", "People"),
    Permission("lifecycle.view_own", "View own lifecycle records", "People"),
    Permission("lifecycle.manage", "Apply employee lifecycle actions", "People"),
    Permission("leave.view_all", "View all leave requests and balances", "Leave"),
    Permission("leave.view_own", "View and request own leave", "Leave"),
    Permission("leave.view_team", "View and approve direct reports' leave", "Leave"),
    Permission("leave.manage", "Manage leave types, holidays, balances and HR approvals", "Leave"),
    Permission("attendance.self", "Clock in and out and view own attendance", "Attendance"),
    Permission("attendance.manage", "Manage attendance and unlock clock devices", "Attendance"),
    Permission("payroll.manage", "Manage compensation, benefits, deductions and payroll", "Payroll"),
    Permission("audit.view", "View workspace audit logs", "Audit"),
    Permission("performance.view_own", "View own performance", "Performance"),
    Permission("performance.manage_own_goals", "Create and update own goals", "Performance"),
    Permission("performance.self_assess", "Complete own self-assessment", "Performance"),
    Permission("performance.view_team", "View direct reports' performance", "Performance"),
    Permission("performance.assess_team", "Prepare assigned forms and assess employees", "Performance"),
    Permission("performance.manage_cycles", "Manage appraisal reviews, participants and templates", "Performance"),
    Permission("performance.manage_competencies", "Manage competencies", "Performance"),
    Permission("performance.manage_rating_scales", "Manage rating scales", "Performance"),
    Permission("performance.manage_settings", "Manage performance settings", "Performance"),
    Permission("performance.calibrate", "Calibrate ratings", "Performance"),
    Permission("performance.finalize", "Publish appraisal results and close appraisals", "Performance"),
    Permission("performance.reopen_appraisal", "Reopen finalized appraisals", "Performance"),
    Permission("performance.manage_development_plans", "Manage development plans", "Performance"),
    Permission("performance.manage_pip", "Manage performance improvement plans", "Performance"),
    Permission("performance.view_reports", "View performance reports and dashboard", "Performance"),
    Permission("performance.view_all", "View every appraisal in the company", "Performance"),
)

ALL_PERMISSIONS: frozenset[str] = frozenset(item.key for item in CATALOG)

_EMPLOYEE = {
    "people.update_own_contact",
    "payroll.view_own",
    "people.view_own",
    "documents.view_own",
    "lifecycle.view_own",
    "leave.view_own",
    "attendance.self",
    "performance.view_own",
    "performance.manage_own_goals",
    "performance.self_assess",
}
_MANAGER = _EMPLOYEE | {
    "recruitment.view_assigned",
    "recruitment.interview",
    "people.view_team",
    "leave.view_team",
    "performance.view_team",
    "performance.assess_team",
    "performance.manage_development_plans",
}
_HR = ALL_PERMISSIONS - {"access.manage_roles", "domains.manage"}


@dataclass(frozen=True)
class SystemRole:
    key: str
    name: str
    description: str
    permissions: frozenset[str]


SYSTEM_ROLES: tuple[SystemRole, ...] = (
    SystemRole("OWNER", "Owner", "Workspace owner. Always has every permission.", ALL_PERMISSIONS),
    SystemRole("ADMIN", "Admin", "Full administrative access.", ALL_PERMISSIONS),
    SystemRole("HR", "HR", "Runs HR processes, including performance cycles and calibration.", frozenset(_HR)),
    SystemRole("MANAGER", "Manager", "Leads a team: approves goals and assesses direct reports.", frozenset(_MANAGER)),
    SystemRole("EMPLOYEE", "Employee", "Self-service: own goals, check-ins and self-assessment.", frozenset(_EMPLOYEE)),
)

SYSTEM_ROLE_KEYS: frozenset[str] = frozenset(role.key for role in SYSTEM_ROLES)
OWNER_ROLE = "OWNER"
