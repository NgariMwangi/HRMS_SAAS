"""Performance authorization, transactional workflows, snapshots and reporting."""
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.org import company_for_tenant
from app.models import AuditLog, Branch, Company, Department, Employee, EmployeeSupervisor, JobTitle, User
from app.models.performance import (
    Appraisal, Competency, DevelopmentAction, GoalProgress, PerformanceCheckIn,
    PerformanceCycle, PerformanceEvent, PerformanceGoal, PerformanceNotification,
    PerformanceParticipant, PerformancePIP, PerformancePIPReview, PerformanceSettings, RatingScale,
)
from app.schemas.performance import SettingsInput
from app.services.access import permissions_for, require_permission
from app.services.performance_scoring import calculate, rating_for, validate_rating

STAGES = ["DRAFT", "GOAL_SETTING", "ACTIVE", "SELF_ASSESSMENT", "MANAGER_ASSESSMENT", "REVIEW", "CALIBRATION", "FINALIZATION", "COMPLETED"]


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fail(message, code=400):
    raise HTTPException(code, message)


def dump(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return json.loads(json.dumps(value, default=lambda item: item.isoformat() if isinstance(item, (date, datetime)) else str(item)))


def row(value):
    return {column.name: dump(getattr(value, column.name)) for column in value.__table__.columns}


def base(user, company_id):
    return {"tenant_id": user.tenant_id, "company_id": company_id}


async def get(session, user, model, identity, lock=False):
    query = select(model).where(model.id == identity, model.tenant_id == user.tenant_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    value = await session.scalar(query)
    if value is None:
        fail("Performance record not found", 404)
    await company_for_tenant(session, value.company_id, user.tenant_id)
    return value


async def company_employee(session, user, company_id, employee_id):
    await company_for_tenant(session, company_id, user.tenant_id)
    employee = await session.scalar(select(Employee).where(Employee.id == employee_id, Employee.company_id == company_id))
    if employee is None:
        fail("Employee not found in this company", 404)
    return employee


async def reference(session, model, identity, company_id):
    if identity is not None and await session.scalar(select(model.id).where(model.id == identity, model.company_id == company_id)) is None:
        fail("Reference does not belong to this company", 404)


def version(value, expected):
    if value.version != expected:
        fail("Record changed. Refresh before continuing.", 409)
    value.version += 1


async def event(session, user, entity, action, details=None, appraisal_id=None):
    session.add(PerformanceEvent(**base(user, entity.company_id), actor_id=user.id, entity_id=entity.id,
        appraisal_id=appraisal_id, action=action, details=dump(details or {})))
    session.add(AuditLog(tenant_id=user.tenant_id, actor_kind="TENANT", actor_id=user.id, requester=user.email,
        action=f"performance.{action}", request=json.dumps(dump(details or {})), method="DOMAIN",
        path=f"/performance/{entity.__tablename__}/{entity.id}", status_code=200, outcome="SUCCESS", response="Recorded"))


async def notify(session, user, company_id, employee_ids, key, message, appraisal_id=None, user_ids=None):
    identities = list((await session.scalars(select(User).where(User.tenant_id == user.tenant_id, User.status == "ACTIVE", or_(User.employee_id.in_([item for item in employee_ids if item]), User.id.in_(user_ids or []))))).all())
    for identity in identities:
        exists = await session.scalar(select(PerformanceNotification.id).where(PerformanceNotification.user_id == identity.id, PerformanceNotification.event_key == key))
        if not exists:
            session.add(PerformanceNotification(**base(user, company_id), user_id=identity.id, event_key=key,
                message=message, appraisal_id=appraisal_id))
    await session.flush()


async def notify_authorities(session, actor, appraisal, permission, key, message):
    recipients = []
    for user in (await session.scalars(select(User).where(User.tenant_id == actor.tenant_id, User.status == "ACTIVE"))).all():
        if permission not in await permissions_for(session, user):
            continue
        visible = await session.scalar(select(PerformanceParticipant.id).where(PerformanceParticipant.id == appraisal.participant_id, await participant_scope(session, user)))
        if visible:
            recipients.append(user.id)
    await notify(session, actor, appraisal.company_id, [], key, message, appraisal.id, recipients)


async def config_for(session, user, company_id):
    await company_for_tenant(session, company_id, user.tenant_id)
    settings = await session.scalar(select(PerformanceSettings).where(PerformanceSettings.company_id == company_id, PerformanceSettings.tenant_id == user.tenant_id))
    return settings.config if settings else dump(SettingsInput())


async def save_settings(session, user, company_id, payload):
    await require_permission(session, user, "performance.manage_settings")
    await company_for_tenant(session, company_id, user.tenant_id)
    # Company row also serializes first-time settings creation.
    await session.scalar(select(Company).where(Company.id == company_id).with_for_update())
    config = dump(payload)
    if payload.rating_scale_id:
        scale = await get(session, user, RatingScale, payload.rating_scale_id)
        if scale.company_id != company_id:
            fail("Rating scale belongs to another company", 404)
        for threshold in (payload.pip_threshold, payload.development_threshold):
            if threshold is not None:
                try:
                    validate_rating(threshold, scale.levels)
                except ValueError as exc:
                    fail(str(exc))
    settings = await session.scalar(select(PerformanceSettings).where(PerformanceSettings.company_id == company_id))
    old = settings.config if settings else None
    if settings:
        settings.config = config
    else:
        settings = PerformanceSettings(**base(user, company_id), config=config)
        session.add(settings)
    await session.flush()
    await event(session, user, settings, "settings_updated", {"old": old, "new": config})
    return config


async def create_catalog(session, user, company_id, payload, model):
    permission = "performance.manage_rating_scales" if model is RatingScale else "performance.manage_competencies"
    await require_permission(session, user, permission)
    await company_for_tenant(session, company_id, user.tenant_id)
    data = dump(payload)
    if model is Competency:
        for key, reference_model in (("department_ids", Department), ("job_title_ids", JobTitle), ("employee_ids", Employee)):
            for identity in getattr(payload, key):
                await reference(session, reference_model, identity, company_id)
        item = model(**base(user, company_id), name=payload.name, definition=data)
    else:
        item = model(**base(user, company_id), name=payload.name, levels=data["levels"])
    session.add(item)
    await session.flush()
    await event(session, user, item, "catalog_created", data)
    return row(item)


async def update_catalog(session, user, identity, payload, model):
    permission = "performance.manage_rating_scales" if model is RatingScale else "performance.manage_competencies"
    await require_permission(session, user, permission)
    item = await get(session, user, model, identity, True)
    old = row(item)
    data = dump(payload)
    if model is Competency:
        for key, reference_model in (("department_ids", Department), ("job_title_ids", JobTitle), ("employee_ids", Employee)):
            for ref in getattr(payload, key):
                await reference(session, reference_model, ref, item.company_id)
        item.definition = data
    else:
        item.levels = data["levels"]
    item.name = payload.name
    await event(session, user, item, "catalog_updated", {"old": old, "new": data})
    return row(item)


async def create_cycle(session, user, company_id, payload):
    await require_permission(session, user, "performance.manage_cycles")
    config = dict(await config_for(session, user, company_id))
    if not config.get("rating_scale_id"):
        fail("Configure a rating scale before creating a cycle")
    scale = await get(session, user, RatingScale, uuid.UUID(config["rating_scale_id"]))
    if scale.company_id != company_id:
        fail("Rating scale belongs to another company", 404)
    if payload.goal_entry_roles is not None:
        config["goal_entry_roles"] = list(dict.fromkeys(payload.goal_entry_roles))
    config["rating_scale"] = {"id": str(scale.id), "name": scale.name, "levels": scale.levels}
    cycle = PerformanceCycle(**base(user, company_id), **payload.model_dump(exclude={"windows", "goal_entry_roles"}), windows=dump(payload)["windows"], config=config)
    session.add(cycle)
    await session.flush()
    await event(session, user, cycle, "cycle_created", row(cycle))
    return row(cycle)


async def update_cycle(session, user, identity, payload):
    await require_permission(session, user, "performance.manage_cycles")
    cycle = await get(session, user, PerformanceCycle, identity, True)
    if cycle.status == "COMPLETED":
        fail("Completed cycle is immutable; reopen an appraisal first", 409)
    if cycle.status not in ("DRAFT", "GOAL_SETTING") and (cycle.name != payload.name or cycle.frequency != payload.frequency or cycle.start_date != payload.start_date or cycle.end_date != payload.end_date):
        fail("Only deadlines may change after the cycle becomes active", 409)
    goals = list((await session.scalars(select(PerformanceGoal).join(Appraisal, PerformanceGoal.appraisal_id == Appraisal.id).join(PerformanceParticipant, Appraisal.participant_id == PerformanceParticipant.id).where(PerformanceParticipant.cycle_id == cycle.id))).all())
    if any(date.fromisoformat(goal.definition["start_date"]) < payload.start_date or date.fromisoformat(goal.definition["due_date"]) > payload.end_date for goal in goals):
        fail("Cycle period must contain every existing goal")
    old = row(cycle)
    if payload.goal_entry_roles is not None:
        if cycle.status not in ("DRAFT", "GOAL_SETTING") and set(payload.goal_entry_roles) != set(cycle.config.get("goal_entry_roles", ["HR", "MANAGER"] + (["EMPLOYEE"] if cycle.config["employee_goal_creation"] else []))):
            fail("Goal entry permissions are locked after goal setting", 409)
        cycle.config = {**cycle.config, "goal_entry_roles": list(dict.fromkeys(payload.goal_entry_roles))}
    version(cycle, payload.version)
    cycle.name, cycle.frequency = payload.name, payload.frequency
    cycle.start_date, cycle.end_date, cycle.windows = payload.start_date, payload.end_date, dump(payload)["windows"]
    await event(session, user, cycle, "cycle_updated", {"old": old, "new": row(cycle), "reason": payload.reason})
    return row(cycle)


async def reassign_appraiser(session, user, identity, payload):
    await require_permission(session, user, "performance.manage_cycles")
    appraisal, participant, cycle, permissions = await appraisal_context(session, user, identity, True)
    mutable(appraisal)
    if appraisal.manager_assessment.get("submitted_at"):
        fail("Reopen the manager assessment before reassigning its appraiser", 409)
    manager = await company_employee(session, user, cycle.company_id, payload.manager_id)
    if payload.manager_id == participant.employee_id or payload.reviewer_id == participant.employee_id:
        fail("Employee cannot appraise themselves")
    await reference(session, Employee, payload.reviewer_id, cycle.company_id)
    old = row(participant)
    version(appraisal, payload.version)
    participant.manager_id, participant.reviewer_id = payload.manager_id, payload.reviewer_id
    participant.context = {**participant.context, "manager_id": str(manager.id), "manager_name": f"{manager.first_name} {manager.last_name}"}
    # Ratings entered by a previous appraiser stay in history; the new appraiser
    # starts an independent draft, while the employee assessment is preserved.
    await event(session, user, appraisal, "appraiser_reassigned", {"old": old, "previous_manager_assessment": appraisal.manager_assessment, "new": row(participant), "reason": payload.reason}, appraisal.id)
    appraisal.manager_assessment, appraisal.scores = {}, {}
    await notify(session, user, cycle.company_id, [manager.id], f"reassigned:{appraisal.id}:{appraisal.version}", f"Assigned as appraiser for {participant.context['employee_name']}", appraisal.id)
    return await present(session, user, appraisal, participant, cycle, permissions)


async def assign_participants(session, user, cycle_id, payload):
    await require_permission(session, user, "performance.manage_cycles")
    cycle = await get(session, user, PerformanceCycle, cycle_id, True)
    if cycle.status not in ("DRAFT", "GOAL_SETTING"):
        fail("Participants are assigned before the active stage", 409)
    for model, identity in ((Branch, payload.branch_id), (Department, payload.department_id), (JobTitle, payload.job_title_id), (Employee, payload.manager_id), (Employee, payload.reviewer_id)):
        await reference(session, model, identity, cycle.company_id)
    if not (payload.all_employees or payload.employee_ids or payload.branch_id or payload.department_id or payload.job_title_id):
        fail("Select employees or a company, branch, department or job title")
    for identity in payload.employee_ids:
        await company_employee(session, user, cycle.company_id, identity)
    query = select(Employee).where(Employee.company_id == cycle.company_id, Employee.status == "ACTIVE")
    for key in ("branch_id", "department_id", "job_title_id"):
        if getattr(payload, key):
            query = query.where(getattr(Employee, key) == getattr(payload, key))
    if payload.employee_ids:
        query = query.where(Employee.id.in_(payload.employee_ids))
    employees = list((await session.scalars(query.order_by(Employee.id))).all())
    definitions = list((await session.scalars(select(Competency).where(Competency.company_id == cycle.company_id, Competency.tenant_id == user.tenant_id))).all())
    existing = set((await session.scalars(select(PerformanceParticipant.employee_id).where(PerformanceParticipant.cycle_id == cycle.id))).all())
    results = []
    for employee in employees:
        if employee.id in existing:
            continue
        manager_id = payload.manager_id or await session.scalar(select(EmployeeSupervisor.supervisor_id).where(EmployeeSupervisor.employee_id == employee.id, EmployeeSupervisor.company_id == cycle.company_id).order_by(EmployeeSupervisor.sort_order, EmployeeSupervisor.id).limit(1))
        if manager_id == employee.id or payload.reviewer_id == employee.id:
            fail("Employee cannot appraise themselves")
        manager = await company_employee(session, user, cycle.company_id, manager_id) if manager_id else None
        context = {"employee_name": f"{employee.first_name} {employee.last_name}", "employee_number": employee.employee_number,
            "company_name": (await session.get(Company, cycle.company_id)).name,
            "manager_name": f"{manager.first_name} {manager.last_name}" if manager else "Unassigned"}
        for key, model in (("branch", Branch), ("department", Department), ("job_title", JobTitle)):
            identity = getattr(employee, f"{key}_id")
            resource = await session.get(model, identity) if identity else None
            context[f"{key}_id"] = str(identity) if identity else None
            context[f"{key}_name"] = resource.name if resource else ""
        context["manager_id"] = str(manager_id) if manager_id else None
        participant = PerformanceParticipant(**base(user, cycle.company_id), cycle_id=cycle.id, employee_id=employee.id,
            manager_id=manager_id, reviewer_id=payload.reviewer_id, context=context)
        session.add(participant)
        await session.flush()
        competencies = []
        for definition in definitions:
            data = definition.definition
            if not data["active"]:
                continue
            conditions = [(data["department_ids"], str(employee.department_id)), (data["job_title_ids"], str(employee.job_title_id)), (data["employee_ids"], str(employee.id))]
            if any(ids for ids, _ in conditions) and not any(value in ids for ids, value in conditions):
                continue
            competencies.append({**data, "id": str(definition.id)})
        if Decimal(cycle.config["competency_weight"]) > 0 and not competencies:
            fail(f"Assign at least one competency to {context['employee_name']} before adding them")
        appraisal = Appraisal(**base(user, cycle.company_id), participant_id=participant.id, competencies=competencies)
        session.add(appraisal)
        await session.flush()
        await event(session, user, participant, "participant_assigned", context, appraisal.id)
        await notify(session, user, cycle.company_id, [employee.id, manager_id], f"assigned:{appraisal.id}", f"Assigned to {cycle.name}", appraisal.id)
        results.append({**row(participant), "appraisal_id": str(appraisal.id)})
    return results


async def participant_scope(session, user):
    permissions = await permissions_for(session, user)
    if "performance.view_all" in permissions:
        return True
    scopes = []
    if "performance.view_own" in permissions and user.employee_id:
        scopes.append(PerformanceParticipant.employee_id == user.employee_id)
    if "performance.view_team" in permissions and user.employee_id:
        scopes.extend([PerformanceParticipant.manager_id == user.employee_id, PerformanceParticipant.reviewer_id == user.employee_id,
            PerformanceParticipant.employee_id.in_(select(EmployeeSupervisor.employee_id).where(EmployeeSupervisor.supervisor_id == user.employee_id))])
    return or_(*scopes) if scopes else False


async def list_appraisals(session, user, company_id, cycle_id=None, employee_id=None, team=False):
    await company_for_tenant(session, company_id, user.tenant_id)
    query = select(Appraisal, PerformanceParticipant, PerformanceCycle).join(PerformanceParticipant, Appraisal.participant_id == PerformanceParticipant.id).join(PerformanceCycle, PerformanceCycle.id == PerformanceParticipant.cycle_id).where(Appraisal.tenant_id == user.tenant_id, Appraisal.company_id == company_id, await participant_scope(session, user))
    if cycle_id:
        cycle = await get(session, user, PerformanceCycle, cycle_id)
        if cycle.company_id != company_id:
            fail("Cycle belongs to another company", 404)
        query = query.where(PerformanceParticipant.cycle_id == cycle_id)
    if employee_id:
        query = query.where(PerformanceParticipant.employee_id == employee_id)
    if team:
        query = query.where(PerformanceParticipant.employee_id != user.employee_id) if user.employee_id else query
    result = []
    permissions = await permissions_for(session, user)
    for appraisal, participant, cycle in (await session.execute(query.order_by(PerformanceCycle.start_date.desc(), PerformanceParticipant.created_at))).all():
        item = await present(session, user, appraisal, participant, cycle, permissions, detail=False)
        result.append(item)
    return result


async def appraisal_context(session, user, identity, lock=False):
    # Lock cycle first in every workflow: consistent ordering with cycle transitions.
    initial = await get(session, user, Appraisal, identity)
    participant = await get(session, user, PerformanceParticipant, initial.participant_id)
    cycle = await get(session, user, PerformanceCycle, participant.cycle_id, lock)
    appraisal = await get(session, user, Appraisal, identity, lock)
    permissions = await permissions_for(session, user)
    visible = await session.scalar(select(PerformanceParticipant.id).where(PerformanceParticipant.id == participant.id, await participant_scope(session, user)))
    if not visible:
        fail("Appraisal not found", 404)
    return appraisal, participant, cycle, permissions


def mutable(appraisal):
    if appraisal.finalized_at:
        fail("Finalized appraisal must be reopened before editing", 409)


def assigned(user, participant, permissions, permission="performance.assess_team"):
    if permission not in permissions:
        fail("Performance permission required", 403)
    if user.employee_id == participant.employee_id:
        fail("You cannot assess or approve your own appraisal", 403)
    if "performance.view_all" not in permissions and user.employee_id not in (participant.manager_id, participant.reviewer_id):
        fail("Only the assigned appraiser can perform this action", 403)


def own(user, participant, permissions, permission):
    if user.employee_id != participant.employee_id or permission not in permissions:
        fail("Employee action is only available to the employee", 403)


def window(cycle, stage):
    dates = cycle.windows.get(stage)
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Africa/Nairobi")).date()
    if dates and not date.fromisoformat(dates["start"]) <= today <= date.fromisoformat(dates["end"]):
        fail(f"{stage.replace('_', ' ').title()} is outside its allowed dates", 409)


async def goals_for(session, appraisal):
    return list((await session.scalars(select(PerformanceGoal).where(PerformanceGoal.appraisal_id == appraisal.id, PerformanceGoal.tenant_id == appraisal.tenant_id).order_by(PerformanceGoal.created_at, PerformanceGoal.id))).all())


def valid_goals(goals, config):
    active = [goal for goal in goals if goal.status != "CANCELLED"]
    if Decimal(config["kpi_weight"]) > 0:
        if not active or sum((goal.weight for goal in active), Decimal(0)) != 100:
            fail("Active goal weights must total 100")
        if any(goal.status not in ("APPROVED", "IN_PROGRESS", "COMPLETED") for goal in active):
            fail("Every active goal must be approved")
    return active


async def transition_cycle(session, user, identity, payload):
    await require_permission(session, user, "performance.manage_cycles")
    cycle = await get(session, user, PerformanceCycle, identity, True)
    stages = [item for item in STAGES if item != "CALIBRATION" or cycle.config["require_calibration"]]
    if cycle.status == "COMPLETED" or payload.status != stages[stages.index(cycle.status) + 1]:
        fail("Invalid cycle transition", 409)
    appraisals = list((await session.scalars(select(Appraisal).join(PerformanceParticipant, Appraisal.participant_id == PerformanceParticipant.id).where(PerformanceParticipant.cycle_id == cycle.id).with_for_update(of=Appraisal))).all())
    if payload.status != "GOAL_SETTING" and not appraisals:
        fail("Assign participants before advancing the cycle")
    if payload.status == "ACTIVE":
        for appraisal in appraisals:
            valid_goals(await goals_for(session, appraisal), cycle.config)
    for appraisal in appraisals:
        gates = {
            "MANAGER_ASSESSMENT": ("require_self", appraisal.self_assessment.get("submitted_at"), "self-assessment"),
            "REVIEW": ("require_manager", appraisal.manager_assessment.get("submitted_at"), "manager assessment"),
            "CALIBRATION": ("require_review", appraisal.review.get("completed_at"), "review meeting"),
            "FINALIZATION": ("require_calibration" if cycle.config["require_calibration"] else "require_review", appraisal.scores.get("calibrated_at") if cycle.config["require_calibration"] else appraisal.review.get("completed_at"), "calibration" if cycle.config["require_calibration"] else "review meeting"),
        }
        gate = gates.get(payload.status)
        if gate and cycle.config[gate[0]] and not gate[1]:
            fail(f"Complete every required {gate[2]} before advancing", 409)
        if payload.status == "CALIBRATION" and not appraisal.scores.get("pre_calibration"):
            source = appraisal.manager_assessment or (appraisal.self_assessment if not cycle.config["require_manager"] else {})
            try:
                appraisal.scores = calculate(valid_goals(await goals_for(session, appraisal), cycle.config), appraisal.competencies, source, cycle.config)
            except ValueError as exc:
                fail(str(exc))
    if payload.status == "COMPLETED" and any(not appraisal.finalized_at for appraisal in appraisals):
        fail("Finalize every appraisal before completing the cycle")
    old = cycle.status
    version(cycle, payload.version)
    cycle.status = payload.status
    for appraisal in appraisals:
        if payload.status in ("ACTIVE", "SELF_ASSESSMENT") and appraisal.status in ("GOAL_SETTING", "ACTIVE"):
            appraisal.status = payload.status
            appraisal.version += 1
        if not appraisal.finalized_at and payload.status in ("MANAGER_ASSESSMENT", "REVIEW", "CALIBRATION", "FINALIZATION"):
            # Optional stages can be skipped without fabricating completion dates.
            appraisal.status = payload.status
            appraisal.version += 1
        participant = await get(session, user, PerformanceParticipant, appraisal.participant_id)
        await notify(session, user, cycle.company_id, [participant.employee_id, participant.manager_id], f"cycle:{cycle.id}:{cycle.status}:{appraisal.id}", f"{cycle.name}: {cycle.status.replace('_', ' ').title()}", appraisal.id)
        if payload.status in ("CALIBRATION", "FINALIZATION"):
            await notify_authorities(session, user, appraisal, "performance.calibrate" if payload.status == "CALIBRATION" else "performance.finalize", f"authority:{cycle.id}:{cycle.status}:{appraisal.id}", f"{participant.context['employee_name']}: {cycle.status.replace('_', ' ').title()} required")
    await event(session, user, cycle, "cycle_transition", {"old": old, "new": cycle.status})
    return row(cycle)


async def present(session, user, appraisal, participant, cycle, permissions, detail=True):
    result = {**row(appraisal), "participant": row(participant), "cycle": row(cycle)}
    result["self_submitted"] = bool(appraisal.self_assessment.get("submitted_at"))
    result["manager_submitted"] = bool(appraisal.manager_assessment.get("submitted_at"))
    is_own = user.employee_id == participant.employee_id
    privileged = "performance.view_all" in permissions
    if is_own and not privileged and not cycle.config["employee_view_manager"]:
        result["manager_assessment"] = {}
        result["scores"] = {key: val for key, val in appraisal.scores.items() if key in ("final", "final_rating") or key.startswith("calibrat") and cycle.config["employee_view_calibration"]}
        result["review"] = {key: val for key, val in appraisal.review.items() if key not in ("manager_comments", "disagreements")}
    if is_own and not privileged and not cycle.config["employee_view_calibration"]:
        result["scores"] = {key: val for key, val in result["scores"].items() if not key.startswith("calibrat")}
    goals = await goals_for(session, appraisal)
    result["goal_count"] = len([goal for goal in goals if goal.status != "CANCELLED"])
    result["completed_goals"] = sum(goal.status == "COMPLETED" for goal in goals)
    active = [goal for goal in goals if goal.status != "CANCELLED"]
    result["goal_progress"] = str(sum((goal.progress * goal.weight for goal in active), Decimal(0)) / (sum((goal.weight for goal in active), Decimal(0)) or 1))
    if detail:
        result["goals"] = [row(goal) for goal in goals]
        result["check_ins"] = [row(item) for item in (await session.scalars(select(PerformanceCheckIn).where(PerformanceCheckIn.appraisal_id == appraisal.id).order_by(PerformanceCheckIn.meeting_date, PerformanceCheckIn.created_at))).all()]
        if is_own and not privileged and not cycle.config["employee_view_manager"]:
            for check_in in result["check_ins"]:
                check_in["details"].pop("manager_feedback", None)
        result["development_actions"] = [row(item) for item in (await session.scalars(select(DevelopmentAction).where(DevelopmentAction.appraisal_id == appraisal.id).order_by(DevelopmentAction.due_date))).all()]
        # Internal audit/calibration reasons are never leaked through the employee endpoint.
        result["events"] = [row(item) for item in (await session.scalars(select(PerformanceEvent).where(PerformanceEvent.appraisal_id == appraisal.id).order_by(PerformanceEvent.created_at))).all() if not item.action.startswith("pip_") or "performance.manage_pip" in permissions] if privileged or "performance.calibrate" in permissions else []
    return result


async def detail(session, user, identity):
    appraisal, participant, cycle, permissions = await appraisal_context(session, user, identity)
    return await present(session, user, appraisal, participant, cycle, permissions)


async def goal_actor(session, user, appraisal_id, permission=None):
    appraisal, participant, cycle, permissions = await appraisal_context(session, user, appraisal_id, True)
    mutable(appraisal)
    if permission:
        assigned(user, participant, permissions, permission)
    elif user.employee_id == participant.employee_id:
        own(user, participant, permissions, "performance.manage_own_goals")
    else:
        assigned(user, participant, permissions)
    return appraisal, participant, cycle, permissions


def goal_entry_allowed(user, participant, cycle, permissions):
    roles = cycle.config.get("goal_entry_roles")
    if roles is None:
        return user.employee_id != participant.employee_id or cycle.config["employee_goal_creation"]
    if user.employee_id == participant.employee_id:
        return "EMPLOYEE" in roles and "performance.manage_own_goals" in permissions
    return ("HR" in roles and "performance.manage_cycles" in permissions) or (
        "MANAGER" in roles and user.employee_id in (participant.manager_id, participant.reviewer_id)
        and "performance.assess_team" in permissions)


async def create_goal(session, user, identity, payload):
    appraisal, participant, cycle, permissions = await goal_actor(session, user, identity)
    if not goal_entry_allowed(user, participant, cycle, permissions):
        fail("Your role cannot enter goals for this review", 403)
    if appraisal.status != "GOAL_SETTING" or cycle.status not in ("DRAFT", "GOAL_SETTING"):
        fail("Goals are created during goal setting", 409)
    window(cycle, "GOAL_SETTING")
    if payload.start_date < cycle.start_date or payload.due_date > cycle.end_date:
        fail("Goal dates must be inside the performance period")
    goal = PerformanceGoal(**base(user, cycle.company_id), appraisal_id=appraisal.id, title=payload.title,
        weight=payload.weight, definition=dump(payload), approval={"created_by": str(user.id), "created_at": now().isoformat()})
    session.add(goal)
    await session.flush()
    await event(session, user, goal, "goal_created", dump(payload), appraisal.id)
    return row(goal)


async def goal_context(session, user, identity):
    initial = await get(session, user, PerformanceGoal, identity)
    context = await goal_actor(session, user, initial.appraisal_id)
    goal = await get(session, user, PerformanceGoal, identity, True)
    return goal, context


async def update_goal(session, user, identity, payload):
    goal, (appraisal, participant, cycle, permissions) = await goal_context(session, user, identity)
    if not goal_entry_allowed(user, participant, cycle, permissions):
        fail("Your role cannot enter goals for this review", 403)
    if appraisal.status not in ("GOAL_SETTING", "ACTIVE") or cycle.status not in ("DRAFT", "GOAL_SETTING", "ACTIVE"):
        fail("Goal definitions are locked after assessment opens", 409)
    if payload.start_date < cycle.start_date or payload.due_date > cycle.end_date:
        fail("Goal dates must be inside the performance period")
    old = row(goal)
    version(goal, payload.version)
    goal.title, goal.weight = payload.title, payload.weight
    goal.definition = dump(payload.model_copy())
    goal.definition.pop("version", None)
    goal.definition.pop("reason", None)
    goal.status = "DRAFT"
    goal.approval = {**goal.approval, "changed_by": str(user.id), "reason": payload.reason, "changed_at": now().isoformat()}
    await event(session, user, goal, "goal_changed_requires_approval", {"old": old, "new": row(goal), "reason": payload.reason}, appraisal.id)
    return row(goal)


async def goal_action(session, user, identity, action, payload):
    goal, (appraisal, participant, cycle, permissions) = await goal_context(session, user, identity)
    if appraisal.status not in ("GOAL_SETTING", "ACTIVE") or cycle.status not in ("DRAFT", "GOAL_SETTING", "ACTIVE"):
        fail("Goal approval is closed", 409)
    if cycle.status in ("DRAFT", "GOAL_SETTING"):
        window(cycle, "GOAL_SETTING")
    if action in ("approve", "request-changes", "reject", "cancel"):
        assigned(user, participant, permissions)
    if action == "submit":
        if goal.status != "DRAFT":
            fail("Only draft goals can be submitted", 409)
        goal.status = "PENDING_APPROVAL" if cycle.config["manager_goal_approval"] else "APPROVED"
    elif action == "approve":
        if goal.status != "PENDING_APPROVAL":
            fail("Goal is not awaiting approval", 409)
        goal.status = "APPROVED"
    elif action in ("request-changes", "reject"):
        if goal.status != "PENDING_APPROVAL" or not payload.reason:
            fail("A pending goal and reason are required")
        goal.status = "DRAFT"
    elif action == "cancel":
        if not payload.reason or goal.status == "CANCELLED":
            fail("Cancellation requires a reason and an active goal")
        goal.status = "CANCELLED"
    else:
        fail("Unknown goal action", 404)
    version(goal, payload.version)
    goal.approval = {**goal.approval, f"{action}_by": str(user.id), f"{action}_at": now().isoformat(), "reason": payload.reason}
    await event(session, user, goal, f"goal_{action}", row(goal), appraisal.id)
    await notify(session, user, cycle.company_id, [participant.manager_id if action == "submit" else participant.employee_id], f"goal:{goal.id}:{goal.version}", f"Goal {action}: {goal.title}", appraisal.id)
    return row(goal)


async def add_progress(session, user, identity, payload):
    goal, (appraisal, participant, cycle, permissions) = await goal_context(session, user, identity)
    if appraisal.status not in ("GOAL_SETTING", "ACTIVE", "SELF_ASSESSMENT") or cycle.status not in ("GOAL_SETTING", "ACTIVE", "SELF_ASSESSMENT"):
        fail("Progress is locked after self-assessment", 409)
    if appraisal.self_assessment.get("submitted_at") or goal.status not in ("APPROVED", "IN_PROGRESS", "COMPLETED"):
        fail("Progress requires an approved goal and an open self-assessment", 409)
    if goal.definition["measurement"] == "BOOLEAN" and payload.actual is not None and payload.actual not in (0, 1):
        fail("Boolean actual must be 0 or 1")
    old = {"progress": str(goal.progress), "actual": str(goal.actual) if goal.actual is not None else None}
    version(goal, payload.version)
    goal.progress, goal.actual = payload.progress, payload.actual
    goal.status = "COMPLETED" if payload.progress == 100 else "IN_PROGRESS"
    progress = GoalProgress(**base(user, goal.company_id), goal_id=goal.id, recorded_by=user.id, details={**dump(payload), "previous": old})
    session.add(progress)
    await session.flush()
    await event(session, user, goal, "progress_recorded", progress.details, appraisal.id)
    return row(goal)


async def progress_history(session, user, identity):
    goal = await get(session, user, PerformanceGoal, identity)
    await appraisal_context(session, user, goal.appraisal_id)
    return [row(item) for item in (await session.scalars(select(GoalProgress).where(GoalProgress.goal_id == goal.id).order_by(GoalProgress.created_at, GoalProgress.id))).all()]


async def add_check_in(session, user, identity, payload):
    appraisal, participant, cycle, permissions = await goal_actor(session, user, identity)
    if appraisal.status not in ("GOAL_SETTING", "ACTIVE", "SELF_ASSESSMENT", "MANAGER_ASSESSMENT"):
        fail("Check-ins are closed", 409)
    if user.employee_id == participant.employee_id and payload.manager_feedback:
        fail("Only the assigned manager can record manager feedback", 403)
    for goal_id in payload.goal_ids:
        goal = await get(session, user, PerformanceGoal, goal_id)
        if goal.appraisal_id != appraisal.id:
            fail("Check-in goal belongs to another appraisal", 404)
    item = PerformanceCheckIn(**base(user, cycle.company_id), appraisal_id=appraisal.id, recorded_by=user.id,
        meeting_date=payload.meeting_date, details=dump(payload))
    session.add(item)
    await session.flush()
    await event(session, user, item, "check_in_recorded", dump(payload), appraisal.id)
    return row(item)


def assessment_valid(payload, goals, competencies, levels, submitted=False, automatic=False):
    goal_ids = {str(goal.id) for goal in goals}
    competency_ids = {item["id"] for item in competencies}
    for key, allowed in (("goals", goal_ids), ("competencies", competency_ids)):
        values = payload.get(key, [])
        ids = [item["id"] for item in values]
        if len(ids) != len(set(ids)) or set(ids) - allowed:
            fail("Assessment contains duplicate or unrelated items")
        if submitted and not (key == "goals" and automatic) and set(ids) != allowed:
            fail("Rate every assigned goal and competency before submitting")
        for item in values:
            try:
                validate_rating(item["rating"], levels)
            except ValueError as exc:
                fail(str(exc))


async def assessment(session, user, identity, kind, payload, submit=False):
    appraisal, participant, cycle, permissions = await appraisal_context(session, user, identity, True)
    mutable(appraisal)
    if kind == "self":
        own(user, participant, permissions, "performance.self_assess")
        if cycle.status != "SELF_ASSESSMENT" or appraisal.status != "SELF_ASSESSMENT" or appraisal.self_assessment.get("submitted_at"):
            fail("Self-assessment is not open", 409)
        window(cycle, "SELF_ASSESSMENT")
    else:
        assigned(user, participant, permissions)
        if cycle.status != "MANAGER_ASSESSMENT" or appraisal.manager_assessment.get("submitted_at"):
            fail("Manager assessment is not open", 409)
        if cycle.config["require_self"] and not appraisal.self_assessment.get("submitted_at"):
            fail("Employee must submit self-assessment first", 409)
        if appraisal.status not in ("SELF_ASSESSMENT", "MANAGER_ASSESSMENT", "ACTIVE"):
            fail("Invalid manager assessment stage", 409)
        window(cycle, "MANAGER_ASSESSMENT")
    goals = valid_goals(await goals_for(session, appraisal), cycle.config)
    data = dump(payload) if payload else dict(getattr(appraisal, f"{kind}_assessment"))
    data.pop("version", None)
    assessment_valid(data, goals, appraisal.competencies, cycle.config["rating_scale"]["levels"], submit,
        kind == "manager" and cycle.config["auto_scoring"])
    version(appraisal, payload.version)
    data["started_at"] = getattr(appraisal, f"{kind}_assessment").get("started_at", now().isoformat())
    if submit:
        data["submitted_at"], data["submitted_by"] = now().isoformat(), str(user.id)
        if kind == "manager":
            try:
                appraisal.scores = calculate(goals, appraisal.competencies, data, cycle.config)
            except ValueError as exc:
                fail(str(exc))
        appraisal.status = "MANAGER_ASSESSMENT" if kind == "self" else "REVIEW"
    setattr(appraisal, f"{kind}_assessment", data)
    await event(session, user, appraisal, f"{kind}_assessment_{'submitted' if submit else 'saved'}", {"assessment": data}, appraisal.id)
    if submit:
        await notify(session, user, cycle.company_id, [participant.manager_id if kind == "self" else participant.employee_id], f"assessment:{appraisal.id}:{kind}:{appraisal.version}", f"{kind.title()} assessment submitted for {cycle.name}", appraisal.id)
    return await present(session, user, appraisal, participant, cycle, permissions)


async def review(session, user, identity, payload):
    appraisal, participant, cycle, permissions = await appraisal_context(session, user, identity, True)
    mutable(appraisal)
    assigned(user, participant, permissions)
    if cycle.status != "REVIEW" or appraisal.status != "REVIEW" or (cycle.config["require_manager"] and not appraisal.manager_assessment.get("submitted_at")):
        fail("Review meeting is not available", 409)
    version(appraisal, payload.version)
    appraisal.review = {**dump(payload), "completed_at": now().isoformat(), "recorded_by": str(user.id)}
    appraisal.status = "CALIBRATION" if cycle.config["require_calibration"] else "FINALIZATION"
    await event(session, user, appraisal, "review_completed", appraisal.review, appraisal.id)
    await notify(session, user, cycle.company_id, [participant.employee_id], f"review:{appraisal.id}:{appraisal.version}", "Your appraisal is ready for acknowledgement", appraisal.id)
    return await present(session, user, appraisal, participant, cycle, permissions)


async def acknowledge(session, user, identity, payload):
    appraisal, participant, cycle, permissions = await appraisal_context(session, user, identity, True)
    mutable(appraisal)
    own(user, participant, permissions, "performance.view_own")
    if cycle.config["require_review"] and not appraisal.review.get("completed_at"):
        fail("Review must be completed before acknowledgement", 409)
    if appraisal.status not in ("CALIBRATION", "FINALIZATION"):
        fail("Appraisal is not ready for acknowledgement", 409)
    if payload.status != "ACKNOWLEDGED" and not payload.comments:
        fail("Comments are required when recording comments or disagreement")
    version(appraisal, payload.version)
    appraisal.acknowledgement = {**dump(payload), "acknowledged_at": now().isoformat(), "by": str(user.id)}
    await event(session, user, appraisal, "acknowledged", appraisal.acknowledgement, appraisal.id)
    return await present(session, user, appraisal, participant, cycle, permissions)


async def calibrate(session, user, identity, payload):
    await require_permission(session, user, "performance.calibrate")
    appraisal, participant, cycle, permissions = await appraisal_context(session, user, identity, True)
    mutable(appraisal)
    if not cycle.config["require_calibration"] or cycle.status != "CALIBRATION" or appraisal.status not in ("CALIBRATION", "FINALIZATION"):
        fail("Calibration is not open", 409)
    if not appraisal.scores.get("pre_calibration"):
        fail("Manager scoring is required before calibration")
    try:
        label = rating_for(payload.score, cycle.config["rating_scale"]["levels"])
    except ValueError as exc:
        fail(str(exc))
    old = dict(appraisal.scores)
    version(appraisal, payload.version)
    appraisal.scores = {**old, "calibrated": str(payload.score), "calibrated_rating": label, "calibration_reason": payload.reason, "calibrated_at": now().isoformat(), "calibrated_by": str(user.id)}
    appraisal.status = "FINALIZATION"
    await event(session, user, appraisal, "calibration", {"old": old, "new": appraisal.scores, "reason": payload.reason}, appraisal.id)
    return await present(session, user, appraisal, participant, cycle, permissions)


async def finalize(session, user, identity, payload):
    await require_permission(session, user, "performance.finalize")
    appraisal, participant, cycle, permissions = await appraisal_context(session, user, identity, True)
    mutable(appraisal)
    if cycle.status != "FINALIZATION":
        fail("Cycle must be in finalization", 409)
    window(cycle, "FINALIZATION")
    for required, completed, label in (
        ("require_self", appraisal.self_assessment.get("submitted_at"), "self-assessment"),
        ("require_manager", appraisal.manager_assessment.get("submitted_at"), "manager assessment"),
        ("require_review", appraisal.review.get("completed_at"), "review meeting"),
        ("require_calibration", appraisal.scores.get("calibrated_at"), "calibration"),
        ("require_acknowledgement", appraisal.acknowledgement.get("acknowledged_at"), "employee acknowledgement"),
    ):
        if cycle.config[required] and not completed:
            fail(f"Complete {label} before finalization", 409)
    try:
        assessment_source = appraisal.manager_assessment or (appraisal.self_assessment if not cycle.config["require_manager"] else {})
        scores = calculate(valid_goals(await goals_for(session, appraisal), cycle.config), appraisal.competencies, assessment_source, cycle.config)
        final = appraisal.scores.get("calibrated", scores["pre_calibration"])
        label = rating_for(final, cycle.config["rating_scale"]["levels"])
    except ValueError as exc:
        fail(str(exc))
    version(appraisal, payload.version)
    appraisal.scores = {**appraisal.scores, **scores, "final": final, "final_rating": label,
        "recommend_development": cycle.config["development_threshold"] is not None and Decimal(final) < Decimal(cycle.config["development_threshold"]),
        "recommend_pip": cycle.config["pip_threshold"] is not None and Decimal(final) < Decimal(cycle.config["pip_threshold"])}
    appraisal.finalized_at, appraisal.finalized_by, appraisal.status = now(), user.id, "FINALIZED"
    await event(session, user, appraisal, "finalized", {**row(appraisal), "participant": row(participant), "cycle": row(cycle)}, appraisal.id)
    await notify(session, user, cycle.company_id, [participant.employee_id, participant.manager_id], f"final:{appraisal.id}:{appraisal.version}", f"{cycle.name} appraisal finalized", appraisal.id)
    return await present(session, user, appraisal, participant, cycle, permissions)


async def reopen(session, user, identity, payload):
    await require_permission(session, user, "performance.reopen_appraisal")
    appraisal, participant, cycle, permissions = await appraisal_context(session, user, identity, True)
    if appraisal.status in ("GOAL_SETTING", "ACTIVE") and not appraisal.finalized_at:
        fail("Appraisal is already open", 409)
    if payload.stage in ("REVIEW", "FINALIZATION"):
        for required, submitted in (("require_self", appraisal.self_assessment.get("submitted_at")), ("require_manager", appraisal.manager_assessment.get("submitted_at"))):
            if cycle.config[required] and not submitted:
                fail("Reopen the incomplete assessment stage first", 409)
    if payload.stage == "FINALIZATION" and (cycle.config["require_review"] and not appraisal.review.get("completed_at") or cycle.config["require_calibration"] and not appraisal.scores.get("calibrated_at")):
        fail("Reopen the incomplete review/calibration stage first", 409)
    old = row(appraisal)
    version(appraisal, payload.version)
    appraisal.finalized_at, appraisal.finalized_by = None, None
    appraisal.status = payload.stage
    appraisal.scores = {key: val for key, val in appraisal.scores.items() if key not in ("final", "final_rating", "recommend_development", "recommend_pip") and (payload.stage == "FINALIZATION" or not key.startswith("calibrat"))} if payload.stage in ("REVIEW", "FINALIZATION") else {}
    appraisal.acknowledgement = {}
    if payload.stage != "FINALIZATION":
        appraisal.review = {}
    if payload.stage in ("GOAL_SETTING", "SELF_ASSESSMENT", "MANAGER_ASSESSMENT"):
        appraisal.manager_assessment = {key: val for key, val in appraisal.manager_assessment.items() if not key.startswith("submitted")}
    if payload.stage in ("GOAL_SETTING", "SELF_ASSESSMENT"):
        appraisal.self_assessment = {key: val for key, val in appraisal.self_assessment.items() if not key.startswith("submitted")}
    # Reopening a completed cycle is explicit and audited as part of this operation.
    cycle.status = payload.stage
    cycle.version += 1
    await event(session, user, appraisal, "reopened", {"old": old, "reason": payload.reason, "stage": payload.stage}, appraisal.id)
    await event(session, user, cycle, "cycle_reopened", {"reason": payload.reason, "stage": payload.stage})
    return await present(session, user, appraisal, participant, cycle, permissions)


async def development_create(session, user, identity, payload):
    appraisal, participant, cycle, permissions = await appraisal_context(session, user, identity, True)
    assigned(user, participant, permissions, "performance.manage_development_plans")
    await company_employee(session, user, cycle.company_id, payload.owner_id)
    action = DevelopmentAction(**base(user, cycle.company_id), appraisal_id=appraisal.id, owner_id=payload.owner_id,
        title=payload.title, due_date=payload.due_date, details=dump(payload))
    session.add(action)
    await session.flush()
    await event(session, user, action, "development_created", dump(payload), appraisal.id)
    await notify(session, user, cycle.company_id, [payload.owner_id], f"development:{action.id}", f"Development action assigned: {action.title}", appraisal.id)
    return row(action)


async def development_update(session, user, identity, payload):
    initial = await get(session, user, DevelopmentAction, identity)
    appraisal, participant, cycle, permissions = await appraisal_context(session, user, initial.appraisal_id, True)
    assigned(user, participant, permissions, "performance.manage_development_plans")
    action = await get(session, user, DevelopmentAction, identity, True)
    old = row(action)
    version(action, payload.version)
    action.status, action.progress = payload.status, Decimal(100) if payload.status == "COMPLETED" else payload.progress
    action.details = {**action.details, "comments": payload.comments, "completed_at": now().isoformat() if payload.status == "COMPLETED" else None}
    await event(session, user, action, "development_updated", {"old": old, "new": row(action)}, appraisal.id)
    return row(action)


async def pip_create(session, user, company_id, payload):
    await require_permission(session, user, "performance.manage_pip")
    await company_employee(session, user, company_id, payload.employee_id)
    await company_employee(session, user, company_id, payload.manager_id)
    hr = await session.scalar(select(User).where(User.id == payload.hr_owner_id, User.tenant_id == user.tenant_id, User.status == "ACTIVE"))
    if not hr or "performance.manage_pip" not in await permissions_for(session, hr):
        fail("HR owner must have permission to manage PIPs")
    if hr.employee_id:
        await company_employee(session, user, company_id, hr.employee_id)
    if payload.appraisal_id:
        appraisal = await get(session, user, Appraisal, payload.appraisal_id)
        participant = await get(session, user, PerformanceParticipant, appraisal.participant_id)
        if appraisal.company_id != company_id or participant.employee_id != payload.employee_id:
            fail("PIP appraisal does not match this employee/company", 404)
    item = PerformancePIP(**base(user, company_id), employee_id=payload.employee_id, manager_id=payload.manager_id,
        hr_owner_id=payload.hr_owner_id, appraisal_id=payload.appraisal_id, start_date=payload.start_date,
        end_date=payload.end_date, details=dump(payload))
    session.add(item)
    await session.flush()
    await event(session, user, item, "pip_created", dump(payload), payload.appraisal_id)
    return row(item)


async def pip_update(session, user, identity, payload):
    await require_permission(session, user, "performance.manage_pip")
    item = await get(session, user, PerformancePIP, identity, True)
    allowed = {"DRAFT": {"ACTIVE", "CANCELLED"}, "ACTIVE": {"EXTENDED", "SUCCESSFUL", "UNSUCCESSFUL", "CANCELLED"}, "EXTENDED": {"EXTENDED", "SUCCESSFUL", "UNSUCCESSFUL", "CANCELLED"}}
    if payload.status not in allowed.get(item.status, set()):
        fail("Invalid PIP transition", 409)
    if payload.status == "EXTENDED" and (not payload.end_date or payload.end_date <= item.end_date):
        fail("Extension must increase the end date")
    if payload.status in ("SUCCESSFUL", "UNSUCCESSFUL") and not payload.outcome:
        fail("Record an outcome before closing the PIP")
    old = row(item)
    version(item, payload.version)
    item.status = payload.status
    if payload.end_date:
        if payload.status != "EXTENDED":
            fail("End dates only change through an extension")
        item.end_date = payload.end_date
    item.details = {**item.details, "reason_for_change": payload.reason, "outcome": payload.outcome, "approved_by": str(user.id), "approved_at": now().isoformat()}
    await event(session, user, item, "pip_updated", {"old": old, "new": row(item), "reason": payload.reason}, item.appraisal_id)
    if item.status in ("ACTIVE", "EXTENDED"):
        await notify(session, user, item.company_id, [item.employee_id, item.manager_id], f"pip:{item.id}:{item.version}", f"Performance improvement plan {item.status.lower()}", item.appraisal_id)
    return row(item)


async def pip_review(session, user, identity, payload):
    await require_permission(session, user, "performance.manage_pip")
    item = await get(session, user, PerformancePIP, identity, True)
    if item.status not in ("ACTIVE", "EXTENDED"):
        fail("Only active PIPs can receive reviews", 409)
    if payload.meeting_date < item.start_date or payload.meeting_date > item.end_date:
        fail("PIP review date must be within the plan period")
    review = PerformancePIPReview(**base(user, item.company_id), pip_id=item.id, recorded_by=user.id,
        meeting_date=payload.meeting_date, details=dump(payload))
    session.add(review)
    await session.flush()
    await event(session, user, item, "pip_review_recorded", dump(payload), item.appraisal_id)
    return row(review)


async def dashboard(session, user, company_id, cycle_id=None):
    await require_permission(session, user, "performance.view_reports")
    await company_for_tenant(session, company_id, user.tenant_id)
    query = select(Appraisal, PerformanceParticipant, PerformanceCycle).join(PerformanceParticipant, Appraisal.participant_id == PerformanceParticipant.id).join(PerformanceCycle, PerformanceParticipant.cycle_id == PerformanceCycle.id).where(Appraisal.company_id == company_id, Appraisal.tenant_id == user.tenant_id)
    if cycle_id:
        cycle = await get(session, user, PerformanceCycle, cycle_id)
        if cycle.company_id != company_id:
            fail("Cycle belongs to another company", 404)
        query = query.where(PerformanceCycle.id == cycle_id)
    records = (await session.execute(query)).all()
    items = [{"appraisal_id": str(appraisal.id), "cycle": cycle.name, "employee_id": str(participant.employee_id), **participant.context,
        "status": appraisal.status, "self_submitted": bool(appraisal.self_assessment.get("submitted_at")),
        "manager_submitted": bool(appraisal.manager_assessment.get("submitted_at")), "review_completed": bool(appraisal.review),
        "calibration_completed": bool(appraisal.scores.get("calibrated_at")), "calibration_required": cycle.config["require_calibration"],
        "finalized": bool(appraisal.finalized_at), "score": appraisal.scores.get("final"), "rating": appraisal.scores.get("final_rating"),
        "recommend_pip": appraisal.scores.get("recommend_pip", False), "recommend_development": appraisal.scores.get("recommend_development", False)} for appraisal, participant, cycle in records]
    ids = [appraisal.id for appraisal, _, _ in records]
    goals = list((await session.scalars(select(PerformanceGoal).where(PerformanceGoal.appraisal_id.in_(ids)))).all())
    actions = list((await session.scalars(select(DevelopmentAction).where(DevelopmentAction.appraisal_id.in_(ids)))).all())
    pips = list((await session.scalars(select(PerformancePIP).where(PerformancePIP.company_id == company_id, PerformancePIP.tenant_id == user.tenant_id))).all())
    scores = [Decimal(item["score"]) for item in items if item["score"] is not None]
    distribution, departments, branches, managers, competencies = {}, {}, {}, {}, {}
    for appraisal, participant, cycle in records:
        if appraisal.finalized_at:
            label = appraisal.scores["final_rating"]
            distribution[label] = distribution.get(label, 0) + 1
        for grouping, label in ((departments, participant.context["department_name"]), (branches, participant.context["branch_name"]), (managers, participant.context["manager_name"])):
            stats = grouping.setdefault(label or "Unassigned", {"participants": 0, "finalized": 0, "scores": []})
            stats["participants"] += 1
            if appraisal.finalized_at:
                stats["finalized"] += 1
                stats["scores"].append(Decimal(appraisal.scores["final"]))
        for rating in appraisal.manager_assessment.get("competencies", []):
            name = next((item["name"] for item in appraisal.competencies if item["id"] == rating["id"]), "Unknown")
            competencies.setdefault(name, []).append(Decimal(rating["rating"]))
    for grouping in (departments, branches, managers):
        for stats in grouping.values():
            values = stats.pop("scores")
            stats["average"] = str((sum(values) / len(values)).quantize(Decimal("0.01"))) if values else None
    return {"participants": len(items), "goals_completed": sum(goal.status == "COMPLETED" for goal in goals),
        "self_completed": sum(item["self_submitted"] for item in items), "manager_completed": sum(item["manager_submitted"] for item in items),
        "reviews_pending": sum(not item["review_completed"] for item in items),
        "calibration_pending": sum(item["calibration_required"] and not item["calibration_completed"] for item in items),
        "finalized": sum(item["finalized"] for item in items), "average_score": str((sum(scores) / len(scores)).quantize(Decimal("0.01"))) if scores else None,
        "active_pips": sum(item.status in ("ACTIVE", "EXTENDED") for item in pips),
        "overdue_development": sum(item.due_date < date.today() and item.status not in ("COMPLETED", "CANCELLED") for item in actions),
        "rating_distribution": distribution, "departments": departments, "branches": branches, "managers": managers,
        "competency_gaps": {name: str((sum(values) / len(values)).quantize(Decimal("0.01"))) for name, values in competencies.items()},
        "goal_achievement": [{"title": goal.title, "progress": str(goal.progress), "actual": str(goal.actual) if goal.actual is not None else None, "status": goal.status} for goal in goals],
        "development_progress": [row(action) for action in actions], "pip_status": [{"id": str(item.id), "employee_id": str(item.employee_id), "status": item.status, "end_date": str(item.end_date)} for item in pips], "records": items}


async def reminders(session, user, company_id):
    await require_permission(session, user, "performance.manage_cycles")
    await company_for_tenant(session, company_id, user.tenant_id)
    # Serialize reminders with workflows and concurrent reminder invocations.
    await session.scalar(select(Company).where(Company.id == company_id).with_for_update())
    before = len((await session.scalars(select(PerformanceNotification.id).where(PerformanceNotification.company_id == company_id))).all())
    records = (await session.execute(select(Appraisal, PerformanceParticipant, PerformanceCycle).join(PerformanceParticipant, Appraisal.participant_id == PerformanceParticipant.id).join(PerformanceCycle, PerformanceCycle.id == PerformanceParticipant.cycle_id).where(Appraisal.company_id == company_id, Appraisal.tenant_id == user.tenant_id))).all()
    for appraisal, participant, cycle in records:
        if appraisal.finalized_at:
            continue
        for stage, employee_id, assessment in (("SELF_ASSESSMENT", participant.employee_id, appraisal.self_assessment), ("MANAGER_ASSESSMENT", participant.manager_id, appraisal.manager_assessment)):
            dates = cycle.windows.get(stage)
            if dates and not assessment.get("submitted_at") and cycle.status == stage:
                deadline = date.fromisoformat(dates["end"])
                if deadline - timedelta(days=3) <= date.today():
                    await notify(session, user, company_id, [employee_id], f"deadline:{appraisal.id}:{stage}:{deadline}", f"{stage.replace('_', ' ').title()} due {deadline}", appraisal.id)
    for action in (await session.scalars(select(DevelopmentAction).where(DevelopmentAction.company_id == company_id, DevelopmentAction.tenant_id == user.tenant_id, DevelopmentAction.status.notin_(["COMPLETED", "CANCELLED"]), DevelopmentAction.due_date <= date.today() + timedelta(days=3)))).all():
        await notify(session, user, company_id, [action.owner_id], f"action-due:{action.id}:{action.due_date}", f"Development action due {action.due_date}: {action.title}", action.appraisal_id)
    for pip in (await session.scalars(select(PerformancePIP).where(PerformancePIP.company_id == company_id, PerformancePIP.tenant_id == user.tenant_id, PerformancePIP.status.in_(["ACTIVE", "EXTENDED"])))).all():
        last = await session.scalar(select(PerformancePIPReview).where(PerformancePIPReview.pip_id == pip.id).order_by(PerformancePIPReview.meeting_date.desc()).limit(1))
        due = date.fromisoformat(last.details["next_review"]) if last and last.details.get("next_review") else (last.meeting_date if last else pip.start_date) + timedelta(days=pip.details["review_frequency_days"])
        if due - timedelta(days=3) <= date.today():
            await notify(session, user, company_id, [pip.manager_id], f"pip-due:{pip.id}:{due}", f"PIP review due {due}", pip.appraisal_id)
    await session.flush()
    after = len((await session.scalars(select(PerformanceNotification.id).where(PerformanceNotification.company_id == company_id))).all())
    return {"notifications_created": after - before}



async def review_action(session, user, identity, payload):
    """Task-based controls reuse the existing gates and immutable history."""
    await require_permission(session, user, "performance.manage_cycles")
    cycle = await get(session, user, PerformanceCycle, identity, True)
    if cycle.version != payload.version:
        fail("This review changed. Refresh and try again", 409)
    targets = {"START": "GOAL_SETTING", "TRACK": "ACTIVE", "SELF_REVIEW": "SELF_ASSESSMENT", "MANAGER_REVIEW": "MANAGER_ASSESSMENT", "DISCUSSION": "REVIEW", "RESULTS": "FINALIZATION", "CLOSE": "COMPLETED"}
    target = targets.get(payload.status)
    if payload.status == "RESULTS" and cycle.status == "REVIEW" and cycle.config["require_calibration"]:
        target = "CALIBRATION"
    stages = [stage for stage in STAGES if stage != "CALIBRATION" or cycle.config["require_calibration"]]
    if not target or stages.index(target) <= stages.index(cycle.status):
        fail("This review action is unavailable", 409)
    if target == "SELF_ASSESSMENT":
        if "SELF_ASSESSMENT" not in cycle.windows:
            fail("Set the self-review start and end dates first")
        window(cycle, "SELF_ASSESSMENT")
    while cycle.status != target:
        next_stage = stages[stages.index(cycle.status) + 1]
        from app.schemas.performance import TransitionInput
        await transition_cycle(session, user, identity, TransitionInput(version=cycle.version, status=next_stage, reason=payload.reason))
    return row(cycle)
