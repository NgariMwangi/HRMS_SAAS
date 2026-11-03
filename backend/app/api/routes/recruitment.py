"""Recruitment: explicit scope checks, human decisions and transactional employee conversion."""
import json
import uuid
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer
from app.api.deps import get_current_user, get_tenant_db
from app.api.access_control import require_access
from app.api.org import company_for_tenant, optional_department_for_company, optional_job_title_for_company
from app.api.routes.employees import create_employee
from app.models import AuditLog, Employee, User
from app.models.recruitment import Application, Candidate, Interview, Offer, RecruitmentEvent, Vacancy
from app.schemas.employee import EmployeeCreate
from app.schemas.recruitment import ApplyInput, CandidateInput, FeedbackInput, HireInput, InterviewInput, JobInput, OfferInput, StageInput, StatusInput
from app.services.access import permissions_for, require_permission

router = APIRouter(prefix="/recruitment", tags=["recruitment"])
Session = Depends(get_tenant_db)
Current = Depends(get_current_user)
ACTIVE = {"APPLIED", "SHORTLISTED", "INTERVIEW"}


def fail(message, code=400):
    raise HTTPException(code, message)


def row(value):
    return {c.name: getattr(value, c.name) for c in value.__table__.columns if c.name != "cv_data"}


def base(user, company_id):
    return dict(tenant_id=user.tenant_id, company_id=company_id)


