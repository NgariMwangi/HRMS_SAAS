from collections.abc import AsyncIterator, Iterator
from pathlib import Path
import asyncio
import os

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.core.config import get_settings
from app.db.seed import seed_countries, seed_payroll_packs, seed_platform_admin
from app.db.session import dispose_engine, get_engine, get_session_maker
from app.main import create_app

TEST_DB_NAME = "hrms_test"
_DEFAULT_DEV_URL = "postgresql+asyncpg://hrms:hrms@localhost:5433/hrms"


def _database_name(url: str) -> str:
    return url.rpartition("/")[2].split("?")[0]


def _with_database(url: str, name: str) -> str:
    prefix, _, rest = url.rpartition("/")
    query = f"?{rest.split('?', 1)[1]}" if "?" in rest else ""
    return f"{prefix}/{name}{query}"


def _asyncpg_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _require_test_database() -> None:
    name = _database_name(get_settings().database_url)
    if name != TEST_DB_NAME:
        raise RuntimeError(
            f"Refusing to touch database {name!r}. Tests must use {TEST_DB_NAME!r}."
        )


@pytest.fixture(scope="session", autouse=True)
def _apply_migrations_and_seed() -> Iterator[None]:
    source_url = os.environ.get("DATABASE_URL") or _DEFAULT_DEV_URL
    if _database_name(source_url) != TEST_DB_NAME:
        admin_dsn = _asyncpg_dsn(source_url)

        async def _ensure_test_db() -> None:
            conn = await asyncpg.connect(admin_dsn)
            try:
                exists = await conn.fetchval(
                    "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
                )
                if not exists:
                    await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
            finally:
                await conn.close()

        asyncio.run(_ensure_test_db())
        os.environ["DATABASE_URL"] = _with_database(source_url, TEST_DB_NAME)

    get_settings.cache_clear()
    _require_test_database()

    backend_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_root / "alembic.ini"))
    command.upgrade(cfg, "head")

    async def _seed() -> None:
        maker = get_session_maker()
        async with maker() as session:
            await seed_countries(session)
            await seed_payroll_packs(session)
            await seed_platform_admin(session)
            await session.commit()
        await dispose_engine()

    asyncio.run(_seed())
    yield
    asyncio.run(dispose_engine())


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    get_settings.cache_clear()
    _require_test_database()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await dispose_engine()


@pytest.fixture
async def clean_tenant_tables() -> AsyncIterator[None]:
    _require_test_database()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE payroll_payslip_lines, payroll_payslips, payroll_runs, employee_pay_lines, employee_compensation, company_payroll_settings, audit_logs, attendance_records, employees, job_titles, departments, branches, companies, users, tenants RESTART IDENTITY CASCADE"
            )
        )
    yield


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
