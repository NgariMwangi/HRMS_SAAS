"""Self-service endpoints derive the employee identity exclusively from the login."""
from datetime import date
from decimal import Decimal
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.api.access_control import require_access
from app.api.deps import get_current_user, get_tenant_db
from app.api.next_of_kin import list_next_of_kin, replace_next_of_kin
from app.core.security import hash_password, verify_password
from app.models import AttendanceRecord, Branch, Company, Currency, Department, Employee, EmployeeDocument, JobTitle, LeaveRequest, PayrollPayslip, PayrollRun, Tenant, User
from app.models.performance import Appraisal, DevelopmentAction, PerformanceParticipant, PerformanceNotification, PerformancePIP, PerformancePIPReview
from app.models.appraisals import EmployeeAppraisal
from app.schemas.performance import DevelopmentUpdate
from app.services import performance as performance_service
from app.services.access import permissions_for
from app.schemas.employee import EmployeeRead, NextOfKinReplace, NextOfKinRead
from app.schemas.payroll import PayslipRead

router = APIRouter(prefix="/employee-portal", tags=["employee portal"])


async def portal_employee(session: AsyncSession = Depends(get_tenant_db), user: User = Depends(get_current_user)) -> Employee:
    tenant = await session.get(Tenant, user.tenant_id)
    employee = await session.scalar(select(Employee).join(Company, Employee.company_id == Company.id).where(
        Employee.id == user.employee_id, Company.tenant_id == user.tenant_id, Company.status == "ACTIVE"))
    if tenant is None or tenant.status != "ACTIVE" or employee is None or employee.status != "ACTIVE":
        raise HTTPException(403, "An active employee account is required. Contact HR for help.")
    return employee


@router.get("/me", dependencies=[Depends(require_access("people.view_own", "people.manage"))])
async def profile(employee: Employee = Depends(portal_employee), user: User = Depends(get_current_user), session: AsyncSession = Depends(get_tenant_db)):
    company = await session.get(Company, employee.company_id)
    branch = await session.get(Branch, employee.branch_id)
    department = await session.get(Department, employee.department_id) if employee.department_id else None
    job = await session.get(JobTitle, employee.job_title_id) if employee.job_title_id else None
    return {"employee": EmployeeRead.model_validate(employee), "company_name": company.name,
            "branch_name": branch.name if branch else "", "department_name": department.name if department else "",
            "job_title_name": job.name if job else "", "google_linked": bool(user.google_subject)}


class ContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    personal_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    other_phone: str | None = Field(default=None, max_length=50)


@router.patch("/profile", response_model=EmployeeRead, dependencies=[Depends(require_access("people.update_own_contact"))])
async def update_profile(payload: ContactUpdate, employee: Employee = Depends(portal_employee), session: AsyncSession = Depends(get_tenant_db)):
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(employee, key, value or None)
    await session.flush()
    await session.refresh(employee)
    return employee


@router.get("/summary", dependencies=[Depends(require_access("people.view_own", "people.manage"))])
async def summary(employee: Employee = Depends(portal_employee), user: User = Depends(get_current_user), session: AsyncSession = Depends(get_tenant_db)):
    held = await permissions_for(session, user)
    result = {}
    if "leave.view_own" in held:
        result["pending_leave"] = await session.scalar(select(func.count()).select_from(LeaveRequest).where(LeaveRequest.employee_id == employee.id, LeaveRequest.company_id == employee.company_id, LeaveRequest.status.like("PENDING%")))
    if "documents.view_own" in held:
        result["documents"] = await session.scalar(select(func.count()).select_from(EmployeeDocument).where(EmployeeDocument.employee_id == employee.id, EmployeeDocument.company_id == employee.company_id))
    if "performance.view_own" in held:
        result["active_appraisals"] = await session.scalar(select(func.count()).select_from(Appraisal).join(PerformanceParticipant, PerformanceParticipant.id == Appraisal.participant_id).where(Appraisal.tenant_id == user.tenant_id, Appraisal.company_id == employee.company_id, PerformanceParticipant.tenant_id == user.tenant_id, PerformanceParticipant.employee_id == employee.id, Appraisal.finalized_at.is_(None)))
        result["active_appraisals"] += await session.scalar(select(func.count()).select_from(EmployeeAppraisal).where(EmployeeAppraisal.tenant_id == user.tenant_id, EmployeeAppraisal.company_id == employee.company_id, EmployeeAppraisal.employee_id == employee.id, EmployeeAppraisal.status.notin_(["PREPARATION", "COMPLETED"])))
        result["unread_notifications"] = await session.scalar(select(func.count()).select_from(PerformanceNotification).where(PerformanceNotification.tenant_id == user.tenant_id, PerformanceNotification.company_id == employee.company_id, PerformanceNotification.user_id == user.id, PerformanceNotification.read_at.is_(None)))
    return result


