"""Tenant performance API. Business and permission rules live in services."""
import csv
import io
import uuid
from datetime import datetime
from pathlib import PurePath
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access_control import require_access
from app.api.deps import get_current_user, get_tenant_db
from app.api.org import company_for_tenant
from app.models import DocumentCategory, EmployeeDocument, User
from app.models.performance import (
    Appraisal, Competency, GoalEvidence, PerformanceCycle, PerformanceGoal,
    PerformanceNotification, PerformanceParticipant, PerformancePIP, PerformancePIPReview, RatingScale,
)
from app.schemas.performance import (
    AcknowledgeInput, AssessmentInput, CalibrationInput, CheckInInput, CompetencyInput,
    AppraiserUpdate, CycleInput, CycleUpdate, DevelopmentInput, DevelopmentUpdate, GoalInput, GoalUpdate, ParticipantInput,
    PIPInput, PIPReviewInput, PIPUpdate, ProgressInput, ReopenInput, ReviewInput, ScaleInput,
    SettingsInput, TransitionInput, VersionInput,
)
from app.services import performance as service
from app.services.access import permissions_for, require_permission

router = APIRouter(prefix="/performance", tags=["performance"])
Session = Depends(get_tenant_db)
Actor = Depends(get_current_user)
VIEW = ("performance.view_own", "performance.view_team", "performance.view_all", "performance.manage_cycles", "performance.manage_settings", "performance.manage_competencies", "performance.manage_rating_scales", "performance.view_reports", "performance.manage_pip", "performance.calibrate", "performance.finalize", "performance.reopen_appraisal")