async def get(session, user, model, identity, lock=False):
    query = select(model).where(model.id == identity, model.tenant_id == user.tenant_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    value = await session.scalar(query)
    if value is None:
        fail("Recruitment record not found", 404)
    await company_for_tenant(session, value.company_id, user.tenant_id)
    return value


async def manage(session, user):
    await require_permission(session, user, "recruitment.manage")


async def accessible_jobs(session, user, company_id):
    held = await require_permission(session, user, "recruitment.manage", "recruitment.view_assigned", "recruitment.interview")
    query = select(Vacancy.id).where(Vacancy.tenant_id == user.tenant_id, Vacancy.company_id == company_id)
    if "recruitment.manage" not in held:
        if user.employee_id is None:
            return []
        interview_apps = select(Interview.application_id).where(Interview.tenant_id == user.tenant_id,
            Interview.company_id == company_id, Interview.interviewer_ids.contains([str(user.employee_id)]))
        interview_jobs = select(Application.job_id).where(Application.id.in_(interview_apps), Application.tenant_id == user.tenant_id)
        conditions = []
        if "recruitment.view_assigned" in held:
            conditions.append(Vacancy.manager_id == user.employee_id)
        if "recruitment.interview" in held:
            conditions.append(Vacancy.id.in_(interview_jobs))
        query = query.where(or_(*conditions))
    return list((await session.scalars(query)).all())


async def accessible_applications(session, user, company_id, jobs):
    held = await permissions_for(session, user)
    query = select(Application.id).where(Application.tenant_id == user.tenant_id, Application.company_id == company_id, Application.job_id.in_(jobs))
    if "recruitment.manage" not in held:
        owned_jobs = select(Vacancy.id).where(Vacancy.tenant_id == user.tenant_id, Vacancy.manager_id == user.employee_id) if "recruitment.view_assigned" in held and user.employee_id else select(Vacancy.id).where(False)
        interviews = select(Interview.application_id).where(Interview.tenant_id == user.tenant_id, Interview.interviewer_ids.contains([str(user.employee_id)])) if "recruitment.interview" in held and user.employee_id else select(Interview.application_id).where(False)
        query = query.where(or_(Application.job_id.in_(owned_jobs), Application.id.in_(interviews)))
    return list((await session.scalars(query)).all())


async def visible_candidate(session, user, identity):
    candidate = await get(session, user, Candidate, identity)
    if "recruitment.manage" not in await permissions_for(session, user):
        jobs = await accessible_jobs(session, user, candidate.company_id)
        applications = await accessible_applications(session, user, candidate.company_id, jobs)
        if not await session.scalar(select(Application.id).where(Application.id.in_(applications), Application.candidate_id == identity)):
            fail("Candidate not found", 404)
    return candidate


async def employee_reference(session, company_id, identity):
    if identity and not await session.scalar(select(Employee.id).where(Employee.company_id == company_id, Employee.id == identity, Employee.status == "ACTIVE")):
        fail("Select an active employee from this company", 404)


async def job_references(session, user, company_id, payload):
    await optional_department_for_company(session, payload.department_id, company_id)
    await optional_job_title_for_company(session, payload.job_title_id, company_id)
    await employee_reference(session, company_id, payload.manager_id)


async def event(session, user, job, action, note="", application=None):
    session.add(RecruitmentEvent(**base(user, job.company_id), job_id=job.id, application_id=application.id if application else None, actor_id=user.id, action=action, note=note))
    session.add(AuditLog(tenant_id=user.tenant_id, actor_kind="TENANT", actor_id=user.id, requester=user.email,
        action=f"recruitment.{action}", request=json.dumps({"job_id": str(job.id), "application_id": str(application.id) if application else None, "note": note}),
        method="DOMAIN", path=f"/recruitment/jobs/{job.id}", status_code=200, outcome="SUCCESS", response="Recorded"))


async def app_job(session, user, identity, lock=True):
    # All workflows lock vacancy before application: consistent ordering prevents hiring races.
    app = await get(session, user, Application, identity)
    job = await get(session, user, Vacancy, app.job_id, lock)
    app = await get(session, user, Application, identity, lock)
    return app, job


def accepting(job):
    if job.status != "OPEN":
        fail("Open this vacancy before adding applications")
    if job.closing_date and job.closing_date < datetime.now(ZoneInfo("Africa/Nairobi")).date():
        fail("This vacancy's application closing date has passed")


@router.get("/workspace")
async def workspace(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Current):
    await company_for_tenant(session, company_id, user.tenant_id)
    jobs = await accessible_jobs(session, user, company_id)
    applications = await accessible_applications(session, user, company_id, jobs)
    held = await permissions_for(session, user)
    def query(model):
        return select(model).where(model.tenant_id == user.tenant_id, model.company_id == company_id).order_by(model.created_at.desc())
    job_rows = list((await session.scalars(query(Vacancy).where(Vacancy.id.in_(jobs)))).all())
    app_rows = list((await session.scalars(query(Application).where(Application.id.in_(applications)))).all())
    candidates = query(Candidate)
    if "recruitment.manage" not in held:
        candidates = candidates.where(Candidate.id.in_([a.candidate_id for a in app_rows]))
    candidate_rows = [row(c) for c in (await session.scalars(candidates)).all()]
    if "recruitment.manage" not in held:
        for c in candidate_rows:
            c.pop("notes", None)
            c.pop("employee_id", None)
    interviews = query(Interview).where(Interview.application_id.in_(applications))
    if "recruitment.manage" not in held:
        managed = {j.id for j in job_rows if "recruitment.view_assigned" in held and j.manager_id == user.employee_id}
        managed_apps = [a.id for a in app_rows if a.job_id in managed]
        interviews = interviews.where(or_(Interview.application_id.in_(managed_apps), Interview.interviewer_ids.contains([str(user.employee_id)])))
    # Interview feedback is private to panel members, assigned hiring managers and HR.
    interview_rows = [row(i) for i in (await session.scalars(interviews)).all()]
    offers = [row(o) for o in (await session.scalars(query(Offer).where(Offer.application_id.in_(applications)))).all()] if "recruitment.manage" in held else []
    events = query(RecruitmentEvent).where(or_(RecruitmentEvent.application_id.in_(applications), RecruitmentEvent.application_id.is_(None) & RecruitmentEvent.job_id.in_(jobs)))
    event_rows = [row(e) for e in (await session.scalars(events)).all()] if "recruitment.manage" in held else []
    return {"jobs": [row(j) for j in job_rows], "candidates": candidate_rows, "applications": [row(a) for a in app_rows], "interviews": interview_rows, "offers": offers, "events": event_rows}


@router.get("/people")
async def people(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Current):
    await company_for_tenant(session, company_id, user.tenant_id)
    await require_permission(session, user, "recruitment.manage", "recruitment.view_assigned", "recruitment.interview")
    # Only names and interview eligibility, no contact, salary or personnel data.
    employees = list((await session.scalars(select(Employee).where(Employee.company_id == company_id, Employee.status == "ACTIVE").order_by(Employee.first_name))).all())
    users = list((await session.scalars(select(User).where(User.tenant_id == user.tenant_id, User.status == "ACTIVE", User.employee_id.in_([e.id for e in employees])))).all())
    eligible = {u.employee_id for u in users if "recruitment.interview" in await permissions_for(session, u)}
    return [dict(id=e.id, name=f"{e.first_name} {e.last_name}", can_interview=e.id in eligible) for e in employees]


@router.post("/jobs", status_code=201, dependencies=[Depends(require_access("recruitment.manage"))])
async def add_job(company_id: uuid.UUID, payload: JobInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    await company_for_tenant(session, company_id, user.tenant_id)
    await job_references(session, user, company_id, payload)
    job = Vacancy(**base(user, company_id), **payload.model_dump())
    session.add(job)
    await session.flush()
    await event(session, user, job, "Job created")
    return row(job)


@router.put("/jobs/{identity}", dependencies=[Depends(require_access("recruitment.manage"))])
async def edit_job(identity: uuid.UUID, payload: JobInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    job = await get(session, user, Vacancy, identity, True)
    await job_references(session, user, job.company_id, payload)
    if job.status == "CLOSED":
        fail("Reopen this vacancy before editing")
    hired = len((await session.scalars(select(Application.id).where(Application.job_id == job.id, Application.stage == "HIRED"))).all())
    if payload.openings < hired:
        fail("Openings cannot be fewer than the employees already hired")
    for key, value in payload.model_dump().items():
        setattr(job, key, value)
    await event(session, user, job, "Job updated")
    return row(job)


@router.post("/jobs/{identity}/status", dependencies=[Depends(require_access("recruitment.manage"))])
async def job_status(identity: uuid.UUID, payload: StatusInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    job = await get(session, user, Vacancy, identity, True)
    if payload.status not in {"OPEN", "CLOSED", "DRAFT"}:
        fail("Invalid vacancy status")
    if payload.status == "OPEN" and not job.description.strip():
        fail("Add a job description before opening the vacancy")
    if payload.status == "OPEN" and job.closing_date and job.closing_date < datetime.now(ZoneInfo("Africa/Nairobi")).date():
        fail("Update the closing date before reopening this vacancy")
    if payload.status == "DRAFT" and await session.scalar(select(Application.id).where(Application.job_id == job.id).limit(1)):
        fail("A vacancy with applications cannot return to draft")
    job.status = payload.status
    await event(session, user, job, f"Job {payload.status.lower()}", payload.note)
    return row(job)


@router.post("/candidates", status_code=201, dependencies=[Depends(require_access("recruitment.manage"))])
async def add_candidate(company_id: uuid.UUID, payload: CandidateInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    await company_for_tenant(session, company_id, user.tenant_id)
    candidate = Candidate(**base(user, company_id), **payload.model_dump())
    session.add(candidate)
    try:
        await session.flush()
    except IntegrityError:
        fail("A candidate with this email already exists. Add another application to their profile.", 409)
    return row(candidate)


@router.put("/candidates/{identity}", dependencies=[Depends(require_access("recruitment.manage"))])
async def edit_candidate(identity: uuid.UUID, payload: CandidateInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    candidate = await get(session, user, Candidate, identity, True)
    for key, value in payload.model_dump().items():
        setattr(candidate, key, value)
    try:
        await session.flush()
    except IntegrityError:
        fail("A candidate with this email already exists", 409)
    return row(candidate)


@router.post("/candidates/{identity}/cv", dependencies=[Depends(require_access("recruitment.manage"))])
async def upload_cv(identity: uuid.UUID, file: UploadFile = File(...), session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    candidate = await get(session, user, Candidate, identity, True)
    content = await file.read(10 * 1024 * 1024 + 1)
    if not content or len(content) > 10 * 1024 * 1024:
        fail("Upload a CV up to 10 MB")
    name = (file.filename or "cv.pdf").replace("\\", "/").split("/")[-1][:255]
    extension = name.rsplit(".", 1)[-1].lower()
    types = {"pdf": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    if extension not in types or (extension == "pdf" and not content.startswith(b"%PDF-")) or (extension == "docx" and not content.startswith(b"PK")):
        fail("Upload a PDF or Word (.docx) CV")
    candidate.cv_name, candidate.cv_type, candidate.cv_data = name, types[extension], content
    return {"cv_name": name}


@router.get("/candidates/{identity}/cv")
async def download_cv(identity: uuid.UUID, session: AsyncSession = Session, user: User = Current):
    candidate = await visible_candidate(session, user, identity)
    loaded = await session.scalar(select(Candidate).options(undefer(Candidate.cv_data)).where(Candidate.id == candidate.id, Candidate.tenant_id == user.tenant_id))
    if not loaded.cv_data:
        fail("No CV uploaded", 404)
    return Response(loaded.cv_data, media_type=loaded.cv_type, headers={"Content-Disposition": "attachment", "X-Content-Type-Options": "nosniff"})


@router.post("/applications", status_code=201, dependencies=[Depends(require_access("recruitment.manage"))])
async def apply(payload: ApplyInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    job = await get(session, user, Vacancy, payload.job_id, True)
    candidate = await get(session, user, Candidate, payload.candidate_id, True)
    if candidate.company_id != job.company_id:
        fail("Candidate and vacancy must belong to the same company", 404)
    if candidate.employee_id:
        fail("This candidate has already been hired")
    accepting(job)
    application = Application(**base(user, job.company_id), job_id=job.id, candidate_id=candidate.id)
    session.add(application)
    try:
        await session.flush()
    except IntegrityError:
        fail("This candidate already has an application for this vacancy", 409)
    await event(session, user, job, "Application added", application=application)
    return row(application)


@router.post("/applications/{identity}/stage", dependencies=[Depends(require_access("recruitment.manage"))])
async def stage(identity: uuid.UUID, payload: StageInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    application, job = await app_job(session, user, identity)
    if application.stage == "HIRED":
        fail("A hired application cannot be changed")
    offer = await session.scalar(select(Offer).where(Offer.application_id == application.id))
    if offer and offer.status in {"ISSUED", "ACCEPTED"}:
        fail("Withdraw the active offer before changing this application")
    if payload.stage in {"REJECTED", "WITHDRAWN"} and not payload.note:
        fail("Add a reason for this decision")
    if payload.stage in ACTIVE and job.status != "OPEN":
        fail("Reopen this vacancy before progressing an application")
    application.stage = payload.stage
    await event(session, user, job, f"Application {payload.stage.lower()}", payload.note, application)
    return row(application)


@router.post("/interviews", status_code=201, dependencies=[Depends(require_access("recruitment.manage"))])
async def schedule(payload: InterviewInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    application, job = await app_job(session, user, payload.application_id)
    if application.stage not in ACTIVE or job.status != "OPEN":
        fail("Interviews require an active application and an open vacancy")
    for identity in payload.interviewer_ids:
        await employee_reference(session, job.company_id, identity)
        linked = await session.scalar(select(User).where(User.tenant_id == user.tenant_id, User.employee_id == identity, User.status == "ACTIVE"))
        if not linked or "recruitment.interview" not in await permissions_for(session, linked):
            fail("Each interviewer needs an active login with recruitment interview permission")
    if payload.starts_at <= datetime.now(timezone.utc):
        fail("Choose a future interview time")
    data = payload.model_dump()
    data["interviewer_ids"] = list(dict.fromkeys(str(i) for i in payload.interviewer_ids))
    interview = Interview(**base(user, job.company_id), **data)
    session.add(interview)
    application.stage = "INTERVIEW"
    await session.flush()
    await event(session, user, job, "Interview scheduled", f"{interview.title}: {interview.starts_at.isoformat()}", application)
    return row(interview)


@router.post("/interviews/{identity}/feedback", dependencies=[Depends(require_access("recruitment.interview"))])
async def feedback(identity: uuid.UUID, payload: FeedbackInput, session: AsyncSession = Session, user: User = Current):
    await require_permission(session, user, "recruitment.interview")
    interview = await get(session, user, Interview, identity, True)
    if str(user.employee_id) not in interview.interviewer_ids:
        fail("Only assigned interviewers can submit feedback", 403)
    if interview.status == "CANCELLED":
        fail("This interview was cancelled")
    application = await get(session, user, Application, interview.application_id)
    if application.stage == "HIRED":
        fail("Feedback is closed for a hired application")
    interview.feedback = {**interview.feedback, str(user.employee_id): {**payload.model_dump(), "submitted_at": datetime.now(timezone.utc).isoformat()}}
    if all(i in interview.feedback for i in interview.interviewer_ids):
        interview.status = "COMPLETED"
    job = await get(session, user, Vacancy, application.job_id)
    await event(session, user, job, "Interview feedback submitted", application=application)
    return row(interview)


@router.post("/interviews/{identity}/cancel", dependencies=[Depends(require_access("recruitment.manage"))])
async def cancel_interview(identity: uuid.UUID, payload: StatusInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    initial = await get(session, user, Interview, identity)
    application, job = await app_job(session, user, initial.application_id)
    interview = await get(session, user, Interview, identity, True)
    if interview.status != "SCHEDULED":
        fail("Only scheduled interviews can be cancelled")
    if not payload.note:
        fail("Add a cancellation reason")
    interview.status = "CANCELLED"
    await event(session, user, job, "Interview cancelled", payload.note, application)
    return row(interview)


@router.post("/offers", status_code=201, dependencies=[Depends(require_access("recruitment.manage"))])
async def add_offer(payload: OfferInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    application, job = await app_job(session, user, payload.application_id)
    if application.stage not in ACTIVE or job.status != "OPEN":
        fail("Offers require an active application and an open vacancy")
    offer = Offer(**base(user, job.company_id), **payload.model_dump())
    session.add(offer)
    try:
        await session.flush()
    except IntegrityError:
        fail("This application already has an offer. Edit the existing offer.", 409)
    await event(session, user, job, "Offer drafted", application=application)
    return row(offer)


@router.put("/offers/{identity}", dependencies=[Depends(require_access("recruitment.manage"))])
async def edit_offer(identity: uuid.UUID, payload: OfferInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    initial = await get(session, user, Offer, identity)
    application, job = await app_job(session, user, initial.application_id)
    offer = await get(session, user, Offer, identity, True)
    if offer.status not in {"DRAFT", "DECLINED", "WITHDRAWN"} or application.stage == "HIRED":
        fail("Withdraw the offer before editing its terms")
    if payload.application_id != offer.application_id:
        fail("An offer cannot be moved to another application")
    for key, value in payload.model_dump().items():
        setattr(offer, key, value)
    offer.status = "DRAFT"
    await event(session, user, job, "Offer updated", application=application)
    return row(offer)


@router.post("/offers/{identity}/status", dependencies=[Depends(require_access("recruitment.manage"))])
async def offer_status(identity: uuid.UUID, payload: StatusInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    initial = await get(session, user, Offer, identity)
    application, job = await app_job(session, user, initial.application_id)
    offer = await get(session, user, Offer, identity, True)
    transitions = {"DRAFT": {"ISSUED", "WITHDRAWN"}, "ISSUED": {"ACCEPTED", "DECLINED", "WITHDRAWN"}, "ACCEPTED": {"WITHDRAWN"}}
    if application.stage == "HIRED" or payload.status not in transitions.get(offer.status, set()):
        fail("Invalid offer transition")
    if payload.status in {"ISSUED", "ACCEPTED"}:
        if job.status != "OPEN" or application.stage not in ACTIVE | {"OFFER"}:
            fail("The vacancy and application must be active")
        if offer.expires_on and offer.expires_on < datetime.now(ZoneInfo("Africa/Nairobi")).date():
            fail("This offer has expired. Withdraw it and update its dates.")
    if payload.status in {"DECLINED", "WITHDRAWN"} and not payload.note:
        fail("Add a reason for this decision")
    offer.status = payload.status
    application.stage = "OFFER" if payload.status in {"ISSUED", "ACCEPTED"} else "SHORTLISTED"
    await event(session, user, job, f"Offer {payload.status.lower()}", payload.note, application)
    return row(offer)


@router.post("/applications/{identity}/hire", dependencies=[Depends(require_access("recruitment.manage")), Depends(require_access("people.manage"))])
async def hire(identity: uuid.UUID, payload: HireInput, session: AsyncSession = Session, user: User = Current):
    await manage(session, user)
    await require_permission(session, user, "people.manage")
    application, job = await app_job(session, user, identity)
    candidate = await get(session, user, Candidate, application.candidate_id, True)
    if application.stage == "HIRED" or candidate.employee_id:
        fail("This candidate has already been hired", 409)
    offer = await session.scalar(select(Offer).where(Offer.application_id == application.id).with_for_update())
    if not offer or offer.status != "ACCEPTED" or job.status != "OPEN":
        fail("Hiring requires an accepted offer and an open vacancy")
    hired = len((await session.scalars(select(Application.id).where(Application.job_id == job.id, Application.stage == "HIRED"))).all())
    if hired >= job.openings:
        fail("All openings for this vacancy have been filled")
    duplicate = await session.scalar(select(Employee.id).where(Employee.company_id == job.company_id,
        or_(Employee.personal_email == candidate.email, Employee.email == candidate.email)))
    if duplicate:
        fail("An employee with this candidate's email already exists. Review the employee record before hiring.", 409)
    employee_payload = EmployeeCreate(company_id=job.company_id, branch_id=payload.branch_id, department_id=job.department_id,
        job_title_id=job.job_title_id, first_name=candidate.first_name, last_name=candidate.last_name, phone=candidate.phone or None,
        email=payload.work_email, personal_email=candidate.email, employment_type=job.employment_type,
        date_joined=payload.date_joined, date_ended=payload.date_ended, supervisor_ids=[job.manager_id] if job.manager_id else [])
    employee = await create_employee(employee_payload, user.tenant_id, session, user)
    candidate.employee_id = employee.id
    application.stage = "HIRED"
    await event(session, user, job, "Employee created", f"Employee number: {employee.employee_number}", application)
    # No automatic payroll, login provisioning, or external messages.
    return {"employee_id": employee.id, "employee_number": employee.employee_number}
