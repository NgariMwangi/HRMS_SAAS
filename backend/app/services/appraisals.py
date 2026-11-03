"""Replacement appraisal workflow. All mutations lock review before employee record."""
import csv
import io
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from app.api.org import company_for_tenant
from app.models import AuditLog, Branch, Company, Department, Employee, EmployeeSupervisor, JobTitle, User
from app.models.appraisals import AppraisalReview, AppraisalTemplate, EmployeeAppraisal
from app.models.performance import PerformanceNotification
from app.services.access import permissions_for, require_permission
from app.schemas.appraisals import Criterion


def fail(message, code=400):
    raise HTTPException(code, message)


def now():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now(ZoneInfo("Africa/Nairobi")).date()


def row(value):
    return {c.name: getattr(value, c.name) for c in value.__table__.columns}


def name(employee):
    return " ".join(p for p in (employee.first_name, employee.other_names, employee.last_name) if p)


def bump(value, expected):
    if expected != value.version:
        fail("This record changed. Refresh and try again.", 409)
    value.version += 1


async def get(session, user, model, identity, lock=False):
    query = select(model).where(model.id == identity, model.tenant_id == user.tenant_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    value = await session.scalar(query)
    if value is None:
        fail("Appraisal record not found", 404)
    await company_for_tenant(session, value.company_id, user.tenant_id)
    return value


async def people(session, user, company_id):
    await require_permission(session, user, "performance.manage_cycles")
    await company_for_tenant(session, company_id, user.tenant_id)
    employees = list((await session.scalars(select(Employee).where(Employee.company_id == company_id, Employee.status == "ACTIVE").order_by(Employee.first_name, Employee.id))).all())
    links = (await session.scalars(select(EmployeeSupervisor).where(EmployeeSupervisor.company_id == company_id).order_by(EmployeeSupervisor.sort_order, EmployeeSupervisor.id))).all()
    supervisors = {}
    for link in links:
        supervisors.setdefault(link.employee_id, link.supervisor_id)
    active = {e.id for e in employees}
    branches = {b.id: b.name for b in (await session.scalars(select(Branch).where(Branch.company_id == company_id))).all()}
    departments = {d.id: d.name for d in (await session.scalars(select(Department).where(Department.company_id == company_id))).all()}
    return [dict(id=e.id, name=name(e), branch_id=e.branch_id, department_id=e.department_id,
        branch_name=branches.get(e.branch_id, ""), department_name=departments.get(e.department_id, ""),
        manager_id=supervisors.get(e.id) if supervisors.get(e.id) in active else None) for e in employees]


async def employee(session, company_id, identity):
    value = await session.scalar(select(Employee).where(Employee.id == identity, Employee.company_id == company_id, Employee.status == "ACTIVE"))
    if value is None:
        fail("Select an active employee from this company")
    return value


async def event(session, user, entity, action, reason="", previous=None):
    details = dict(action=action, at=now(), actor=user.full_name, reason=reason, version=entity.version)
    if isinstance(entity, EmployeeAppraisal):
        # Keep old versions for authorized audit/reopening without exposing them in read responses.
        if previous is not None:
            details["previous"] = previous
        entity.history = [*(entity.history or []), details]
    session.add(AuditLog(tenant_id=user.tenant_id, actor_kind="TENANT", actor_id=user.id,
        requester=user.email, action=f"appraisal.{action}", request=json.dumps(details, default=str),
        method="DOMAIN", path=f"/performance/simple/{entity.__tablename__}/{entity.id}",
        status_code=200, outcome="SUCCESS", response="Recorded"))


async def notify(session, record, message, employee_ids=None, hr=False, kind="event"):
    created = 0
    query = select(User).where(User.tenant_id == record.tenant_id, User.status == "ACTIVE")
    if not hr:
        query = query.where(User.employee_id.in_([i for i in (employee_ids or []) if i]))
    for user in (await session.scalars(query)).all():
        if hr and "performance.finalize" not in await permissions_for(session, user):
            continue
        key = f"simple:{record.id}:{record.version}:{kind}:{'hr' if hr else 'staff'}" if not kind.startswith("reminder:") else f"simple:{record.id}:{record.status}:{kind}"
        exists = await session.scalar(select(PerformanceNotification.id).where(PerformanceNotification.user_id == user.id, PerformanceNotification.event_key == key))
        if not exists:
            session.add(PerformanceNotification(tenant_id=record.tenant_id, company_id=record.company_id,
                user_id=user.id, event_key=key, message=message, appraisal_id=None))
            created += 1
    return created


def validate_form(criteria, weighted, review=None):
    parsed = [Criterion.model_validate(c) for c in criteria]
    if not parsed or len({c.id for c in parsed}) != len(parsed):
        fail("Add assessment criteria with unique identifiers")
    objectives = [c for c in parsed if c.section == "OBJECTIVE"]
    if weighted and objectives and sum(c.weight for c in objectives) != Decimal(100):
        fail("Individual objective weights must total 100%")
    if weighted and any(c.weight <= 0 for c in objectives):
        fail("Every weighted objective needs a positive weight")
    if review and any(c.due_date and not review.start_date <= c.due_date <= review.end_date for c in parsed):
        fail("Objective due dates must fall within the performance period")


async def save_template(session, user, company_id, payload, identity=None):
    await require_permission(session, user, "performance.manage_cycles")
    await company_for_tenant(session, company_id, user.tenant_id)
    criteria = [c.model_dump(mode="json") for c in payload.criteria]
    validate_form(criteria, payload.weighted)
    if identity:
        value = await get(session, user, AppraisalTemplate, identity, True)
        if value.company_id != company_id:
            fail("Template not found", 404)
        bump(value, payload.version)
    else:
        value = AppraisalTemplate(tenant_id=user.tenant_id, company_id=company_id, version=1)
        session.add(value)
    value.name, value.weighted, value.criteria = payload.name, payload.weighted, criteria
    await session.flush()
    await event(session, user, value, "template_saved")
    return row(value)


async def save_review(session, user, company_id, payload, identity=None):
    await require_permission(session, user, "performance.manage_cycles")
    await company_for_tenant(session, company_id, user.tenant_id)
    if identity:
        review = await get(session, user, AppraisalReview, identity, True)
        if review.company_id != company_id or review.status != "DRAFT":
            fail("Only a draft review can be edited")
        bump(review, payload.version)
    else:
        review = AppraisalReview(tenant_id=user.tenant_id, company_id=company_id, version=1, status="DRAFT")
    template = await get(session, user, AppraisalTemplate, payload.template_id)
    if template.company_id != company_id:
        fail("Choose a template from this company")
    data = payload.model_dump(exclude={"employee_ids", "version"})
    for key, value in data.items():
        setattr(review, key, value)
    # Existing customized forms survive changes to review dates/participants.
    if not review.template_snapshot or str(review.template_snapshot.get("id")) != str(template.id):
        existing = await session.scalar(select(EmployeeAppraisal.id).where(EmployeeAppraisal.review_id == review.id)) if review.id else None
        if existing:
            fail("Create a new draft to use another template; existing individual forms are preserved")
        review.template_snapshot = dict(id=str(template.id), name=template.name, weighted=template.weighted, criteria=template.criteria)
    session.add(review)
    await session.flush()
    available = {str(p["id"]): p for p in await people(session, user, company_id)}
    existing = list((await session.scalars(select(EmployeeAppraisal).where(EmployeeAppraisal.review_id == review.id))).all())
    selected = set(payload.employee_ids)
    for record in existing:
        if record.employee_id not in selected:
            await session.delete(record)
    present = {r.employee_id for r in existing}
    for identity in payload.employee_ids:
        if str(identity) not in available:
            fail("Participants must be active employees of this company")
        if identity in present:
            continue
        person = await employee(session, company_id, identity)
        department = await session.get(Department, person.department_id) if person.department_id else None
        branch = await session.get(Branch, person.branch_id)
        title = await session.get(JobTitle, person.job_title_id) if person.job_title_id else None
        manager_id = available[str(identity)]["manager_id"]
        manager = await employee(session, company_id, manager_id) if manager_id else None
        session.add(EmployeeAppraisal(tenant_id=user.tenant_id, company_id=company_id, review_id=review.id,
            employee_id=identity, manager_id=manager_id, version=1, status="PREPARATION", preparation_ready=False,
            criteria=review.template_snapshot["criteria"], context=dict(employee_name=name(person), employee_number=person.employee_number,
                department_name=department.name if department else "", branch_name=branch.name if branch else "",
                job_title_name=title.name if title else "", manager_name=name(manager) if manager else "Not assigned"),
            self_review={}, manager_review={}, discussion={}, acknowledgement={}, result={}, history=[]))
    await event(session, user, review, "review_saved")
    await session.flush()
    if review.preparation == "MANAGER":
        for record in (await session.scalars(select(EmployeeAppraisal).where(EmployeeAppraisal.review_id == review.id, EmployeeAppraisal.preparation_ready.is_(False)))).all():
            await notify(session, record, f"Prepare individual objectives for {record.context['employee_name']} in {review.name}.", [record.manager_id], kind=f"preparation:{review.version}")
    return row(review)


async def permissions(session, user, record):
    held = await permissions_for(session, user)
    own = user.employee_id == record.employee_id
    manager = not own and user.employee_id is not None and user.employee_id == record.manager_id
    hr = "performance.manage_cycles" in held
    visible = hr or "performance.view_all" in held or own and "performance.view_own" in held or manager and bool({"performance.view_team", "performance.assess_team"} & held)
    if not visible or record.status == "PREPARATION" and not (hr or manager and "performance.assess_team" in held):
        fail("Appraisal not found", 404)
    return dict(own=own, manager=manager and "performance.assess_team" in held, hr=hr,
        finalize="performance.finalize" in held and not own,
        reopen="performance.reopen_appraisal" in held and not own,
        self_assess=own and "performance.self_assess" in held)


async def present(session, user, record, review=None):
    rights = await permissions(session, user, record)
    review = review or await get(session, user, AppraisalReview, record.review_id)
    data = row(record)
    published = record.status in {"ACKNOWLEDGEMENT", "COMPLETED"}
    # Employees see only published manager results; draft self-review stays private to its author.
    if rights["own"] and not published:
        data.update(manager_review={}, discussion={}, result={})
    elif not rights["own"] and record.status in {"PREPARATION", "SELF_REVIEW"}:
        data["self_review"] = {}
    data["history"] = [{k: v for k, v in item.items() if k != "previous"} for item in record.history]
    data["review"] = row(review)
    data["permissions"] = rights
    deadline = review.employee_deadline if record.status == "SELF_REVIEW" else review.acknowledgement_deadline if record.status == "ACKNOWLEDGEMENT" else review.manager_deadline
    data["deadline"] = deadline
    data["overdue"] = record.status not in {"PREPARATION", "COMPLETED"} and deadline < today()
    return data


async def locked_record(session, user, identity, version):
    record = await get(session, user, EmployeeAppraisal, identity)
    review = await get(session, user, AppraisalReview, record.review_id, True)
    record = await get(session, user, EmployeeAppraisal, identity, True)
    rights = await permissions(session, user, record)
    previous = {key: getattr(record, key) for key in ("status", "criteria", "self_review", "manager_review", "discussion", "acknowledgement", "result")}
    if rights["own"] or rights["manager"]:
        await employee(session, record.company_id, user.employee_id)
    bump(record, version)
    return record, review, rights, previous


async def prepare(session, user, identity, payload):
    record, review, rights, previous = await locked_record(session, user, identity, payload.version)
    if review.status != "DRAFT" or not (rights["hr"] or rights["manager"] and review.preparation == "MANAGER"):
        fail("Only HR or the assigned preparation manager can edit a draft form", 403)
    if not rights["hr"] and payload.manager_id != record.manager_id:
        fail("Only HR can change the appraiser", 403)
    manager = await employee(session, record.company_id, payload.manager_id) if payload.manager_id else None
    if payload.manager_id == record.employee_id:
        fail("An employee cannot appraise themselves")
    criteria = [c.model_dump(mode="json") for c in payload.criteria]
    if payload.ready:
        if not manager:
            fail("Assign an appraiser before marking the form ready")
        validate_form(criteria, review.template_snapshot["weighted"], review)
    elif len({c["id"] for c in criteria}) != len(criteria):
        fail("Each criterion must have a unique identifier")
    record.manager_id, record.criteria, record.preparation_ready = payload.manager_id, criteria, payload.ready
    record.context = {**record.context, "manager_name": name(manager) if manager else "Not assigned"}
    await event(session, user, record, "form_prepared", previous=previous)
    if payload.ready and not rights["hr"]:
        await notify(session, record, f"{record.context['employee_name']}'s form is ready for HR to publish.", hr=True)
    elif review.preparation == "MANAGER" and rights["hr"] and not payload.ready:
        await notify(session, record, f"Prepare individual objectives for {record.context['employee_name']} in {review.name}.", [record.manager_id], kind="preparation_assignment")
    await session.flush()
    return await present(session, user, record, review)


async def publish(session, user, identity, payload):
    await require_permission(session, user, "performance.manage_cycles")
    review = await get(session, user, AppraisalReview, identity, True)
    if review.status != "DRAFT":
        fail("This review is already published", 409)
    bump(review, payload.version)
    records = list((await session.scalars(select(EmployeeAppraisal).where(EmployeeAppraisal.review_id == review.id).order_by(EmployeeAppraisal.id).with_for_update())).all())
    if not records:
        fail("Select at least one participant")
    for record in records:
        if not record.preparation_ready or not record.manager_id:
            fail(f"Prepare and confirm the form for {record.context['employee_name']} before publishing")
        await employee(session, review.company_id, record.employee_id)
        await employee(session, review.company_id, record.manager_id)
        for identity, permission, label in ((record.employee_id, "performance.self_assess", record.context["employee_name"]), (record.manager_id, "performance.assess_team", record.context["manager_name"])):
            account = await session.scalar(select(User).where(User.employee_id == identity, User.tenant_id == user.tenant_id, User.status == "ACTIVE"))
            if account is None or permission not in await permissions_for(session, account):
                fail(f"{label} needs an active employee login with {'self-review' if permission.endswith('self_assess') else 'manager assessment'} permission before publication")
        validate_form(record.criteria, review.template_snapshot["weighted"], review)
        record.status = "SELF_REVIEW"
        record.version += 1
        await event(session, user, record, "appraisal_assigned")
        await notify(session, record, f"{review.name}: your appraisal is ready for self-review.", [record.employee_id])
    review.status = "PUBLISHED"
    await event(session, user, review, "review_published")
    return row(review)


def responses_valid(record, payload, manager):
    known = {c["id"] for c in record.criteria}
    supplied = [r.criterion_id for r in payload.responses]
    if len(supplied) != len(set(supplied)) or set(supplied) - known:
        fail("Use each criterion in this appraisal only once")
    if payload.submit:
        if set(supplied) != known or any(not r.comment or manager and r.rating is None for r in payload.responses):
            fail("Complete every criterion with comments" + (" and a manager rating" if manager else ""))
        if not manager and not payload.achievements:
            fail("Describe your achievements before submitting")
        if manager and not payload.summary:
            fail("Add an overall manager summary before submitting")
    if not manager and any(r.rating is not None for r in payload.responses):
        fail("Employee input uses comments; the assigned manager supplies ratings")


def score(record, review):
    ratings = {r["criterion_id"]: Decimal(r["rating"]) for r in record.manager_review["responses"]}
    sections = {}
    for section in ("OBJECTIVE", "BEHAVIOUR"):
        criteria = [c for c in record.criteria if c["section"] == section]
        if not criteria:
            continue
        weighted = section == "OBJECTIVE" and review.template_snapshot["weighted"]
        denominator = Decimal(100) if weighted else Decimal(len(criteria))
        sections[section] = sum((ratings[c["id"]] * (Decimal(c["weight"]) if weighted else 1) for c in criteria), Decimal(0)) / denominator
    total = sections["OBJECTIVE"] * Decimal("0.7") + sections["BEHAVIOUR"] * Decimal("0.3") if len(sections) == 2 else next(iter(sections.values()))
    total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    label = "Significantly below expectations" if total < Decimal("1.5") else "Partly meets expectations" if total < Decimal("2.5") else "Meets expectations" if total < Decimal("3.5") else "Exceeds expectations" if total < Decimal("4.5") else "Significantly exceeds expectations"
    return dict(score=str(total), rating=label, sections={k: str(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)) for k, v in sections.items()})


