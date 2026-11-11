"""Read-only API and financial checks after a legacy import (no real emails)."""
import argparse
import asyncio
import json
import os
import uuid
from decimal import Decimal
from pathlib import Path
from sqlalchemy.engine import make_url
from app.core.config import get_settings


async def verify(args):
    if args.database:
        if not args.database.startswith("hrms_migration_"):
            raise ValueError("Unexpected rehearsal database name")
        os.environ["DATABASE_URL"] = make_url(get_settings().database_url).set(database=args.database).render_as_string(hide_password=False)
        get_settings.cache_clear()
    from sqlalchemy import select, text, func
    from httpx import AsyncClient, ASGITransport
    from app.main import create_app
    from app.db.session import get_session_maker, dispose_engine
    from app.models import User, PayrollPayslip, PayrollRun, Employee, EmployeeCompensation, Branch, Country
    from app.core.security import create_access_token
    from app.models.legacy_import import LegacyImportRecord
    from scripts.prepare_legacy_organization import legacy_id
    mapping = json.loads(Path(args.mapping).read_text())
    source = json.loads(Path(args.snapshot).read_text())["tables"]
    tenant = uuid.UUID(mapping["tenant_id"])
    async with get_session_maker()() as session:
        await session.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        owner = await session.get(User, uuid.UUID(mapping["preserved_owner_id"]))
        owner_token = create_access_token(user_id=owner.id, email=owner.email, tenant_id=tenant)
        active = await session.scalar(select(User).join(Employee, User.employee_id == Employee.id).where(User.tenant_id == tenant, User.status == "ACTIVE", Employee.status == "ACTIVE", User.role == "EMPLOYEE").limit(1))
        employee_token = create_access_token(user_id=active.id, email=active.email, tenant_id=tenant)
        for source_row in source["payroll_items"]:
            row = await session.get(PayrollPayslip, legacy_id("payroll_items", source_row["id"]))
            assert row is not None and row.gross == Decimal(source_row["gross_pay"]) and row.net == Decimal(source_row["net_pay"]), "Historical payroll amounts changed"
        source_users = {r["email"].strip().lower(): r for r in source["users"]}
        for row in (await session.scalars(select(User).where(User.tenant_id == tenant, User.id != owner.id))).all():
            assert row.password_hash == source_users[row.email.strip().lower()]["password_hash"], "Imported login hash changed"
        archive_count = await session.scalar(select(func.count()).select_from(LegacyImportRecord))
        assert archive_count == sum(map(len, source.values()))
        assert await session.scalar(select(func.count()).select_from(EmployeeCompensation).where(EmployeeCompensation.is_historical)) > 0
        country_slips = (await session.execute(select(Country.code, PayrollPayslip.id).join(Branch, Branch.country_id == Country.id)
            .join(PayrollRun, PayrollRun.branch_id == Branch.id).join(PayrollPayslip, PayrollPayslip.run_id == PayrollRun.id))).all()
        samples = {}
        for code, identity in country_slips:
            samples.setdefault(code, str(identity))
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    staff_headers = {"Authorization": f"Bearer {employee_token}"}
    checked = []
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        for identity in mapping["companies"].values():
            for path in [f"/employees?company_id={identity}", f"/leave-balances?company_id={identity}&year=2026",
                         f"/legacy-import/tables?company_id={identity}", f"/workforce/consultants?company_id={identity}"]:
                response = await client.get(path, headers=owner_headers)
                assert response.status_code == 200, f"{path}: {response.status_code}"
                checked.append(path.split("?")[0])
        response = await client.get("/employee-portal/me", headers=staff_headers)
        assert response.status_code == 200
        assert "bank_account_number" not in response.json()["employee"]
        denied = await client.get(f"/legacy-import/tables?company_id={next(iter(mapping['companies'].values()))}", headers=staff_headers)
        assert denied.status_code == 403
        for code, identity in samples.items():
            response = await client.get(f"/payroll/payslips/{identity}/pdf", headers=owner_headers)
            assert response.status_code == 200 and response.content.startswith(b"%PDF"), f"{code} PDF failed"
            checked.append(f"{code} payslip PDF")
    await dispose_engine()
    print(json.dumps(dict(status="PASS", employee_snapshots_checked=len(source["payroll_items"]),
        imported_login_hashes_checked=len(source["users"])-1, retained_source_records=archive_count,
        checks=checked, employee_portal=True, owner_only_archive=True, real_emails_sent=False), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database")
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--snapshot", required=True)
    asyncio.run(verify(parser.parse_args()))