@router.get("/emergency-contacts", response_model=list[NextOfKinRead], dependencies=[Depends(require_access("people.view_own", "people.manage"))])
async def contacts(employee: Employee = Depends(portal_employee), session: AsyncSession = Depends(get_tenant_db)):
    return await list_next_of_kin(session, employee.id)


@router.put("/emergency-contacts", response_model=list[NextOfKinRead], dependencies=[Depends(require_access("people.update_own_contact"))])
async def update_contacts(payload: NextOfKinReplace, employee: Employee = Depends(portal_employee), session: AsyncSession = Depends(get_tenant_db)):
    await session.refresh(employee, with_for_update=True)
    return await replace_next_of_kin(session, employee, payload.items)


@router.get("/attendance", dependencies=[Depends(require_access("attendance.self", "attendance.manage"))])
async def attendance(start: date | None = None, end: date | None = None, limit: int = Query(100, ge=1, le=366), employee: Employee = Depends(portal_employee), session: AsyncSession = Depends(get_tenant_db)):
    if start and end and start > end:
        raise HTTPException(400, "Start date must precede end date")
    query = select(AttendanceRecord).where(AttendanceRecord.employee_id == employee.id, AttendanceRecord.company_id == employee.company_id)
    if start:
        query = query.where(AttendanceRecord.work_on >= start)
    if end:
        query = query.where(AttendanceRecord.work_on <= end)
    rows = (await session.scalars(query.order_by(AttendanceRecord.work_on.desc()).limit(limit))).all()
    return [{"id": row.id, "work_on": row.work_on, "status": row.status, "source": row.source, "checked_in_at": row.checked_in_at, "checked_out_at": row.checked_out_at} for row in rows]


async def own_payslips(session, employee, identity=None):
    query = select(PayrollPayslip, PayrollRun, Currency).join(PayrollRun, PayrollRun.id == PayrollPayslip.run_id).join(Currency, Currency.id == PayrollRun.currency_id).options(selectinload(PayrollPayslip.lines)).where(
        PayrollPayslip.employee_id == employee.id, PayrollPayslip.company_id == employee.company_id,
        PayrollRun.company_id == employee.company_id, PayrollRun.status == "APPROVED")
    if identity:
        query = query.where(PayrollPayslip.id == identity)
    rows = (await session.execute(query.order_by(PayrollRun.period_end.desc()).limit(120))).all()
    return [{**PayslipRead.model_validate(slip).model_dump(mode="json"), "period_start": run.period_start, "period_end": run.period_end, "currency_code": currency.code} for slip, run, currency in rows]


@router.get("/payslips", dependencies=[Depends(require_access("payroll.view_own"))])
async def payslips(employee: Employee = Depends(portal_employee), session: AsyncSession = Depends(get_tenant_db)):
    return await own_payslips(session, employee)