async def assess(session, user, identity, payload, manager=False):
    record, review, rights, previous = await locked_record(session, user, identity, payload.version)
    allowed = rights["manager"] and record.status in {"MANAGER_REVIEW", "DISCUSSION"} if manager else rights["self_assess"] and record.status == "SELF_REVIEW"
    if not allowed:
        fail("This assessment is not available for editing by your account", 403)
    responses_valid(record, payload, manager)
    data = payload.model_dump(mode="json", exclude={"version", "submit"})
    if payload.submit:
        data["submitted_at"] = now()
    if manager:
        record.manager_review = data
        if payload.submit:
            record.status = "DISCUSSION"
            record.result = score(record, review)
        else:
            # Revising a submitted draft requires fresh submission before discussing/publishing.
            record.status, record.result = "MANAGER_REVIEW", {}
            record.discussion = {k: v for k, v in record.discussion.items() if k != "submitted_at"}
    else:
        record.self_review = data
        if payload.submit:
            record.status = "MANAGER_REVIEW"
            await notify(session, record, f"{record.context['employee_name']} submitted their self-review for {review.name}.", [record.manager_id])
    await event(session, user, record, ("manager" if manager else "self") + ("_submitted" if payload.submit else "_draft_saved"), previous=previous)
    await session.flush()
    return await present(session, user, record, review)


