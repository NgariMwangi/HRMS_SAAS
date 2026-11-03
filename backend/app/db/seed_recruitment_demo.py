"""Add fictional recruitment examples only to the existing East Africa Demo workspace.

Never deletes records or resets edited examples. Run: python -m app.db.seed_recruitment_demo
"""
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from app.api.routes import recruitment as api
from app.db.session import dispose_engine, get_session_maker
from app.models import Company, Employee, Tenant, User
from app.models.recruitment import Candidate, Vacancy
from app.schemas.recruitment import ApplyInput, CandidateInput, InterviewInput, JobInput, OfferInput, StageInput, StatusInput


async def seed_demo(session):
    owner = await session.scalar(select(User).where(User.email == "demo@example.com", User.role == "OWNER", User.status == "ACTIVE"))
    tenant = await session.get(Tenant, owner.tenant_id) if owner else None
    if not tenant or tenant.name != "East Africa Demo" or tenant.status != "ACTIVE":
        raise RuntimeError("Refusing to seed recruitment outside East Africa Demo")
    await session.execute(text("SELECT set_config('app.current_tenant_id', :tid, true)"), {"tid": str(tenant.id)})
    companies = list((await session.scalars(select(Company).where(Company.tenant_id == tenant.id, Company.status == "ACTIVE").order_by(Company.name).with_for_update())).all())
    today = datetime.now(ZoneInfo("Africa/Nairobi")).date()
    result = []
    for company in companies:
        # Company lock serializes concurrent seed runs. Existing fixtures are never rebuilt.
        existing = await session.scalar(select(Vacancy.id).where(Vacancy.company_id == company.id, Vacancy.title == "DEMO · Operations coordinator"))
        if existing:
            result.append({"company": company.name, "created": False})
            continue
        manager = await session.scalar(select(Employee).join(User, User.employee_id == Employee.id).where(
            Employee.company_id == company.id, Employee.first_name == "Morgan", Employee.last_name == "Demo",
            Employee.employee_number.like("PERF-DEMO-%"), User.tenant_id == tenant.id, User.status == "ACTIVE", User.role == "MANAGER"))
        jobs = []
        for title, description in [
            ("Operations coordinator", "DEMO: Coordinate daily assignments, maintain service standards and support the team."),
            ("Accounts assistant", "DEMO: Maintain accurate records, reconcile transactions and prepare monthly reports."),
            ("Customer support officer", "DEMO: Respond to enquiries, follow up service issues and maintain customer records."),
        ]:
            payload = JobInput(title=f"DEMO · {title}", description=description,
                requirements="DEMO: Relevant experience, clear communication and attention to detail.",
                openings=2, location="Nairobi", closing_date=today + timedelta(days=30), manager_id=manager.id if manager else None)
            created = await api.add_job(company.id, payload, session, owner)
            if len(jobs) < 2:
                await api.job_status(created["id"], StatusInput(status="OPEN"), session, owner)
            jobs.append(created)
        candidates = []
        for name in ["Zuri", "Kevin", "Faith", "Sam"]:
            email = f"recruitment.{name.lower()}.{str(company.id)[:8]}@demo.example"
            if await session.scalar(select(Candidate.id).where(Candidate.company_id == company.id, Candidate.email == email)):
                raise RuntimeError("Demo candidate collision. No records were overwritten.")
            created = await api.add_candidate(company.id, CandidateInput(first_name=name, last_name="Demo", email=email,
                source="Demo walkthrough", notes="DEMO: Fictional applicant for testing the recruitment workflow."), session, owner)
            candidates.append(created)
        applications = []
        for index, candidate in enumerate(candidates):
            job = jobs[0 if index < 2 else 1]
            applications.append(await api.apply(ApplyInput(job_id=job["id"], candidate_id=candidate["id"]), session, owner))
        await api.stage(applications[1]["id"], StageInput(stage="SHORTLISTED"), session, owner)
        if manager:
            await api.schedule(InterviewInput(application_id=applications[1]["id"], title="DEMO · Operations interview",
                starts_at=datetime.now(timezone.utc) + timedelta(days=2), location="Demo meeting room", interviewer_ids=[manager.id]), session, owner)
        await api.stage(applications[2]["id"], StageInput(stage="SHORTLISTED"), session, owner)
        offer = await api.add_offer(OfferInput(application_id=applications[2]["id"], salary="55000", currency="KES",
            start_date=today + timedelta(days=20), expires_on=today + timedelta(days=10), terms="DEMO: Monthly gross salary. Review the agreed employment terms before creating the employee record."), session, owner)
        await api.offer_status(offer["id"], StatusInput(status="ISSUED"), session, owner)
        await api.offer_status(offer["id"], StatusInput(status="ACCEPTED"), session, owner)
        await api.stage(applications[3]["id"], StageInput(stage="REJECTED", note="DEMO: Another applicant matched the requirements more closely."), session, owner)
        result.append({"company": company.name, "created": True})
    return result


async def main():
    try:
        async with get_session_maker()() as session:
            result = await seed_demo(session)
            await session.commit()
        for item in result:
            print(f"{item['company']}: {'added 3 vacancies, 4 candidates and 4 applications' if item['created'] else 'existing demo examples preserved'}")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
