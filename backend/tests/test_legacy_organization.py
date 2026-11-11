import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select
from app.db.session import get_session_maker
from app.models import Branch, Company, User
from scripts.prepare_legacy_organization import prepare
from tests.test_access import workspace


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_organization_dry_run_preservation_and_repeated_apply(client, tmp_path):
    w, _ = await workspace(client)
    source = {"companies": [{"id": 1, "name": "Nexgen", "is_active": True},
        {"id": 2, "name": "WashFlow Kenya Limited", "is_active": True}],
        "branches": [{"id": 1, "company_id": 1, "name": "Head Office", "country_code": "KE"},
        {"id": 2, "company_id": 2, "name": "Head Office", "country_code": "KE"},
        {"id": 3, "company_id": 1, "name": "Uganda", "country_code": "UG"}]}
    file = tmp_path / "organization.json"
    file.write_text(json.dumps(source), encoding="utf-8")
    args = SimpleNamespace(source_file=str(file), tenant_id=UUID(w["tenant"]["id"]),
        nexgen_company_id=UUID(w["company"]["id"]), head_office_id=UUID(w["branch"]["id"]),
        owner_id=UUID(w["user"]["id"]), nexgen_branches="", apply=False)
    async with get_session_maker()() as session:
        owner = await session.get(User, args.owner_id)
        original_password = owner.password_hash
    await prepare(args)
    async with get_session_maker()() as session:
        assert len((await session.scalars(select(Company))).all()) == 1
    args.apply = True
    await prepare(args)
    await prepare(args)
    async with get_session_maker()() as session:
        companies = (await session.scalars(select(Company))).all()
        branches = (await session.scalars(select(Branch))).all()
        assert len(companies) == 2 and len(branches) == 2
        assert len([b for b in branches if b.company_id == args.nexgen_company_id]) == 1
        owner = await session.get(User, args.owner_id)
        assert owner.role == "OWNER" and owner.password_hash == original_password
    args.nexgen_branches = "3"
    await prepare(args)
    async with get_session_maker()() as session:
        assert len((await session.scalars(select(Branch))).all()) == 3