async def discussion(session, user, identity, payload):
    record, review, rights, previous = await locked_record(session, user, identity, payload.version)
    if not rights["manager"] or record.status != "DISCUSSION":
        fail("Only the assigned manager can record this discussion", 403)
    if payload.meeting_date > today():
        fail("The recorded discussion cannot be in the future")
    if len({a.id for a in payload.actions}) != len(payload.actions):
        fail("Development actions need unique identifiers")
    for action in payload.actions:
        await employee(session, record.company_id, action.owner_id)
        if action.due_date < payload.meeting_date:
            fail("Development deadlines cannot precede the discussion")
    record.discussion = payload.model_dump(mode="json", exclude={"version", "submit"})
    if payload.submit:
        record.discussion = {**record.discussion, "submitted_at": now()}
        record.status = "HR_REVIEW"
        await notify(session, record, f"{record.context['employee_name']}'s appraisal is ready for HR review.", hr=True)
    await event(session, user, record, "discussion_submitted" if payload.submit else "discussion_saved", previous=previous)
    await session.flush()
    return await present(session, user, record, review)


async def act(session, user, identity, payload):
    record, review, rights, previous = await locked_record(session, user, identity, payload.version)
    action = payload.action
    if action in {"RETURN_SELF", "RETURN_MANAGER", "CLOSE", "REOPEN"} and not payload.reason:
        fail("Provide a reason for this action")
    if action == "RETURN_SELF":
        if not rights["manager"] or record.status != "MANAGER_REVIEW":
            fail("Only the assigned manager can return a submitted self-review", 403)
        record.status, record.manager_review, record.result, record.discussion = "SELF_REVIEW", {}, {}, {}
        record.self_review = {k: v for k, v in record.self_review.items() if k != "submitted_at"}
        await notify(session, record, f"Self-review returned: {payload.reason}", [record.employee_id])
    elif action == "RETURN_MANAGER":
        if not rights["finalize"] or record.status != "HR_REVIEW":
            fail("Only authorized HR can return an appraisal for correction", 403)
        record.status, record.result = "MANAGER_REVIEW", {}
        record.manager_review = {k: v for k, v in record.manager_review.items() if k != "submitted_at"}
        record.discussion = {k: v for k, v in record.discussion.items() if k != "submitted_at"}
        await notify(session, record, f"HR returned the appraisal: {payload.reason}", [record.manager_id])
    elif action == "PUBLISH":
        if not rights["finalize"] or record.status != "HR_REVIEW":
            fail("Only authorized HR can publish an appraisal after discussion", 403)
        record.status = "ACKNOWLEDGEMENT"
        await notify(session, record, f"Your final appraisal for {review.name} is ready. Please acknowledge receipt.", [record.employee_id])
    elif action == "ACKNOWLEDGE":
        if not rights["own"] or record.status != "ACKNOWLEDGEMENT":
            fail("Only this employee can acknowledge the published appraisal", 403)
        if not payload.agrees and not payload.reason:
            fail("Add a comment explaining your disagreement")
        record.acknowledgement = dict(agrees=payload.agrees, comment=payload.reason, at=now(), by=str(user.id))
        record.status = "COMPLETED"
    elif action == "CLOSE":
        if not rights["finalize"] or record.status != "ACKNOWLEDGEMENT" or today() <= review.acknowledgement_deadline:
            fail("HR can close without acknowledgement only after its deadline", 403)
        record.status = "COMPLETED"
        record.acknowledgement = dict(received=False, closed_by=str(user.id), reason=payload.reason, at=now())
    elif action == "REOPEN":
        if not rights["reopen"] or record.status != "COMPLETED":
            fail("Only authorized HR can reopen a completed appraisal", 403)
        record.status, record.acknowledgement, record.result = "MANAGER_REVIEW", {}, {}
        record.manager_review = {k: v for k, v in record.manager_review.items() if k != "submitted_at"}
        record.discussion = {k: v for k, v in record.discussion.items() if k != "submitted_at"}
        review.status = "PUBLISHED"
        await notify(session, record, f"Appraisal reopened: {payload.reason}", [record.manager_id, record.employee_id])
    await event(session, user, record, action.lower(), payload.reason, previous)
    await session.flush()
    if record.status == "COMPLETED":
        unfinished = await session.scalar(select(EmployeeAppraisal.id).where(EmployeeAppraisal.review_id == review.id, EmployeeAppraisal.status != "COMPLETED").limit(1))
        if unfinished is None:
            review.status = "COMPLETED"
    review.version += 1
    return await present(session, user, record, review)


