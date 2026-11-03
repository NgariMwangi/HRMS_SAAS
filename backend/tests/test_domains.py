from types import SimpleNamespace
import uuid
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import get_session_maker
from app.models import Company, Employee, EmployeeNextOfKin
from app.services.domains import hostname
from tests.test_access import workspace, staff_login
from tests.test_platform import _admin_login
from tests.test_leave_requests import _person
from tests.test_employee_portal import google_tokens


@pytest.mark.parametrize("value", ["https://company.com", "company.com/path", "a@company.com", "*.company.com", "127.0.0.1", "bad..com", "-bad.com", "localhost", "a.com:443"])
def test_invalid_hostname(value):
    with pytest.raises(HTTPException):
        hostname(value)


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_domain_management_and_dns_proof(client, monkeypatch):
    w, owner = await workspace(client)
    other, foreign = await workspace(client, "foreign-domains@example.com")
    cid = w["company"]["id"]
    listing = await client.get(f"/domains?company_id={cid}", headers=owner)
    assert listing.status_code == 200, listing.text
    automatic = listing.json()[0]
    assert automatic["kind"] == "AUTOMATIC" and automatic["status"] == "ACTIVE"
    assert "verification_token" not in automatic
    await client.patch(f"/companies/{cid}", headers=owner, json={"name": "Renamed company"})
    assert (await client.get(f"/domains?company_id={cid}", headers=owner)).json()[0]["hostname"] == automatic["hostname"]
    assert (await client.get(f"/domains?company_id={cid}", headers=foreign)).status_code == 404
    for role in ["HR", "MANAGER", "EMPLOYEE"]:
        _, _, staff = await staff_login(client, owner, w, f"Domains{role}", role)
        assert (await client.get(f"/domains?company_id={cid}", headers=staff)).status_code == 403
    for bad in ["admin.hrms.techtutor.co.ke", "squat.hrms.techtutor.co.ke", "x.local", "127.0.0.1", "https://people.mycompany.co.ke"]:
        assert (await client.post(f"/domains?company_id={cid}", headers=owner, json={"hostname": bad})).status_code == 422
    added = await client.post(f"/domains?company_id={cid}", headers=owner, json={"hostname": "People.Mycompany.co.ke."})
    assert added.status_code == 201, added.text
    domain = added.json(); path = f"/domains/{domain['id']}"
    assert domain["status"] == "PENDING"
    assert (await client.get("/domains/context", headers={"Host": domain["hostname"]})).status_code == 404
    assert (await client.post(f"/domains?company_id={other['company']['id']}", headers=foreign, json={"hostname": domain["hostname"]})).status_code == 409
    assert (await client.post(path + "/verify", headers=foreign)).status_code == 404
    resolver = AsyncMock()
    monkeypatch.setattr("app.services.domains.dns.asyncresolver.Resolver", lambda: resolver)
    proof = domain["dns_records"][1]["value"]
    resolver.resolve.side_effect = [[SimpleNamespace(strings=[proof.encode()])], [SimpleNamespace(target="wrong.company.co.ke.")]]
    assert (await client.post(path + "/verify", headers=owner)).status_code == 422
    resolver.resolve.side_effect = [[SimpleNamespace(strings=[b"wrong proof"])], [SimpleNamespace(target="hrms.techtutor.co.ke.")]]
    assert (await client.post(path + "/verify", headers=owner)).status_code == 422
    resolver.resolve.side_effect = [[SimpleNamespace(strings=[proof[:12].encode(), proof[12:].encode()])], [SimpleNamespace(target="hrms.techtutor.co.ke.")]]
    verified = await client.post(path + "/verify", headers=owner)
    assert verified.status_code == 200 and verified.json()["status"] == "ACTIVE", verified.text
    context = await client.get("/domains/context", headers={"Host": domain["hostname"]})
    assert context.status_code == 200 and context.json()["company"]["company_id"] == cid
    assert context.headers["cache-control"] == "no-store" and proof not in context.text
    assert (await client.post(path + "/disable", headers={**owner, "Host": domain["hostname"]})).status_code == 422
    assert (await client.post(path + "/disable", headers=owner)).json()["status"] == "DISABLED"
    assert (await client.get("/domains/context", headers={"Host": domain["hostname"]})).status_code == 404
    resolver.resolve.side_effect = [[SimpleNamespace(strings=[proof.encode()])], [SimpleNamespace(target="hrms.techtutor.co.ke.")]]
    assert (await client.post(path + "/verify", headers=owner)).json()["status"] == "ACTIVE"
    assert (await client.delete(path, headers=owner)).status_code == 204
    assert (await client.delete(f"/domains/{automatic['id']}", headers=owner)).status_code == 422
    admin = await _admin_login(client)
    assert (await client.get(f"/platform/tenants/{w['tenant']['id']}/domains?company_id={cid}", headers=admin)).status_code == 200
    assert (await client.get(f"/platform/tenants/{other['tenant']['id']}/domains?company_id={cid}", headers=admin)).status_code == 404


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_host_authentication_and_company_isolation(client, monkeypatch):
    w, owner = await workspace(client)
    other, foreign = await workspace(client, "different-tenant@example.com")
    cid = w["company"]["id"]
    second = (await client.post("/companies", headers=owner, json={"name": "Other company"})).json()
    branch = (await client.post("/branches", headers=owner, json={"company_id": second["id"], "country_id": w["branch"]["country_id"], "name": "Other office", "code": "OTHER"})).json()
    own, _, employee = await staff_login(client, owner, w, "DomainOwn")
    second_ws = {**w, "company": second, "branch": branch}
    outsider, identity, outsider_token = await staff_login(client, owner, second_ws, "DomainOther")
    automatic = (await client.get(f"/domains?company_id={cid}", headers=owner)).json()[0]
    host = automatic["hostname"]; bound = {**owner, "Host": host}
    second_host = (await client.get(f"/domains?company_id={second['id']}", headers=owner)).json()[0]["hostname"]
    assert [row["id"] for row in (await client.get("/companies", headers={**owner, "Host": second_host})).json()] == [second["id"]]
    assert (await client.get("/domains/context", headers={"Host": "unconnected.company.co.ke", "X-Forwarded-Host": host})).status_code == 404
    assert (await client.get("/domains/context", headers={"X-Forwarded-Host": host})).json()["company"] is None
    assert (await client.get("/companies", headers=bound)).json()[0]["id"] == cid
    assert len((await client.get("/companies", headers=bound)).json()) == 1
    assert (await client.get(f"/companies/{second['id']}", headers=bound)).status_code == 404
    assert (await client.get("/companies", headers={**foreign, "Host": host})).status_code == 403
    assert (await client.post("/companies", headers=bound, json={"name": "Forbidden company"})).status_code == 403
    employees = await client.get("/employees", headers=bound)
    assert employees.status_code == 200, employees.text
    assert [row["id"] for row in employees.json()] == [own["id"]]
    assert (await client.get(f"/employees/{outsider['id']}/next-of-kin", headers=bound)).status_code == 404
    assert (await client.patch(f"/employees/{own['id']}", headers=bound, json={"branch_id": branch["id"]})).status_code in {403, 400}
    assert (await client.post("/auth/login", headers={"Host": host}, json={"email": "different-tenant@example.com", "password": "password12"})).status_code == 403
    assert (await client.post("/auth/login", headers={"Host": host}, json={"email": identity["email"], "password": "Password123!"})).status_code == 403
    assert (await client.post("/auth/refresh", headers={"Host": host}, json={"refresh_token": other["refresh_token"]})).status_code == 403
    assert (await client.get("/auth/me", headers={**outsider_token, "Host": host})).status_code == 403
    assert (await client.get("/employee-portal/me", headers={**employee, "Host": host})).status_code == 200
    assert (await client.post("/platform/auth/login", headers={"Host": host}, json={})).status_code == 403
    assert (await client.post("/auth/register", headers={"Host": host}, json={})).status_code == 403
    monkeypatch.setattr(get_settings(), "domain_tls_secret", "test-tls-secret")
    assert (await client.get("/domains/tls-allowed", params={"domain": host, "key": "wrong"})).status_code == 403
    assert (await client.get("/domains/tls-allowed", params={"domain": host, "key": "test-tls-secret"})).status_code == 204
    assert (await client.get("/domains/tls-allowed", params={"domain": "unknown.company.co.ke", "key": "test-tls-secret"})).status_code == 403
    # Direct ORM checks verify isolation even when development PostgreSQL runs as a superuser.
    async with get_session_maker()() as session:
        session.info["domain_company_id"] = uuid.UUID(cid)
        assert await session.get(Employee, uuid.UUID(outsider["id"])) is None
        assert await session.get(Company, uuid.UUID(second["id"])) is None
        assert list((await session.scalars(select(Employee.id))).all()) == [uuid.UUID(own["id"])]


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_company_domain_scopes_module_records_and_child_writes(client):
    from datetime import date
    from app.models import EmployeeCompensation, EmployeePayLine
    from tests.test_recruitment import vacancy
    from tests.test_performance import setup_cycle
    from tests.test_tenancy import _kenya
    w, owner = await workspace(client)
    other, foreign = await workspace(client, "module-other@example.com")
    own, _, _ = await staff_login(client, owner, w, "ScopeOwn")
    outsider, _, _ = await staff_login(client, foreign, other, "ScopeForeign")
    cid = w["company"]["id"]
    review, _ = await setup_cycle(client, owner, cid)
    foreign_review, _ = await setup_cycle(client, foreign, other["company"]["id"])
    job = await vacancy(client, owner, cid)
    foreign_job = await vacancy(client, foreign, other["company"]["id"])
    host = (await client.get(f"/domains?company_id={cid}", headers=owner)).json()[0]["hostname"]
    bound = {**owner, "Host": host}
    for path in [f"/performance/reviews?company_id={other['company']['id']}", f"/recruitment/workspace?company_id={other['company']['id']}", f"/payroll/runs?company_id={other['company']['id']}", f"/reports/headcount?company_id={other['company']['id']}"]:
        assert (await client.get(path, headers=bound)).status_code in {403, 404}, path
    reviews = await client.get(f"/performance/reviews?company_id={cid}", headers=bound)
    assert reviews.status_code == 200 and review["id"] in str(reviews.json()) and foreign_review["id"] not in str(reviews.json())
    recruitment = await client.get(f"/recruitment/workspace?company_id={cid}", headers=bound)
    assert recruitment.status_code == 200 and job["id"] in str(recruitment.json()) and foreign_job["id"] not in str(recruitment.json())
    kenya = await _kenya()
    async with get_session_maker()() as session:
        compensation = EmployeeCompensation(company_id=uuid.UUID(other["company"]["id"]), employee_id=uuid.UUID(outsider["id"]), effective_from=date(2026, 1, 1), structure="GROSS_ONLY", gross_amount=20000, currency_id=kenya.default_currency_id)
        session.add(compensation); await session.flush()
        line = EmployeePayLine(compensation_id=compensation.id, name="Foreign allowance", amount=1000)
        session.add(line); await session.commit()
        compensation_id, line_id = compensation.id, line.id
    async with get_session_maker()() as session:
        session.info["domain_company_id"] = uuid.UUID(cid)
        assert await session.get(EmployeePayLine, line_id) is None
        assert list((await session.scalars(select(EmployeePayLine))).all()) == []
        session.add(EmployeePayLine(compensation_id=compensation_id, name="Tampered reference", amount=1000))
        with pytest.raises(HTTPException) as error:
            await session.flush()
        assert error.value.status_code == 403
        await session.rollback()


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_google_does_not_link_an_employee_to_the_wrong_company_domain(client, google_tokens):
    from app.models import User
    w, owner = await workspace(client)
    other, foreign = await workspace(client, "google-foreign@example.com")
    _, identity, _ = await staff_login(client, foreign, other, "GoogleForeign")
    host = (await client.get(f"/domains?company_id={w['company']['id']}", headers=owner)).json()[0]["hostname"]
    nonce = (await client.get("/auth/google/challenge", headers={"Host": host})).json()["nonce"]
    response = await client.post("/auth/google/login", headers={"Host": host}, json={"credential": google_tokens(nonce), "email": identity["email"], "password": "Password123!"})
    assert response.status_code == 403, response.text
    async with get_session_maker()() as session:
        assert (await session.get(User, uuid.UUID(identity["id"]))).google_subject is None
