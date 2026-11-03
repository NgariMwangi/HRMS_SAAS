"""Shared synthetic performance helpers for the existing East Africa Demo tenant.

Run from backend: .venv/Scripts/python.exe -m app.db.seed_performance_demo
The CLI now creates simple reviews and replaces only the earlier demo stage examples.
Never runs at server startup; preserves real employees and unrelated reviews.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from app.api.org import ensure_document_categories
from app.core.security import hash_password
from app.db.session import dispose_engine, get_session_maker
from app.models import Branch, Company, Department, DocumentCategory, Employee, EmployeeDocument, EmployeeSupervisor, JobTitle, Tenant, User
from app.models.performance import Appraisal, Competency, GoalEvidence, PerformanceCycle, PerformanceGoal, PerformanceSettings, RatingScale
from app.schemas import performance as schema
from app.services import performance as service
from app.services.access import ensure_system_roles

DEMO_PASSWORD = "PerformanceDemo12!"
PREFIX = "DEMO · "
LEVELS = [
    {"value": "1", "label": "Unsatisfactory", "minimum": "1", "maximum": "1.99"},
    {"value": "2", "label": "Needs Improvement", "minimum": "2", "maximum": "2.99"},
    {"value": "3", "label": "Meets Expectations", "minimum": "3", "maximum": "3.99"},
    {"value": "4", "label": "Exceeds Expectations", "minimum": "4", "maximum": "4.49"},
    {"value": "5", "label": "Outstanding", "minimum": "4.50", "maximum": "5"},
]
STAGES = service.STAGES
PROFILES = [("Amina", "4.70", "4.80"), ("Brian", "3.40", "3.60"), ("Carol", "2.30", "2.70"), ("David", "4.20", "3.80")]
GOALS = [
    ("Deliver planned assignments", "NUMBER", "HIGHER_IS_BETTER", "100", "assignments", 40),
    ("Maintain service quality", "PERCENTAGE", "HIGHER_IS_BETTER", "95", "%", 20),
    ("Reduce rework and errors", "NUMBER", "LOWER_IS_BETTER", "5", "errors", 15),
    ("Complete professional training", "MILESTONE", "MILESTONE", "1", "course", 15),
    ("Improve team knowledge sharing", "QUALITATIVE", "HIGHER_IS_BETTER", None, "peer feedback", 10),
]


async def identity(session, company, branches, index, first, role):
    """Only create/reuse namespaced synthetic records, with stable company-specific emails."""
    company_tag = {"Rift Valley Trading Ltd": "rift", "Nile Logistics Ltd": "nile", "Coastal Packers Ltd": "coastal"}.get(company.name, str(company.id)[:8])
    email = f"performance.{first.lower()}@{company_tag}-demo.example"
    existing = await session.scalar(select(User).where(User.email == email))
    if existing:
        if existing.tenant_id != company.tenant_id or existing.role != role or not existing.employee_id:
            raise RuntimeError(f"Demo login collision: {email}")
        employee = await session.get(Employee, existing.employee_id)
        if employee is None or employee.company_id != company.id:
            raise RuntimeError(f"Demo employee collision: {email}")
        return employee, existing
    department_name = PREFIX + ("Service delivery" if index % 2 == 0 else "Business support")
    department = await session.scalar(select(Department).where(Department.company_id == company.id, Department.name == department_name))
    if department is None:
        department = Department(company_id=company.id, name=department_name, description="Synthetic performance walkthrough department")
        session.add(department)
        await session.flush()
    title_name = PREFIX + ("Team manager" if role == "MANAGER" else "HR coordinator" if role == "HR" else "Service specialist")
    title = await session.scalar(select(JobTitle).where(JobTitle.company_id == company.id, JobTitle.name == title_name))
    if title is None:
        title = JobTitle(company_id=company.id, name=title_name)
        session.add(title)
        await session.flush()
    employee = Employee(company_id=company.id, branch_id=branches[index % len(branches)].id,
                        department_id=department.id, job_title_id=title.id,
                        employee_number=f"PERF-DEMO-{index + 1:02}", first_name=first, last_name="Demo",
                        email=email, date_joined=date(2025, 1, 15), employment_type="FULL_TIME", status="ACTIVE")
    session.add(employee)
    await session.flush()
    user = User(tenant_id=company.tenant_id, employee_id=employee.id, email=email,
                full_name=f"{first} Demo", role=role, status="ACTIVE", password_hash=hash_password(DEMO_PASSWORD))
    session.add(user)
    await session.flush()
    return employee, user


async def evidence(session, actor, employee, goal, appraisal_id, label):
    category = await session.scalar(select(DocumentCategory).where(DocumentCategory.company_id == employee.company_id, DocumentCategory.name == "Work related"))
    if category is None:
        category = DocumentCategory(company_id=employee.company_id, name="Work related", locked=False, sort_order=40)
        session.add(category)
        await session.flush()
    filename = f"demo-{label}-{employee.first_name.lower()}-evidence.txt"
    document = EmployeeDocument(company_id=employee.company_id, employee_id=employee.id, category_id=category.id,
        filename=filename, content_type="text/plain", file_bytes=(
            "SYNTHETIC DEMONSTRATION DATA — not a real employee performance record.\n"
            f"Employee: {employee.first_name} Demo\nGoal: {goal['title']}\n"
            "Evidence: sample assignment register, quality checklist and peer feedback.\n"
            "Use the progress history to compare the initial update with the latest achievement.\n").encode(),
        uploaded_by=actor.id, note="DEMO performance evidence")
    session.add(document)
    await session.flush()
    session.add(GoalEvidence(**service.base(actor, employee.company_id), goal_id=uuid.UUID(goal["id"]), document_id=document.id))
    await session.flush()
    await service.event(session, actor, await session.get(PerformanceGoal, uuid.UUID(goal["id"])), "evidence_uploaded", {"document_id": str(document.id), "filename": filename}, appraisal_id)


async def cycle_demo(session, owner, company, manager, hr, staff, stage, start, end, label, today, review_mode=False):
    name = f"{PREFIX}{label} · {stage.replace('_', ' ').title()}"
    if review_mode:
        name = f"{PREFIX}{today.year} ? {'Current performance review' if stage == 'ACTIVE' else 'Completed performance review'}"
    existing = await session.scalar(select(PerformanceCycle).where(PerformanceCycle.company_id == company.id, PerformanceCycle.name == name))
    if existing:
        return False
    windows = {stage: schema.Window(start=today - timedelta(days=3), end=today + timedelta(days=2))} if stage in ("SELF_ASSESSMENT", "MANAGER_ASSESSMENT") else {}
    if review_mode:
        windows = {"SELF_ASSESSMENT": schema.Window(start=today + timedelta(days=7) if stage == "ACTIVE" else today - timedelta(days=3), end=today + timedelta(days=21) if stage == "ACTIVE" else today + timedelta(days=2))}
    created = await service.create_cycle(session, owner, company.id, schema.CycleInput(name=name, frequency="CUSTOM", start_date=start, end_date=end, windows=windows, goal_entry_roles=["HR", "MANAGER"] if review_mode else None))
    cycle_id = uuid.UUID(created["id"])
    participants = await service.assign_participants(session, owner, cycle_id, schema.ParticipantInput(employee_ids=[employee.id for employee, _ in staff], manager_id=manager[0].id))
    records = {uuid.UUID(p["employee_id"]): uuid.UUID(p["appraisal_id"]) for p in participants}

    async def advance(next_stage):
        cycle = await session.get(PerformanceCycle, cycle_id)
        await service.transition_cycle(session, owner, cycle_id, schema.TransitionInput(version=cycle.version, status=next_stage))

    async def version(appraisal_id):
        return (await session.get(Appraisal, appraisal_id)).version

    if stage == "DRAFT":
        return True
    await advance("GOAL_SETTING")
    goal_sets = {}
    for index, (employee, actor) in enumerate(staff):
        appraisal_id = records[employee.id]
        goals = []
        for goal_index, (title, measurement, direction, target, unit, weight) in enumerate(GOALS):
            goal = await service.create_goal(session, hr[1] if review_mode else actor, appraisal_id, schema.GoalInput(
                title=title, description=f"DEMO: measurable contribution to {company.name}. Agree scope and evidence with your manager.",
                measurement=measurement, direction=direction, target=target, unit=unit,
                weight=weight, start_date=start, due_date=end, priority="HIGH" if goal_index == 0 else "NORMAL"))
            goal = await service.goal_action(session, hr[1] if review_mode else actor, uuid.UUID(goal["id"]), "submit", schema.TransitionInput(version=goal["version"], status=""))
            if stage != "GOAL_SETTING" or index != 0 or goal_index < 3:
                goal = await service.goal_action(session, manager[1], uuid.UUID(goal["id"]), "approve", schema.TransitionInput(version=goal["version"], status=""))
            if stage == "GOAL_SETTING" and index == 1 and goal_index == 1:
                # A separate revision goal demonstrates requested changes without affecting completed cycles.
                extra = await service.create_goal(session, actor, appraisal_id, schema.GoalInput(title="DEMO draft: clarify customer feedback target", weight=0, target=10, start_date=start, due_date=end))
                extra = await service.goal_action(session, actor, uuid.UUID(extra["id"]), "submit", schema.TransitionInput(version=extra["version"], status=""))
                await service.goal_action(session, manager[1], uuid.UUID(extra["id"]), "request-changes", schema.TransitionInput(version=extra["version"], status="", reason="Specify the sample size and how feedback will be collected."))
            goals.append(goal)
        goal_sets[employee.id] = goals
    if stage == "GOAL_SETTING":
        return True
    await advance("ACTIVE")
    for index, (employee, actor) in enumerate(staff):
        appraisal_id = records[employee.id]
        for goal_index, goal in enumerate(goal_sets[employee.id]):
            first = await service.add_progress(session, actor, uuid.UUID(goal["id"]), schema.ProgressInput(version=goal["version"], progress=25, actual=25 if goal_index < 2 else None, comment="DEMO first check-in: initial progress recorded.", achievements="Completed initial work plan"))
            progress = (85, 65, 40, 100)[index] if stage == "ACTIVE" else (100, 90, 55, 100)[index]
            actual = (110, 95, 65, 105)[index] if goal_index == 0 else (98, 95, 80, 97)[index] if goal_index == 1 else (2, 5, 12, 3)[index] if goal_index == 2 else None
            latest = await service.add_progress(session, actor, uuid.UUID(goal["id"]), schema.ProgressInput(version=first["version"], progress=progress, actual=actual, comment="DEMO follow-up: updated achievement and supporting evidence.", blockers="Rework needs coaching" if index == 2 else "", achievements="Updated delivery register and reviewed quality results"))
            goal_sets[employee.id][goal_index] = latest
        await evidence(session, actor, employee, goal_sets[employee.id][0], appraisal_id, label.lower().replace(" ", "-"))
        await service.add_check_in(session, manager[1], appraisal_id, schema.CheckInInput(kind="MONTHLY", meeting_date=min(today, start + (end - start) // 2),
            achievements="Assignment register reviewed; strong customer feedback captured.", challenges="Improve consistency of quality checks" if index == 2 else "Balance delivery and training time",
            employee_comments="I would benefit from more structured feedback.", manager_feedback="Continue weekly check-ins and share evidence against each target.",
            agreed_actions="Review progress weekly; complete the agreed training module.", goal_ids=[uuid.UUID(goal["id"]) for goal in goal_sets[employee.id]]))
    if stage == "ACTIVE":
        return True
    await advance("SELF_ASSESSMENT")

    async def assessment_payload(employee, own):
        appraisal_id = records[employee.id]
        appraisal = await session.get(Appraisal, appraisal_id)
        index = next(i for i, (person, _) in enumerate(staff) if person.id == employee.id)
        rating = Decimal(PROFILES[index][1]) + (Decimal("0.20") if own else Decimal("0"))
        return schema.AssessmentInput(version=appraisal.version,
            goals=[schema.ItemRating(id=goal["id"], rating=rating, comment="DEMO employee reflection" if own else "DEMO assessment supported by delivery records") for goal in goal_sets[employee.id]],
            competencies=[schema.ItemRating(id=competency["id"], rating=PROFILES[index][2], comment="Peer feedback and check-in observations reviewed") for competency in appraisal.competencies],
            summary="I achieved most agreed objectives and identified practical development needs." if own else "Independent review of results, evidence and demonstrated behaviours.",
            achievements="Delivered assignments and shared learning with colleagues.", challenges="Maintaining consistent quality under time pressure.",
            support="Coaching, access to training and regular manager feedback.", career_interests="Develop specialist and team leadership skills.", recommendations="Complete the agreed development actions.")

    for index, (employee, actor) in enumerate(staff):
        await service.assessment(session, actor, records[employee.id], "self", await assessment_payload(employee, True), submit=stage != "SELF_ASSESSMENT" or index == 0)
    if stage == "SELF_ASSESSMENT":
        return True
    await advance("MANAGER_ASSESSMENT")
    for index, (employee, _) in enumerate(staff):
        await service.assessment(session, manager[1], records[employee.id], "manager", await assessment_payload(employee, False), submit=stage != "MANAGER_ASSESSMENT" or index == 0)
    if stage == "MANAGER_ASSESSMENT":
        return True
    await advance("REVIEW")
    for index, (employee, _) in enumerate(staff):
        if stage == "REVIEW" and index > 0:
            continue
        await service.review(session, manager[1], records[employee.id], schema.ReviewInput(version=await version(records[employee.id]), meeting_date=end,
            attendees=[f"{employee.first_name} Demo", "Morgan Demo"], summary="DEMO review: discussed results, feedback and development priorities.",
            employee_comments="I received the feedback and shared my perspective.", manager_comments="Ratings reflect the evidence and agreed targets.",
            achievements="Completed major delivery priorities.", improvements="Strengthen planning and quality assurance.", agreed_actions="Follow the documented development plan."))
    if stage == "REVIEW":
        return True
    if (await session.get(PerformanceCycle, cycle_id)).config["require_calibration"]:
        await advance("CALIBRATION")
        for index, (employee, _) in enumerate(staff):
            if stage == "CALIBRATION" and index > 0:
                continue
            appraisal = await session.get(Appraisal, records[employee.id])
            await service.calibrate(session, hr[1], appraisal.id, schema.CalibrationInput(version=appraisal.version, score=appraisal.scores["pre_calibration"], reason="DEMO calibration: compared evidence and rating standards across departments; original rating retained."))
        if stage == "CALIBRATION":
            return True
    await advance("FINALIZATION")
    if review_mode and stage == "COMPLETED":
        historical = await session.get(PerformanceCycle, cycle_id)
        await service.update_cycle(session, owner, cycle_id, schema.CycleUpdate(
            name=historical.name, frequency=historical.frequency, start_date=start, end_date=end,
            windows={"SELF_ASSESSMENT": schema.Window(start=end + timedelta(days=1), end=end + timedelta(days=14))},
            version=historical.version, reason="DEMO: record the historical self-review dates for the completed example"))
    for index, (employee, actor) in enumerate(staff):
        if stage == "FINALIZATION" and index == 3:
            continue
        await service.acknowledge(session, actor, records[employee.id], schema.AcknowledgeInput(version=await version(records[employee.id]), status="DISAGREES" if index == 2 else "ACKNOWLEDGED_WITH_COMMENTS", comments="DEMO: received the review; I would like more discussion of the quality rating." if index == 2 else "DEMO: feedback received and development actions understood."))
        if stage == "COMPLETED" or index == 0:
            await service.finalize(session, hr[1], records[employee.id], schema.VersionInput(version=await version(records[employee.id])))
    if stage == "COMPLETED":
        await advance("COMPLETED")
        for index, (employee, _) in enumerate(staff):
            action = await service.development_create(session, manager[1], records[employee.id], schema.DevelopmentInput(title=f"DEMO · {employee.first_name}: quality and planning workshop", owner_id=employee.id,
                due_date=end + timedelta(days=45) if index == 2 else today + timedelta(days=30), area="Service quality", skill_gap="Consistent quality checks",
                desired_outcome="Apply the checklist independently and reduce rework.", action="Complete training, shadow a senior colleague, and review three work samples with the manager.", priority="HIGH" if index == 2 else "NORMAL"))
            if index in (0, 1, 2):
                await service.development_update(session, manager[1], uuid.UUID(action["id"]), schema.DevelopmentUpdate(version=action["version"], status="COMPLETED" if index == 0 else "IN_PROGRESS", progress=100 if index == 0 else 60 if index == 1 else 20, comments="DEMO: learning evidence reviewed at follow-up."))
        employee = staff[2][0]
        for closed in (False, True):
            pip_start = end + timedelta(days=1) if closed else today - timedelta(days=21)
            pip = await service.pip_create(session, hr[1], company.id, schema.PIPInput(employee_id=employee.id, manager_id=manager[0].id, hr_owner_id=hr[1].id, appraisal_id=records[employee.id],
                start_date=pip_start, end_date=pip_start + timedelta(days=60), reason="DEMO: improvement support after the quality review" + (" (completed example)" if closed else " (active example)"),
                issues="Repeated rework and missed quality checks in the synthetic example.", support="Weekly coaching, job aids and protected training time.", review_frequency_days=14,
                objectives=[schema.PIPObjective(title="Reduce rework", target="At most 5 reworked assignments", expected_standard="Use the checklist for every assignment"), schema.PIPObjective(title="Meet delivery deadlines", target="95% delivered on time", expected_standard="Plan and review work weekly")]))
            pip = await service.pip_update(session, hr[1], uuid.UUID(pip["id"]), schema.PIPUpdate(version=pip["version"], status="ACTIVE", reason="DEMO support plan agreed by HR and the assigned manager."))
            await service.pip_review(session, hr[1], uuid.UUID(pip["id"]), schema.PIPReviewInput(meeting_date=pip_start + timedelta(days=14), notes="DEMO: checklist use improved; continue coaching on complex cases.", objective_progress=["Rework reduced from 12 to 7 assignments", "On-time delivery improved to 90%"], next_review=pip_start + timedelta(days=28)))
            if closed:
                await service.pip_update(session, hr[1], uuid.UUID(pip["id"]), schema.PIPUpdate(version=pip["version"], status="SUCCESSFUL", reason="DEMO final review completed.", outcome="Targets met consistently during the final review period; continue routine coaching."))
    return True


async def seed_company(session, owner, company, stages, today, review_mode=False):
    await session.scalar(select(Company).where(Company.id == company.id).with_for_update())
    branches = list((await session.scalars(select(Branch).where(Branch.company_id == company.id, Branch.status == "ACTIVE").order_by(Branch.name))).all())
    if not branches:
        raise RuntimeError(f"No active branch in {company.name}")
    await ensure_system_roles(session, company.tenant_id)
    await ensure_document_categories(session, company.id)
    manager = await identity(session, company, branches, 0, "Morgan", "MANAGER")
    hr = await identity(session, company, branches, 1, "Helena", "HR")
    staff = [await identity(session, company, branches, i + 2, first, "EMPLOYEE") for i, (first, _, _) in enumerate(PROFILES)]
    for employee, _ in staff:
        if not await session.scalar(select(EmployeeSupervisor.id).where(EmployeeSupervisor.employee_id == employee.id, EmployeeSupervisor.supervisor_id == manager[0].id)):
            session.add(EmployeeSupervisor(company_id=company.id, employee_id=employee.id, supervisor_id=manager[0].id, sort_order=0))
    await session.flush()
    scale = await session.scalar(select(RatingScale).where(RatingScale.company_id == company.id, RatingScale.name == PREFIX + "Five-point scale"))
    if scale is None:
        scale_row = await service.create_catalog(session, owner, company.id, schema.ScaleInput(name=PREFIX + "Five-point scale", levels=LEVELS), RatingScale)
        scale = await session.get(RatingScale, uuid.UUID(scale_row["id"]))
    for name, description, indicators in [
        ("Quality and accountability", "Demonstrates reliable work and follows through on commitments.", ["Checks work before delivery", "Owns and corrects mistakes"]),
        ("Communication and teamwork", "Shares information clearly and supports colleagues.", ["Communicates progress early", "Shares useful knowledge"]),
        ("Learning and adaptability", "Applies feedback and develops new skills.", ["Uses feedback constructively", "Applies training to daily work"]),
    ]:
        if not await session.scalar(select(Competency.id).where(Competency.company_id == company.id, Competency.name == PREFIX + name)):
            await service.create_catalog(session, owner, company.id, schema.CompetencyInput(name=PREFIX + name, description=description, indicators=indicators, employee_ids=[employee.id for employee, _ in staff]), Competency)
    settings = await session.scalar(select(PerformanceSettings).where(PerformanceSettings.company_id == company.id))
    previous_config = dict(settings.config) if settings else None
    demo_config = schema.SettingsInput(frequency="QUARTERLY", rating_scale_id=scale.id, require_calibration=not review_mode,
        employee_view_calibration=True, development_threshold="3.50", pip_threshold="3.00")
    if settings is None:
        await service.save_settings(session, owner, company.id, demo_config)
    else:
        # Within the transaction only: each demo cycle snapshots its own configuration.
        settings.config = service.dump(demo_config)
        await session.flush()
    created = 0
    for stage in stages:
        if stage == "COMPLETED":
            start, end, label = today - timedelta(days=180), today - timedelta(days=90), f"{today.year} completed review"
        elif stage in ("DRAFT", "GOAL_SETTING", "ACTIVE"):
            start, end, label = today - timedelta(days=5), today + timedelta(days=85), f"{today.year} walkthrough"
        else:
            start, end, label = today - timedelta(days=95), today - timedelta(days=5), f"{today.year} walkthrough"
        created += await cycle_demo(session, owner, company, manager, hr, staff, stage, start, end, label, today, review_mode=review_mode)
    if previous_config is not None:
        settings.config = previous_config
        await session.flush()
    await service.reminders(session, owner, company.id)
    return {"company": company.name, "cycles_created": created, "manager": manager[1].email, "hr": hr[1].email, "employee": staff[0][1].email}


async def seed_performance_demo(session, today=None):
    owner = await session.scalar(select(User).where(User.email == "demo@example.com", User.role == "OWNER", User.status == "ACTIVE"))
    if owner is None:
        raise RuntimeError("The existing demo workspace is required. Run app.db.seed_demo first.")
    tenant = await session.get(Tenant, owner.tenant_id)
    if tenant is None or tenant.name != "East Africa Demo" or tenant.status != "ACTIVE":
        raise RuntimeError("Refusing to seed outside the active East Africa Demo workspace")
    await session.execute(text("SELECT set_config('app.current_tenant_id', :tid, true)"), {"tid": str(owner.tenant_id)})
    companies = list((await session.scalars(select(Company).where(Company.tenant_id == owner.tenant_id, Company.status == "ACTIVE").order_by(Company.name))).all())
    result = []
    for company in companies:
        stages = STAGES if company.name == "Rift Valley Trading Ltd" else ["ACTIVE", "MANAGER_ASSESSMENT", "COMPLETED"]
        result.append(await seed_company(session, owner, company, stages, today or datetime.now(ZoneInfo("Africa/Nairobi")).date()))
    return result


async def main():
    try:
        async with get_session_maker()() as session:
            from app.db.seed_performance_reviews import seed_review_demo
            result = await seed_review_demo(session)
            await session.commit()
        for company in result:
            print(f"{company['company']}: {company['cycles_created']} demo reviews added")
            print(f"  Manager: {company['manager']}\n  HR: {company['hr']}\n  Employee: {company['employee']}")
        print(f"New demo-account password: {DEMO_PASSWORD}")
        print("Existing logins, employee records and performance configuration were preserved.")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
