import hmac
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.access_control import require_access
from app.api.deps import get_platform_db, get_tenant_db, get_tenant_id
from app.core.config import get_settings
from app.models import CompanyDomain
from app.services.domains import add_custom, central_hosts, domain_read, ensure_automatic, owned_company, resolve_company, verify_custom

router = APIRouter(prefix="/domains", tags=["Company domains"])
platform_router = APIRouter(prefix="/platform/tenants/{tenant_id}/domains", tags=["Platform company domains"])


class DomainCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hostname: str = Field(min_length=3, max_length=253)


@router.get("/context")
async def context(request: Request):
    return {"company": request.state.company_domain, "central_url": f"https://{get_settings().hrms_base_domain}"}


@router.get("/tls-allowed", include_in_schema=False)
async def tls_allowed(domain: str = "", key: str = ""):
    secret = get_settings().domain_tls_secret
    if not secret or not hmac.compare_digest(secret, key):
        raise HTTPException(403, "Forbidden")
    host = domain.lower().rstrip(".")
    base = get_settings().hrms_base_domain.lower().strip()
    if (base and host in {base, f"app.{base}", f"admin.{base}"}) or await resolve_company(host):
        return Response(status_code=204)
    raise HTTPException(403, "Domain not permitted")


def management_routes(target, db_dependency, tenant_dependency=None):
    dependencies = [Depends(require_access("domains.manage"))] if tenant_dependency else []
    # Path tenant_id is supplied by FastAPI for the platform router; tenant JWT for the tenant router.
    async def tenant_from_path(tenant_id: uuid.UUID):
        return tenant_id
    tenant_source = tenant_dependency or tenant_from_path

    @target.get("", dependencies=dependencies)
    async def listing(company_id: uuid.UUID, tenant_id: uuid.UUID = Depends(tenant_source), session: AsyncSession = Depends(db_dependency)):
        company = await owned_company(session, company_id, tenant_id)
        await ensure_automatic(session, company)
        return [domain_read(row) for row in (await session.scalars(select(CompanyDomain).where(CompanyDomain.company_id == company_id, CompanyDomain.tenant_id == tenant_id).order_by(CompanyDomain.created_at))).all()]

    @target.post("", status_code=201, dependencies=dependencies)
    async def create(payload: DomainCreate, company_id: uuid.UUID, tenant_id: uuid.UUID = Depends(tenant_source), session: AsyncSession = Depends(db_dependency)):
        return domain_read(await add_custom(session, await owned_company(session, company_id, tenant_id), payload.hostname))

    async def owned_domain(session, domain_id, tenant_id):
        domain = await session.get(CompanyDomain, domain_id)
        if domain is None or domain.tenant_id != tenant_id:
            raise HTTPException(404, "Domain not found")
        await owned_company(session, domain.company_id, tenant_id)
        return domain

    @target.post("/{domain_id}/verify", dependencies=dependencies)
    async def verify(domain_id: uuid.UUID, tenant_id: uuid.UUID = Depends(tenant_source), session: AsyncSession = Depends(db_dependency)):
        return domain_read(await verify_custom(session, await owned_domain(session, domain_id, tenant_id)))

    async def removable(request, session, domain_id, tenant_id):
        domain = await owned_domain(session, domain_id, tenant_id)
        if domain.kind != "CUSTOM":
            raise HTTPException(422, "The automatic company address cannot be removed")
        if domain.hostname == request.url.hostname:
            raise HTTPException(422, "Open the main HRMS address before disconnecting this domain")
        return domain

    @target.post("/{domain_id}/disable", dependencies=dependencies)
    async def disable(request: Request, domain_id: uuid.UUID, tenant_id: uuid.UUID = Depends(tenant_source), session: AsyncSession = Depends(db_dependency)):
        domain = await removable(request, session, domain_id, tenant_id)
        domain.status = "DISABLED"
        await session.flush()
        return domain_read(domain)

    @target.delete("/{domain_id}", status_code=204, dependencies=dependencies)
    async def remove(request: Request, domain_id: uuid.UUID, tenant_id: uuid.UUID = Depends(tenant_source), session: AsyncSession = Depends(db_dependency)):
        await session.delete(await removable(request, session, domain_id, tenant_id))
        return Response(status_code=204)


management_routes(router, get_tenant_db, get_tenant_id)
management_routes(platform_router, get_platform_db)
