import ipaddress
import re
import secrets
import unicodedata
from datetime import datetime, timezone
import dns.asyncresolver
import dns.exception
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from app.core.config import get_settings
from app.db.session import get_session_maker
from app.models import Company, CompanyDomain, Tenant


def hostname(value: str) -> str:
    value = value.strip().rstrip(".").lower()
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError:
        raise HTTPException(422, "Enter a valid domain name")
    if len(value) > 253 or "." not in value or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in value.split(".")):
        raise HTTPException(422, "Enter only a domain name, such as people.example.com")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise HTTPException(422, "An IP address cannot be used as a company domain")


def central_hosts():
    settings = get_settings()
    hosts = {item.strip().lower() for item in settings.hrms_central_hosts.split(",") if item.strip()}
    if settings.hrms_base_domain:
        base = hostname(settings.hrms_base_domain)
        hosts.update({base, f"app.{base}", f"admin.{base}"})
    return hosts


async def ensure_automatic(session, company):
    base = get_settings().hrms_base_domain.strip()
    if not base:
        return None
    base = hostname(base)
    await session.scalar(select(Company.id).where(Company.id == company.id).with_for_update())
    existing = await session.scalar(select(CompanyDomain).where(CompanyDomain.company_id == company.id, CompanyDomain.kind == "AUTOMATIC"))
    if existing:
        return existing
    slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", company.name).encode("ascii", "ignore").decode().lower()).strip("-")[:45].rstrip("-") or "company"
    if slug in {"admin", "app", "api", "www", "mail", "support"}:
        slug += "-company"
    for suffix in ["", f"-{company.id.hex[:8]}", f"-{company.id.hex}"]:
        domain = CompanyDomain(tenant_id=company.tenant_id, company_id=company.id, hostname=f"{slug[:63-len(suffix)]}{suffix}.{base}", kind="AUTOMATIC", status="ACTIVE", verification_token=secrets.token_urlsafe(32))
        try:
            async with session.begin_nested():
                session.add(domain)
                await session.flush()
            return domain
        except IntegrityError:
            continue
    raise HTTPException(409, "Could not allocate a company address")


async def backfill_automatic():
    async with get_session_maker()() as session:
        await session.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        for company in (await session.scalars(select(Company))).all():
            await ensure_automatic(session, company)
        await session.commit()


async def resolve_company(host):
    async with get_session_maker()() as session:
        await session.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
        result = (await session.execute(select(CompanyDomain, Company).join(Company, Company.id == CompanyDomain.company_id).join(Tenant, Tenant.id == Company.tenant_id).where(CompanyDomain.hostname == host, CompanyDomain.status == "ACTIVE", Company.status == "ACTIVE", Tenant.status == "ACTIVE"))).first()
        if result:
            domain, company = result
            return {"company_id": company.id, "tenant_id": company.tenant_id, "company_name": company.name, "hostname": domain.hostname}
    return None


async def owned_company(session, company_id, tenant_id):
    company = await session.get(Company, company_id)
    if company is None or company.tenant_id != tenant_id:
        raise HTTPException(404, "Company not found")
    return company


def domain_read(domain):
    return {"id": domain.id, "company_id": domain.company_id, "hostname": domain.hostname, "kind": domain.kind, "status": domain.status, "verified_at": domain.verified_at,
            "dns_records": [] if domain.kind == "AUTOMATIC" else [
                {"type": "CNAME", "name": domain.hostname, "value": get_settings().hrms_domain_target},
                {"type": "TXT", "name": f"_hrms-verification.{domain.hostname}", "value": f"hrms-verification={domain.verification_token}"}]}


async def add_custom(session, company, value):
    value = hostname(value)
    base = get_settings().hrms_base_domain.lower().strip()
    if value in central_hosts() or (base and (value == base or value.endswith("." + base))) or value.endswith((".localhost", ".local", ".internal", ".test", ".invalid", ".example")):
        raise HTTPException(422, "Choose a public domain owned by your company, outside the HRMS main domain")
    existing = await session.scalar(select(CompanyDomain.id).where(CompanyDomain.hostname == value))
    if existing:
        raise HTTPException(409, "This domain is already registered")
    count = len((await session.scalars(select(CompanyDomain.id).where(CompanyDomain.company_id == company.id))).all())
    if count >= 11:
        raise HTTPException(422, "A company can connect up to ten custom domains")
    domain = CompanyDomain(tenant_id=company.tenant_id, company_id=company.id, hostname=value, kind="CUSTOM", status="PENDING", verification_token=secrets.token_urlsafe(32))
    try:
        async with session.begin_nested():
            session.add(domain)
            await session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "This domain is already registered") from exc
    return domain


async def verify_custom(session, domain):
    if domain.kind != "CUSTOM":
        raise HTTPException(422, "The platform manages automatic company addresses")
    resolver = dns.asyncresolver.Resolver()
    try:
        txt = await resolver.resolve(f"_hrms-verification.{domain.hostname}", "TXT", lifetime=4)
        cname = await resolver.resolve(domain.hostname, "CNAME", lifetime=4)
    except dns.exception.DNSException as exc:
        raise HTTPException(422, "DNS records are not available yet. Check both records and try again after DNS updates propagate.") from exc
    values = {b"".join(record.strings).decode("utf-8", errors="replace") for record in txt}
    targets = {str(record.target).lower().rstrip(".") for record in cname}
    if f"hrms-verification={domain.verification_token}" not in values or hostname(get_settings().hrms_domain_target) not in targets:
        raise HTTPException(422, "DNS records do not match. Add the exact TXT and CNAME records shown below, then verify again.")
    domain.status = "ACTIVE"
    domain.verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.flush()
    return domain
