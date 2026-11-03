from datetime import date
import uuid

import pytest
from sqlalchemy import func, select
from app.db.seed_performance_demo import LEVELS, seed_performance_demo
from app.db.session import get_session_maker
from app.models import Company, Employee, User
from app.models.performance import Appraisal, DevelopmentAction, GoalEvidence, GoalProgress, PerformanceCycle, PerformanceEvent, PerformanceNotification, PerformancePIP, PerformancePIPReview, PerformanceSettings, RatingScale
from app.schemas.performance import ScaleInput, SettingsInput, CycleInput
from app.services import performance as service
from tests.conftest import auth_header
from tests.test_tenancy import _kenya, _register
from tests.test_access import workspace, staff_login


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_performance_demo_full_workflows_preservation_and_idempotency(client):
    country = await _kenya()
    data = await _register(client, email="demo@example.com", tenant_name="East Africa Demo", company_name="Rift Valley Trading Ltd", country_id=country.id)
    owner_headers = auth_header(data["access_token"])
    original, _, _ = await staff_login(client, owner_headers, data, "Existing")
    other, other_headers = await workspace(client, "untouched@example.com")
    company_id = uuid.UUID(data["company"]["id"])
    async with get_session_maker()() as session:
        owner = await session.get(User, uuid.UUID(data["user"]["id"]))
        scale = await service.create_catalog(session, owner, company_id, ScaleInput(name="Existing policy", levels=LEVELS), RatingScale)
        config = await service.save_settings(session, owner, company_id, SettingsInput(rating_scale_id=scale["id"], kpi_weight=80, competency_weight=20))
        await session.commit()
    async with get_session_maker()() as session:
        result = await seed_performance_demo(session, today=date.today())
        await session.commit()
        assert result[0]["cycles_created"] == 9
        settings = await session.scalar(select(PerformanceSettings).where(PerformanceSettings.company_id == company_id))
        assert settings.config == config
        cycles = list((await session.scalars(select(PerformanceCycle).where(PerformanceCycle.company_id == company_id))).all())
        assert {cycle.status for cycle in cycles} == set(service.STAGES)
        assert all(cycle.config["kpi_weight"] == "70" and cycle.config["require_calibration"] for cycle in cycles)
        assert await session.scalar(select(func.count()).select_from(Appraisal)) == 36
        assert await session.scalar(select(func.count()).select_from(GoalProgress)) == 280
        assert await session.scalar(select(func.count()).select_from(GoalEvidence)) == 28
        assert await session.scalar(select(func.count()).select_from(DevelopmentAction)) == 4
        assert await session.scalar(select(func.count()).select_from(PerformancePIPReview)) == 2
        assert set((await session.scalars(select(PerformancePIP.status))).all()) == {"ACTIVE", "SUCCESSFUL"}
        existing = await session.get(Employee, uuid.UUID(original["id"]))
        assert existing.first_name == original["first_name"]
        owner = await session.get(User, uuid.UUID(data["user"]["id"]))
        dashboard = await service.dashboard(session, owner, company_id)
        assert dashboard["participants"] == 36 and dashboard["finalized"] == 5
        assert dashboard["active_pips"] == 1
        assert set(dashboard["rating_distribution"]) == {"Outstanding", "Meets Expectations", "Needs Improvement", "Exceeds Expectations"}
        assert any(row["score"] == "4.08" for row in dashboard["records"])
        before = {model.__tablename__: await session.scalar(select(func.count()).select_from(model)) for model in (Employee, User, Appraisal, PerformanceCycle, GoalProgress, GoalEvidence, PerformanceEvent, PerformanceNotification, PerformancePIP)}
    async with get_session_maker()() as session:
        second = await seed_performance_demo(session, today=date.today())
        await session.commit()
        assert second[0]["cycles_created"] == 0
        after = {model.__tablename__: await session.scalar(select(func.count()).select_from(model)) for model in (Employee, User, Appraisal, PerformanceCycle, GoalProgress, GoalEvidence, PerformanceEvent, PerformanceNotification, PerformancePIP)}
        assert after == before
        assert (await session.scalar(select(Company).where(Company.id == uuid.UUID(other["company"]["id"])))).name == other["company"]["name"]
    for role in ("employee", "manager", "hr"):
        login = await client.post("/auth/login", json={"email": result[0][role], "password": "PerformanceDemo12!"})
        assert login.status_code == 200, login.text
        headers = auth_header(login.json()["access_token"])
        appraisals = await client.get(f"/performance/appraisals?company_id={company_id}", headers=headers)
        assert appraisals.status_code == 200, appraisals.text
        assert len(appraisals.json()) == (9 if role == "employee" else 36)
    assert (await client.get(f"/performance/cycles?company_id={company_id}", headers=other_headers)).status_code == 403

    # Replace the old stage examples while preserving a real review and all logins.
    from app.db.seed_performance_reviews import seed_review_demo
    from zoneinfo import ZoneInfo
    from datetime import datetime
    async with get_session_maker()() as session:
        owner = await session.get(User, uuid.UUID(data["user"]["id"]))
        real = await service.create_cycle(session, owner, company_id, CycleInput(name="Actual team review", start_date="2026-01-01", end_date="2026-12-31"))
        await session.commit()
    async with get_session_maker()() as session:
        replaced = await seed_review_demo(session, today=datetime.now(ZoneInfo("Africa/Nairobi")).date())
        await session.commit()
        assert replaced[0]["old_examples_removed"] == 9
        assert replaced[0]["cycles_created"] == 2
        rows = list((await session.scalars(select(PerformanceCycle).where(PerformanceCycle.company_id == company_id))).all())
        assert len(rows) == 3
        assert await session.get(PerformanceCycle, uuid.UUID(real["id"])) is not None
        demos = [row for row in rows if row.name.startswith("DEMO")]
        assert {row.status for row in demos} == {"ACTIVE", "COMPLETED"}
        assert all(row.config["goal_entry_roles"] == ["HR", "MANAGER"] and not row.config["require_calibration"] for row in demos)
        assert all("SELF_ASSESSMENT" in row.windows for row in demos)
        assert await session.scalar(select(func.count()).select_from(Appraisal)) == 8
        assert await session.scalar(select(func.count()).select_from(GoalEvidence)) == 8
        assert await session.scalar(select(func.count()).select_from(PerformancePIP)) == 2
        settings = await session.scalar(select(PerformanceSettings).where(PerformanceSettings.company_id == company_id))
        assert settings.config == config
    async with get_session_maker()() as session:
        again = await seed_review_demo(session, today=datetime.now(ZoneInfo("Africa/Nairobi")).date())
        await session.commit()
        assert again[0]["old_examples_removed"] == 0
        assert again[0]["cycles_created"] == 0
        assert await session.scalar(select(func.count()).select_from(Appraisal)) == 8