@router.get("/improvement-plans", dependencies=[Depends(require_access("performance.view_own"))])
async def improvement_plans(employee: Employee = Depends(portal_employee), user: User = Depends(get_current_user), session: AsyncSession = Depends(get_tenant_db)):
    # Draft plans are internal HR preparations. Staff see only their own published plans.
    plans = (await session.scalars(select(PerformancePIP).where(PerformancePIP.tenant_id == user.tenant_id,
        PerformancePIP.company_id == employee.company_id, PerformancePIP.employee_id == employee.id,
        PerformancePIP.status != "DRAFT").order_by(PerformancePIP.start_date.desc(), PerformancePIP.id))).all()
    result = []
    for plan in plans:
        reviews = (await session.scalars(select(PerformancePIPReview).where(PerformancePIPReview.tenant_id == user.tenant_id,
            PerformancePIPReview.company_id == employee.company_id, PerformancePIPReview.pip_id == plan.id).order_by(PerformancePIPReview.meeting_date))).all()
        details = plan.details or {}
        result.append({"id": plan.id, "status": plan.status, "start_date": plan.start_date, "end_date": plan.end_date,
            "appraisal_id": plan.appraisal_id, "details": {key: details[key] for key in ("reason", "issues", "support", "objectives", "review_frequency_days", "outcome") if key in details},
            "reviews": [{"id": r.id, "meeting_date": r.meeting_date, "details": {key: r.details[key] for key in ("notes", "objective_progress", "next_review") if key in r.details}} for r in reviews]})
    return result


@router.patch("/development-actions/{identity}", dependencies=[Depends(require_access("performance.view_own"))])
async def development_progress(identity: uuid.UUID, payload: DevelopmentUpdate, employee: Employee = Depends(portal_employee), user: User = Depends(get_current_user), session: AsyncSession = Depends(get_tenant_db)):
    action = await session.scalar(select(DevelopmentAction).where(DevelopmentAction.id == identity,
        DevelopmentAction.tenant_id == user.tenant_id, DevelopmentAction.company_id == employee.company_id,
        DevelopmentAction.owner_id == employee.id))
    if action is None:
        raise HTTPException(404, "Development action not found")
    appraisal, participant, _, _ = await performance_service.appraisal_context(session, user, action.appraisal_id, True)
    if participant.employee_id != employee.id:
        raise HTTPException(404, "Development action not found")
    action = await session.scalar(select(DevelopmentAction).where(DevelopmentAction.id == identity,
        DevelopmentAction.tenant_id == user.tenant_id, DevelopmentAction.company_id == employee.company_id,
        DevelopmentAction.owner_id == employee.id).with_for_update().execution_options(populate_existing=True))
    if action is None:
        raise HTTPException(404, "Development action not found")
    if payload.status == "CANCELLED":
        raise HTTPException(403, "Contact your manager to cancel an agreed development action")
    if action.status in ("COMPLETED", "CANCELLED"):
        raise HTTPException(409, "Contact your manager to reopen this development action")
    old = performance_service.row(action)
    performance_service.version(action, payload.version)
    action.status = payload.status
    action.progress = Decimal(100) if payload.status == "COMPLETED" else payload.progress
    action.details = {**action.details, "employee_comments": payload.comments,
        "completed_at": performance_service.now().isoformat() if payload.status == "COMPLETED" else None}
    await performance_service.event(session, user, action, "employee_development_updated", {"old": old, "new": performance_service.row(action)}, appraisal.id)
    return performance_service.row(action)


@router.get("/payslips/{identity}", dependencies=[Depends(require_access("payroll.view_own"))])
async def payslip(identity: uuid.UUID, employee: Employee = Depends(portal_employee), session: AsyncSession = Depends(get_tenant_db)):
    rows = await own_payslips(session, employee, identity)
    if not rows:
        raise HTTPException(404, "Payslip not found")
    return rows[0]


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("current_password", "new_password")
    @classmethod
    def password_bytes(cls, value):
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


@router.post("/password", dependencies=[Depends(require_access("people.view_own", "people.manage"))])
async def password(payload: PasswordChange, employee: Employee = Depends(portal_employee), user: User = Depends(get_current_user), session: AsyncSession = Depends(get_tenant_db)):
    await session.refresh(user, with_for_update=True)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    await session.flush()
    return {"message": "Password updated"}
