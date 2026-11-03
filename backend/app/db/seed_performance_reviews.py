"""Replace only the old, namespaced performance walkthroughs in East Africa Demo.

Run: python -m app.db.seed_performance_reviews
The replacement and seeding commit together; repeated runs preserve the new reviews.
"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, text

from app.db.seed_performance_demo import PREFIX, STAGES, seed_company
from app.db.session import dispose_engine, get_session_maker
from app.models import Company, Employee, EmployeeDocument, Tenant, User
from app.models.performance import (Appraisal, GoalEvidence, PerformanceCycle,
    PerformanceEvent, PerformanceGoal, PerformanceParticipant, PerformancePIP)


async def seed_review_demo(session, today=None):
    owner = await session.scalar(select(User).where(User.email == "demo@example.com", User.role == "OWNER", User.status == "ACTIVE"))
    tenant = await session.get(Tenant, owner.tenant_id) if owner else None
    if tenant is None or tenant.name != "East Africa Demo" or tenant.status != "ACTIVE":
        raise RuntimeError("Refusing to replace examples outside East Africa Demo")
    await session.execute(text("SELECT set_config('app.current_tenant_id', :tid, true)"), {"tid": str(tenant.id)})
    companies = list((await session.scalars(select(Company).where(Company.tenant_id == tenant.id, Company.status == "ACTIVE").order_by(Company.name).with_for_update())).all())
    result = []
    today = today or datetime.now(ZoneInfo("Africa/Nairobi")).date()
    for company in companies:
        candidates = list((await session.scalars(select(PerformanceCycle).where(PerformanceCycle.tenant_id == tenant.id, PerformanceCycle.company_id == company.id))).all())
        legacy = []
        for review in candidates:
            # Match exactly the old seeder's name format, across seed years.
            if not review.name.startswith(PREFIX):
                continue
            suffix = review.name[len(PREFIX):]
            year = suffix[:4]
            expected = {f"{year} {'completed review' if stage == 'COMPLETED' else 'walkthrough'} · {stage.replace('_', ' ').title()}" for stage in STAGES}
            if year.isdigit() and suffix in expected:
                participants = list((await session.scalars(select(PerformanceParticipant).where(PerformanceParticipant.cycle_id == review.id))).all())
                for participant in participants:
                    employee = await session.get(Employee, participant.employee_id)
                    if employee is None or employee.company_id != company.id or employee.last_name != "Demo" or not (employee.employee_number or "").startswith("PERF-DEMO-"):
                        raise RuntimeError(f"Review {review.name} contains non-demo participants; replacement stopped")
                legacy.append(review.id)
        removed = len(legacy)
        if legacy:
            appraisal_ids = list((await session.scalars(select(Appraisal.id).join(PerformanceParticipant, Appraisal.participant_id == PerformanceParticipant.id).where(PerformanceParticipant.cycle_id.in_(legacy)))).all())
            goal_ids = list((await session.scalars(select(PerformanceGoal.id).where(PerformanceGoal.appraisal_id.in_(appraisal_ids)))).all())
            documents = list((await session.scalars(select(EmployeeDocument).join(GoalEvidence, GoalEvidence.document_id == EmployeeDocument.id).where(GoalEvidence.goal_id.in_(goal_ids)))).all())
            # PIPs use SET NULL, so explicitly remove the seeded examples before reviews.
            pips = list((await session.scalars(select(PerformancePIP).where(PerformancePIP.appraisal_id.in_(appraisal_ids)))).all())
            for pip in pips:
                if not pip.details.get("reason", "").startswith("DEMO:"):
                    raise RuntimeError("A non-demo PIP references an old walkthrough; replacement stopped")
                await session.delete(pip)
            await session.flush()
            await session.execute(delete(PerformanceCycle).where(PerformanceCycle.tenant_id == tenant.id, PerformanceCycle.company_id == company.id, PerformanceCycle.id.in_(legacy)))
            await session.execute(delete(PerformanceEvent).where(PerformanceEvent.tenant_id == tenant.id, PerformanceEvent.entity_id.in_(legacy)))
            for document in documents:
                if document.note == "DEMO performance evidence" and document.filename.startswith("demo-"):
                    await session.delete(document)
            await session.flush()
        summary = await seed_company(session, owner, company, ["ACTIVE", "COMPLETED"], today, review_mode=True)
        summary["old_examples_removed"] = removed
        result.append(summary)
    return result


async def main():
    try:
        async with get_session_maker()() as session:
            result = await seed_review_demo(session)
            await session.commit()
        for company in result:
            print(f"{company['company']}: removed {company['old_examples_removed']} old examples; added {company['cycles_created']} reviews")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
