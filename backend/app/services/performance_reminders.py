"""Run idempotent reminders from an existing scheduler or a scheduled command.

Usage: python -m app.services.performance_reminders
The command uses an active user with manage_cycles in each tenant, and explicitly
sets the tenant RLS context before accessing company-scoped performance data.
No email transport exists in this project; all reminders are persisted in-app.
"""
import asyncio

from sqlalchemy import select, text

from app.db.session import dispose_engine, get_session_maker
from app.models import Company, Tenant, User
from app.services.access import permissions_for
from app.services.performance import reminders
from app.services.appraisals import reminders as appraisal_reminders


async def run():
    total = 0
    async with get_session_maker()() as session:
        await session.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        tenants = list((await session.scalars(select(Tenant.id).where(Tenant.status == "ACTIVE"))).all())
        await session.rollback()
        for tenant_id in tenants:
            await session.execute(text("SELECT set_config('app.current_tenant_id', :tenant, true)"), {"tenant": str(tenant_id)})
            users = list((await session.scalars(select(User).where(User.tenant_id == tenant_id, User.status == "ACTIVE"))).all())
            actor = None
            for user in users:
                if "performance.manage_cycles" in await permissions_for(session, user):
                    actor = user
                    break
            if actor:
                for company_id in (await session.scalars(select(Company.id).where(Company.tenant_id == tenant_id))).all():
                    total += (await reminders(session, actor, company_id))["notifications_created"]
                    total += (await appraisal_reminders(session, actor, company_id))["notifications_created"]
            await session.commit()
    await dispose_engine()
    print(f"Created {total} performance reminders")


if __name__ == "__main__":
    asyncio.run(run())