async def development(session, user, identity, payload):
    record, review, rights, previous = await locked_record(session, user, identity, payload.version)
    if record.status not in {"ACKNOWLEDGEMENT", "COMPLETED"}:
        fail("Development tracking starts when results are published")
    actions = record.discussion.get("actions", [])
    selected = next((a for a in actions if a["id"] == payload.action_id), None)
    if selected is None:
        fail("Development action not found", 404)
    if not (rights["manager"] or rights["finalize"] or rights["own"] and selected["owner_id"] == str(user.employee_id)):
        fail("Only the employee action owner, assigned manager or HR can update progress", 403)
    record.discussion = {**record.discussion, "actions": [{**a, "status": payload.status} if a["id"] == selected["id"] else a for a in actions]}
    await event(session, user, record, "development_updated", previous=previous)
    return await present(session, user, record, review)


async def list_records(session, user, company_id, scope="my", review_id=None, employee_id=None):
    await company_for_tenant(session, company_id, user.tenant_id)
    held = await permissions_for(session, user)
    query = select(EmployeeAppraisal).where(EmployeeAppraisal.tenant_id == user.tenant_id, EmployeeAppraisal.company_id == company_id)
    if scope == "manage":
        if not {"performance.manage_cycles", "performance.view_all", "performance.view_reports", "performance.finalize"} & held:
            fail("You cannot view company appraisals", 403)
        # Reports alone must not expose all appraisal text. They use their dedicated endpoint.
        if not {"performance.manage_cycles", "performance.view_all"} & held:
            fail("Company-wide appraisal visibility is required", 403)
    elif scope == "team":
        await require_permission(session, user, "performance.view_team", "performance.assess_team")
        query = query.where(EmployeeAppraisal.manager_id == user.employee_id, EmployeeAppraisal.employee_id != user.employee_id) if user.employee_id else query.where(False)
    else:
        await require_permission(session, user, "performance.view_own")
        query = query.where(EmployeeAppraisal.employee_id == user.employee_id, EmployeeAppraisal.status != "PREPARATION") if user.employee_id else query.where(False)
    if review_id:
        query = query.where(EmployeeAppraisal.review_id == review_id)
    if employee_id:
        query = query.where(EmployeeAppraisal.employee_id == employee_id)
    records = (await session.scalars(query.order_by(EmployeeAppraisal.created_at.desc(), EmployeeAppraisal.id))).all()
    reviews = {r.id: r for r in (await session.scalars(select(AppraisalReview).where(AppraisalReview.company_id == company_id, AppraisalReview.tenant_id == user.tenant_id))).all()}
    return [await present(session, user, r, reviews[r.review_id]) for r in records]


