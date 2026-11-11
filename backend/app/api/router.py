from fastapi import APIRouter
from app.api.routes import domains
from app.api.routes import employee_portal, google_auth
from app.api.routes import recruitment
from app.api.routes import reports, platform_modules

from app.api.routes import (
    access,
    audit_logs,
    auth,
    branches,
    companies,
    countries,
    departments,
    document_categories,
    documents,
    employees,
    job_titles,
    leave_balances,
    leave_requests,
    leave_types,
    public_holidays,
    lifecycle,
    platform,
    platform_workspace,
    platform_ops,
    platform_payroll,
    attendance,
    benefits,
    deductions,
    payroll,
    performance,
)

api_router = APIRouter()
from app.api.routes import legacy_import
api_router.include_router(legacy_import.router)
from app.api.routes import workforce_payments
api_router.include_router(workforce_payments.router)
api_router.include_router(workforce_payments.platform_router)
from app.api.routes import employee_pay_settings
api_router.include_router(employee_pay_settings.router)
api_router.include_router(employee_pay_settings.platform_router)
from app.api.routes import payslips
api_router.include_router(payslips.router)
api_router.include_router(payslips.employee_router)
api_router.include_router(payslips.platform_router)
from app.api.routes import appraisals
api_router.include_router(appraisals.router)
api_router.include_router(appraisals.platform_router)
api_router.include_router(domains.router)
api_router.include_router(domains.platform_router)
api_router.include_router(platform_modules.router)
api_router.include_router(reports.router)
api_router.include_router(reports.platform_router)
api_router.include_router(recruitment.router)
api_router.include_router(employee_portal.router)
api_router.include_router(google_auth.router)
api_router.include_router(performance.router)
api_router.include_router(access.router)
api_router.include_router(audit_logs.router)
api_router.include_router(auth.router)
api_router.include_router(companies.router)
api_router.include_router(branches.router)
api_router.include_router(departments.router)
api_router.include_router(document_categories.router)
api_router.include_router(documents.router)
api_router.include_router(job_titles.router)
api_router.include_router(leave_types.router)
api_router.include_router(public_holidays.router)
api_router.include_router(leave_balances.router)
api_router.include_router(leave_requests.router)
api_router.include_router(attendance.router)
api_router.include_router(payroll.router)
api_router.include_router(deductions.router)
api_router.include_router(benefits.router)
api_router.include_router(employees.router)
api_router.include_router(lifecycle.router)
api_router.include_router(countries.router)
api_router.include_router(platform.router)
api_router.include_router(platform_payroll.router)
api_router.include_router(platform_ops.router)
api_router.include_router(platform_workspace.router)