@router.get("/settings", dependencies=[Depends(require_access(*VIEW))])
async def settings(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return await service.config_for(session, user, company_id)


@router.put("/settings", dependencies=[Depends(require_access("performance.manage_settings"))])
async def save_settings(payload: SettingsInput, company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return await service.save_settings(session, user, company_id, payload)


async def catalog_rows(session, user, company_id, model):
    await company_for_tenant(session, company_id, user.tenant_id)
    return [service.row(item) for item in (await session.scalars(select(model).where(model.company_id == company_id, model.tenant_id == user.tenant_id).order_by(model.created_at))).all()]


@router.get("/rating-scales", dependencies=[Depends(require_access(*VIEW))])
async def scales(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return await catalog_rows(session, user, company_id, RatingScale)


@router.post("/rating-scales", status_code=201, dependencies=[Depends(require_access("performance.manage_rating_scales"))])
async def create_scale(payload: ScaleInput, company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return await service.create_catalog(session, user, company_id, payload, RatingScale)


@router.put("/rating-scales/{identity}", dependencies=[Depends(require_access("performance.manage_rating_scales"))])
async def update_scale(identity: uuid.UUID, payload: ScaleInput, session: AsyncSession = Session, user: User = Actor):
    return await service.update_catalog(session, user, identity, payload, RatingScale)


@router.get("/competencies", dependencies=[Depends(require_access(*VIEW))])
async def competencies(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return await catalog_rows(session, user, company_id, Competency)


@router.post("/competencies", status_code=201, dependencies=[Depends(require_access("performance.manage_competencies"))])
async def create_competency(payload: CompetencyInput, company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return await service.create_catalog(session, user, company_id, payload, Competency)


@router.put("/competencies/{identity}", dependencies=[Depends(require_access("performance.manage_competencies"))])
async def update_competency(identity: uuid.UUID, payload: CompetencyInput, session: AsyncSession = Session, user: User = Actor):
    return await service.update_catalog(session, user, identity, payload, Competency)


@router.get("/reviews", dependencies=[Depends(require_access(*VIEW))])
@router.get("/cycles", dependencies=[Depends(require_access(*VIEW))])
async def cycles(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    await company_for_tenant(session, company_id, user.tenant_id)
    permissions = await permissions_for(session, user)
    query = select(PerformanceCycle).where(PerformanceCycle.company_id == company_id, PerformanceCycle.tenant_id == user.tenant_id)
    if not ({"performance.view_all", "performance.manage_cycles", "performance.view_reports"} & permissions):
        query = query.where(PerformanceCycle.id.in_(select(PerformanceParticipant.cycle_id).where(PerformanceParticipant.tenant_id == user.tenant_id, await service.participant_scope(session, user))))
    return [service.row(item) for item in (await session.scalars(query.order_by(PerformanceCycle.start_date.desc()))).all()]


@router.post("/reviews", status_code=201, dependencies=[Depends(require_access("performance.manage_cycles"))])
@router.post("/cycles", status_code=201, dependencies=[Depends(require_access("performance.manage_cycles"))])
async def create_cycle(payload: CycleInput, company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return await service.create_cycle(session, user, company_id, payload)


@router.put("/reviews/{identity}", dependencies=[Depends(require_access("performance.manage_cycles"))])
@router.put("/cycles/{identity}", dependencies=[Depends(require_access("performance.manage_cycles"))])
async def update_cycle(identity: uuid.UUID, payload: CycleUpdate, session: AsyncSession = Session, user: User = Actor):
    return await service.update_cycle(session, user, identity, payload)


@router.put("/appraisals/{identity}/appraiser", dependencies=[Depends(require_access("performance.manage_cycles"))])
async def reassign_appraiser(identity: uuid.UUID, payload: AppraiserUpdate, session: AsyncSession = Session, user: User = Actor):
    return await service.reassign_appraiser(session, user, identity, payload)


@router.post("/cycles/{identity}/transition", dependencies=[Depends(require_access("performance.manage_cycles"))])
async def transition_cycle(identity: uuid.UUID, payload: TransitionInput, session: AsyncSession = Session, user: User = Actor):
    return await service.transition_cycle(session, user, identity, payload)


@router.post("/reviews/{identity}/participants", status_code=201, dependencies=[Depends(require_access("performance.manage_cycles"))])
@router.post("/cycles/{identity}/participants", status_code=201, dependencies=[Depends(require_access("performance.manage_cycles"))])
async def participants(identity: uuid.UUID, payload: ParticipantInput, session: AsyncSession = Session, user: User = Actor):
    return await service.assign_participants(session, user, identity, payload)


@router.get("/people", dependencies=[Depends(require_access("performance.manage_cycles", "performance.manage_pip", "performance.manage_competencies"))])
async def people(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    from app.models import Employee
    await company_for_tenant(session, company_id, user.tenant_id)
    return [{"id": str(item.id), "name": f"{item.first_name} {item.last_name}", "branch_id": str(item.branch_id), "department_id": str(item.department_id) if item.department_id else None, "job_title_id": str(item.job_title_id) if item.job_title_id else None} for item in (await session.scalars(select(Employee).where(Employee.company_id == company_id, Employee.status == "ACTIVE").order_by(Employee.first_name))).all()]


@router.get("/hr-owners", dependencies=[Depends(require_access("performance.manage_pip"))])
async def hr_owners(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    await company_for_tenant(session, company_id, user.tenant_id)
    result = []
    for item in (await session.scalars(select(User).where(User.tenant_id == user.tenant_id, User.status == "ACTIVE"))).all():
        if "performance.manage_pip" in await permissions_for(session, item):
            if item.employee_id:
                from app.models import Employee
                employee = await session.get(Employee, item.employee_id)
                if not employee or employee.company_id != company_id:
                    continue
            result.append({"id": str(item.id), "email": item.email})
    return result


@router.get("/appraisals", dependencies=[Depends(require_access("performance.view_own", "performance.view_team", "performance.view_all"))])
async def appraisals(company_id: uuid.UUID, cycle_id: uuid.UUID | None = None, employee_id: uuid.UUID | None = None, team: bool = False, session: AsyncSession = Session, user: User = Actor):
    return await service.list_appraisals(session, user, company_id, cycle_id, employee_id, team)


@router.get("/appraisals/{identity}")
async def appraisal(identity: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return await service.detail(session, user, identity)


@router.post("/appraisals/{identity}/goals", status_code=201, dependencies=[Depends(require_access("performance.manage_own_goals", "performance.assess_team"))])
async def create_goal(identity: uuid.UUID, payload: GoalInput, session: AsyncSession = Session, user: User = Actor):
    return await service.create_goal(session, user, identity, payload)


@router.put("/goals/{identity}", dependencies=[Depends(require_access("performance.manage_own_goals", "performance.assess_team"))])
async def update_goal(identity: uuid.UUID, payload: GoalUpdate, session: AsyncSession = Session, user: User = Actor):
    return await service.update_goal(session, user, identity, payload)


@router.post("/goals/{identity}/actions/{action}", dependencies=[Depends(require_access("performance.manage_own_goals", "performance.assess_team"))])
async def goal_action(identity: uuid.UUID, action: str, payload: TransitionInput, session: AsyncSession = Session, user: User = Actor):
    return await service.goal_action(session, user, identity, action, payload)


@router.post("/goals/{identity}/progress", dependencies=[Depends(require_access("performance.manage_own_goals", "performance.assess_team"))])
async def progress(identity: uuid.UUID, payload: ProgressInput, session: AsyncSession = Session, user: User = Actor):
    return await service.add_progress(session, user, identity, payload)


@router.get("/goals/{identity}/progress")
async def progress_history(identity: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return await service.progress_history(session, user, identity)


@router.post("/goals/{identity}/evidence", status_code=201, dependencies=[Depends(require_access("performance.manage_own_goals", "performance.assess_team"))])
async def evidence(identity: uuid.UUID, file: UploadFile = File(), session: AsyncSession = Session, user: User = Actor):
    goal, (appraisal, participant, cycle, permissions) = await service.goal_context(session, user, identity)
    if appraisal.self_assessment.get("submitted_at") or appraisal.status not in ("GOAL_SETTING", "ACTIVE", "SELF_ASSESSMENT"):
        service.fail("Evidence is locked after self-assessment", 409)
    from app.api.lifecycle import ALLOWED_ATTACHMENT_TYPES, MAX_ATTACHMENT_BYTES
    content = await file.read(50 * 1024 * 1024 + 1)
    # Reuse the HRMS document validation and storage; protected performance
    # evidence routes apply appraisal authorization before accessing any bytes.
    filename = PurePath(file.filename or "evidence").name.replace("\r", "").replace("\n", "").replace("\x00", "")[:255] or "evidence"
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_ATTACHMENT_TYPES or not content or len(content) > MAX_ATTACHMENT_BYTES:
        service.fail("Upload a supported document, image or text file of 50 MB or smaller")
    await session.scalar(select(PerformanceCycle).where(PerformanceCycle.id == cycle.id).with_for_update())
    from app.api.org import ensure_document_categories
    from app.models import Company
    await session.scalar(select(Company).where(Company.id == goal.company_id).with_for_update())
    await ensure_document_categories(session, goal.company_id)
    category = await session.scalar(select(DocumentCategory).where(DocumentCategory.company_id == goal.company_id, DocumentCategory.system_key == "PERFORMANCE"))
    if not category:
        category = DocumentCategory(company_id=goal.company_id, system_key="PERFORMANCE", name="Performance related", locked=False, sort_order=40)
        session.add(category)
        await session.flush()
    document = EmployeeDocument(company_id=goal.company_id, employee_id=participant.employee_id, category_id=category.id,
        filename=filename, content_type=content_type, file_bytes=content, uploaded_by=user.id, note=f"Goal evidence: {goal.title}")
    if (await session.scalar(select(func.count()).select_from(GoalEvidence).where(GoalEvidence.goal_id == goal.id))) >= 10:
        service.fail("At most 10 evidence files per goal")
    from app.api.documents import MAX_EMPLOYEE_DOCUMENTS
    if (await session.scalar(select(func.count()).select_from(EmployeeDocument).where(EmployeeDocument.employee_id == participant.employee_id))) >= MAX_EMPLOYEE_DOCUMENTS:
        service.fail(f"At most {MAX_EMPLOYEE_DOCUMENTS} uploaded documents per employee")
    session.add(document)
    await session.flush()
    link = GoalEvidence(**service.base(user, goal.company_id), goal_id=goal.id, document_id=document.id)
    session.add(link)
    await session.flush()
    await service.event(session, user, goal, "evidence_uploaded", {"document_id": str(document.id), "filename": filename}, appraisal.id)
    return {"id": str(link.id), "filename": filename}


@router.get("/goals/{identity}/evidence")
async def evidence_list(identity: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    goal = await service.get(session, user, PerformanceGoal, identity)
    await service.appraisal_context(session, user, goal.appraisal_id)
    return [{"id": str(link.id), "filename": doc.filename} for link, doc in (await session.execute(select(GoalEvidence, EmployeeDocument).join(EmployeeDocument, GoalEvidence.document_id == EmployeeDocument.id).where(GoalEvidence.goal_id == goal.id, GoalEvidence.tenant_id == user.tenant_id))).all()]


@router.get("/evidence/{identity}/download")
async def download_evidence(identity: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    link = await service.get(session, user, GoalEvidence, identity)
    goal = await service.get(session, user, PerformanceGoal, link.goal_id)
    await service.appraisal_context(session, user, goal.appraisal_id)
    document = await session.get(EmployeeDocument, link.document_id)
    await session.refresh(document, ["file_bytes"])
    return Response(document.file_bytes, media_type=document.content_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.filename)}", "Cache-Control": "no-store"})


@router.post("/appraisals/{identity}/check-ins", status_code=201, dependencies=[Depends(require_access("performance.manage_own_goals", "performance.assess_team"))])
async def check_in(identity: uuid.UUID, payload: CheckInInput, session: AsyncSession = Session, user: User = Actor):
    return await service.add_check_in(session, user, identity, payload)


@router.put("/appraisals/{identity}/self-assessment", dependencies=[Depends(require_access("performance.self_assess"))])
async def self_assessment(identity: uuid.UUID, payload: AssessmentInput, session: AsyncSession = Session, user: User = Actor):
    return await service.assessment(session, user, identity, "self", payload)


@router.post("/appraisals/{identity}/submit-self-assessment", dependencies=[Depends(require_access("performance.self_assess"))])
async def submit_self(identity: uuid.UUID, payload: AssessmentInput, session: AsyncSession = Session, user: User = Actor):
    return await service.assessment(session, user, identity, "self", payload, True)


@router.put("/appraisals/{identity}/manager-assessment", dependencies=[Depends(require_access("performance.assess_team"))])
async def manager_assessment(identity: uuid.UUID, payload: AssessmentInput, session: AsyncSession = Session, user: User = Actor):
    return await service.assessment(session, user, identity, "manager", payload)


@router.post("/appraisals/{identity}/submit-manager-assessment", dependencies=[Depends(require_access("performance.assess_team"))])
async def submit_manager(identity: uuid.UUID, payload: AssessmentInput, session: AsyncSession = Session, user: User = Actor):
    return await service.assessment(session, user, identity, "manager", payload, True)


@router.post("/appraisals/{identity}/review", dependencies=[Depends(require_access("performance.assess_team"))])
async def review(identity: uuid.UUID, payload: ReviewInput, session: AsyncSession = Session, user: User = Actor):
    return await service.review(session, user, identity, payload)


@router.post("/appraisals/{identity}/acknowledge", dependencies=[Depends(require_access("performance.view_own"))])
async def acknowledge(identity: uuid.UUID, payload: AcknowledgeInput, session: AsyncSession = Session, user: User = Actor):
    return await service.acknowledge(session, user, identity, payload)


@router.post("/appraisals/{identity}/calibrate", dependencies=[Depends(require_access("performance.calibrate"))])
async def calibrate(identity: uuid.UUID, payload: CalibrationInput, session: AsyncSession = Session, user: User = Actor):
    return await service.calibrate(session, user, identity, payload)


@router.post("/appraisals/{identity}/finalize", dependencies=[Depends(require_access("performance.finalize"))])
async def finalize(identity: uuid.UUID, payload: VersionInput, session: AsyncSession = Session, user: User = Actor):
    return await service.finalize(session, user, identity, payload)


@router.post("/appraisals/{identity}/reopen", dependencies=[Depends(require_access("performance.reopen_appraisal"))])
async def reopen(identity: uuid.UUID, payload: ReopenInput, session: AsyncSession = Session, user: User = Actor):
    return await service.reopen(session, user, identity, payload)


@router.post("/appraisals/{identity}/development-actions", status_code=201, dependencies=[Depends(require_access("performance.manage_development_plans"))])
async def development_create(identity: uuid.UUID, payload: DevelopmentInput, session: AsyncSession = Session, user: User = Actor):
    return await service.development_create(session, user, identity, payload)


@router.patch("/development-actions/{identity}", dependencies=[Depends(require_access("performance.manage_development_plans"))])
async def development_update(identity: uuid.UUID, payload: DevelopmentUpdate, session: AsyncSession = Session, user: User = Actor):
    return await service.development_update(session, user, identity, payload)


@router.get("/pips", dependencies=[Depends(require_access("performance.manage_pip"))])
async def pips(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    values = await catalog_rows(session, user, company_id, PerformancePIP)
    for item in values:
        item["reviews"] = [service.row(review) for review in (await session.scalars(select(PerformancePIPReview).where(PerformancePIPReview.pip_id == uuid.UUID(item["id"])).order_by(PerformancePIPReview.meeting_date))).all()]
    return values


@router.post("/pips", status_code=201, dependencies=[Depends(require_access("performance.manage_pip"))])
async def pip_create(payload: PIPInput, company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return await service.pip_create(session, user, company_id, payload)


@router.patch("/pips/{identity}", dependencies=[Depends(require_access("performance.manage_pip"))])
async def pip_update(identity: uuid.UUID, payload: PIPUpdate, session: AsyncSession = Session, user: User = Actor):
    return await service.pip_update(session, user, identity, payload)


@router.post("/pips/{identity}/reviews", status_code=201, dependencies=[Depends(require_access("performance.manage_pip"))])
async def pip_review(identity: uuid.UUID, payload: PIPReviewInput, session: AsyncSession = Session, user: User = Actor):
    return await service.pip_review(session, user, identity, payload)


@router.get("/dashboard", dependencies=[Depends(require_access("performance.view_reports"))])
async def dashboard(company_id: uuid.UUID, cycle_id: uuid.UUID | None = None, session: AsyncSession = Session, user: User = Actor):
    return await service.dashboard(session, user, company_id, cycle_id)


@router.get("/reports/export", dependencies=[Depends(require_access("performance.view_reports"))])
async def export(company_id: uuid.UUID, cycle_id: uuid.UUID | None = None, session: AsyncSession = Session, user: User = Actor):
    report = await service.dashboard(session, user, company_id, cycle_id)
    stream = io.StringIO()
    columns = ["cycle", "employee_name", "employee_number", "branch_name", "department_name", "job_title_name", "manager_name", "status", "self_submitted", "manager_submitted", "review_completed", "finalized", "score", "rating"]
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for item in report["records"]:
        # Spreadsheet formula injection protection for user-entered names.
        writer.writerow({key: "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value for key, value in item.items()})
    return Response("\ufeff" + stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=performance.csv", "Cache-Control": "no-store"})


@router.get("/notifications", dependencies=[Depends(require_access(*VIEW))])
async def notifications(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    await company_for_tenant(session, company_id, user.tenant_id)
    return [service.row(item) for item in (await session.scalars(select(PerformanceNotification).where(PerformanceNotification.tenant_id == user.tenant_id, PerformanceNotification.company_id == company_id, PerformanceNotification.user_id == user.id).order_by(PerformanceNotification.created_at.desc()).limit(100))).all()]


@router.post("/notifications/{identity}/read", dependencies=[Depends(require_access(*VIEW))])
async def read_notification(identity: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    item = await service.get(session, user, PerformanceNotification, identity, True)
    if item.user_id != user.id:
        service.fail("Notification not found", 404)
    item.read_at = service.now()
    return service.row(item)


@router.post("/reminders", dependencies=[Depends(require_access("performance.manage_cycles"))])
async def reminders(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return await service.reminders(session, user, company_id)


@router.post("/reviews/{identity}/action", dependencies=[Depends(require_access("performance.manage_cycles"))])
async def review_action(identity: uuid.UUID, payload: TransitionInput, session: AsyncSession = Session, user: User = Actor):
    return await service.review_action(session, user, identity, payload)