async def export(session, user, company_id):
    await require_permission(session, user, "performance.view_reports")
    await company_for_tenant(session, company_id, user.tenant_id)
    records = (await session.scalars(select(EmployeeAppraisal).where(EmployeeAppraisal.company_id == company_id, EmployeeAppraisal.tenant_id == user.tenant_id, EmployeeAppraisal.status.in_(["ACKNOWLEDGEMENT", "COMPLETED"])).order_by(EmployeeAppraisal.id))).all()
    stream = io.StringIO()
    writer = csv.writer(stream)
    reviews = {r.id: r for r in (await session.scalars(select(AppraisalReview).where(AppraisalReview.company_id == company_id, AppraisalReview.tenant_id == user.tenant_id))).all()}
    writer.writerow(["Review", "Period start", "Period end", "Employee", "Department", "Appraiser", "Status", "Score", "Rating"])
    for r in records:
        review = reviews[r.review_id]
        values = [review.name, review.start_date, review.end_date, r.context.get("employee_name", ""), r.context.get("department_name", ""), r.context.get("manager_name", ""), r.status, r.result.get("score", ""), r.result.get("rating", "")]
        writer.writerow(["'" + str(v) if str(v).startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else v for v in values])
    return "\ufeff" + stream.getvalue()


async def results(session, user, company_id):
    """Reporting permission grants summaries, never private assessment narratives."""
    await require_permission(session, user, "performance.view_reports")
    await company_for_tenant(session, company_id, user.tenant_id)
    reviews = {r.id: r for r in (await session.scalars(select(AppraisalReview).where(AppraisalReview.tenant_id == user.tenant_id, AppraisalReview.company_id == company_id))).all()}
    output = []
    for r in (await session.scalars(select(EmployeeAppraisal).where(EmployeeAppraisal.tenant_id == user.tenant_id, EmployeeAppraisal.company_id == company_id).order_by(EmployeeAppraisal.created_at.desc(), EmployeeAppraisal.id))).all():
        review = reviews[r.review_id]
        due = review.employee_deadline if r.status == "SELF_REVIEW" else review.acknowledgement_deadline if r.status == "ACKNOWLEDGEMENT" else review.manager_deadline
        output.append(dict(id=r.id, employee_id=r.employee_id, manager_id=r.manager_id, review_id=r.review_id,
            company_id=company_id, context=r.context, review=row(review), version=r.version, status=r.status,
            result=r.result if r.status in {"ACKNOWLEDGEMENT", "COMPLETED"} else {}, deadline=due,
            overdue=r.status not in {"PREPARATION", "COMPLETED"} and due < today(), preparation_ready=r.preparation_ready,
            permissions={}, criteria=[], self_review={}, manager_review={}, discussion={}, acknowledgement={}, history=[]))
    return output


async def reminders(session, user, company_id):
    await company_for_tenant(session, company_id, user.tenant_id)
    # Multiple workers use the same company lock; notification keys remain stable across draft saves.
    await session.scalar(select(Company.id).where(Company.id == company_id).with_for_update())
    created = 0
    records = (await session.scalars(select(EmployeeAppraisal).where(EmployeeAppraisal.company_id == company_id, EmployeeAppraisal.tenant_id == user.tenant_id, EmployeeAppraisal.status.notin_(["PREPARATION", "COMPLETED"])).order_by(EmployeeAppraisal.review_id, EmployeeAppraisal.id))).all()
    for record in records:
        review = await get(session, user, AppraisalReview, record.review_id)
        due = review.employee_deadline if record.status == "SELF_REVIEW" else review.acknowledgement_deadline if record.status == "ACKNOWLEDGEMENT" else review.manager_deadline
        if due < today():
            created += await notify(session, record, f"Overdue: {review.name} — {record.context['employee_name']} ({record.status.replace('_', ' ').lower()}).", [record.employee_id if record.status in {"SELF_REVIEW", "ACKNOWLEDGEMENT"} else record.manager_id], hr=record.status == "HR_REVIEW", kind=f"reminder:{due}")
    return {"notifications_created": created}
