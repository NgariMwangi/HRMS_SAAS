import uuid
from datetime import date, datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.access_control import require_access
from app.api.deps import get_current_admin, get_current_user, get_platform_db, get_tenant_db
from app.api.org import company_for_tenant
from app.models import Branch, Department, PlatformAdmin, Tenant, User
from app.services import reports as service
from app.services.access import permissions_for
from app.core.permissions import ALL_PERMISSIONS

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_access("reports.view"))])
platform_router = APIRouter(prefix="/platform/tenants/{tenant_id}/reports", tags=["platform-reports"])


def selection(company_id: uuid.UUID, branch_id: uuid.UUID | None = None, department_id: uuid.UUID | None = None,
    start_on: date | None = None, end_on: date | None = None,
    status: str | None = Query(default=None, max_length=30), q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=250)):
    today = datetime.now(ZoneInfo("Africa/Nairobi")).date()
    end = end_on or today
    return dict(company_id=company_id, branch_id=branch_id, department_id=department_id, start_on=start_on or end.replace(day=1), end_on=end, status=status, q=q, page=page, page_size=page_size)


def no_cache(response):
    response.headers["Cache-Control"] = "no-store"


async def catalog_data(session, tenant_id, company_id, permissions):
    company = await company_for_tenant(session, company_id, tenant_id)
    branches = list((await session.scalars(select(Branch).where(Branch.company_id == company_id).order_by(Branch.name))).all())
    departments = list((await session.scalars(select(Department).where(Department.company_id == company_id).order_by(Department.name))).all())
    return dict(company=company.name, reports=service.allowed(permissions), branches=[dict(id=b.id, name=b.name) for b in branches], departments=[dict(id=d.id, name=d.name) for d in departments])


async def generate(session, tenant_id, kind, filters, permissions=None):
    if kind not in service.CATALOG:
        service.fail("Report not found", 404)
    if permissions is not None and kind not in {r["key"] for r in service.allowed(permissions)}:
        service.fail("You do not have access to this report", 403)
    return await service.generate(session, tenant_id, kind=kind, **{k:v for k,v in filters.items() if k not in {"page", "page_size"}})


def paginated(report, filters):
    first = (filters["page"] - 1) * filters["page_size"]
    return {**report, "rows": report["rows"][first:first + filters["page_size"]], "page": filters["page"], "page_size": filters["page_size"]}


def exported(report):
    filename = f"{report['key']}-{report['end_on'].isoformat()}.csv"
    return Response(service.csv_bytes(report), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/catalog")
async def catalog(company_id: uuid.UUID, response: Response, session: AsyncSession = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    no_cache(response)
    return await catalog_data(session, user.tenant_id, company_id, await permissions_for(session, user))


@router.get("/{kind}/export")
async def export_report(kind: str, filters: dict = Depends(selection), session: AsyncSession = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    return exported(await generate(session, user.tenant_id, kind, filters, await permissions_for(session, user)))


async def pdf_export(report):
    from app.services.report_pdf import render
    from fastapi.concurrency import run_in_threadpool
    content = await run_in_threadpool(render, report)
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{report["key"]}-{report["end_on"]}.pdf"', "Cache-Control": "no-store"})


@router.get("/{kind}/pdf")
async def export_pdf(kind: str, filters: dict = Depends(selection), session: AsyncSession = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    return await pdf_export(await generate(session, user.tenant_id, kind, filters, await permissions_for(session, user)))


@router.get("/{kind}")
async def report(kind: str, response: Response, filters: dict = Depends(selection), session: AsyncSession = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    no_cache(response)
    return paginated(await generate(session, user.tenant_id, kind, filters, await permissions_for(session, user)), filters)


@platform_router.get("/catalog")
async def platform_catalog(tenant_id: uuid.UUID, company_id: uuid.UUID, response: Response, session: AsyncSession = Depends(get_platform_db), _: PlatformAdmin = Depends(get_current_admin)):
    if await session.get(Tenant, tenant_id) is None:
        service.fail("Tenant not found", 404)
    no_cache(response)
    return await catalog_data(session, tenant_id, company_id, ALL_PERMISSIONS)


@platform_router.get("/{kind}/export")
async def platform_export(tenant_id: uuid.UUID, kind: str, filters: dict = Depends(selection), session: AsyncSession = Depends(get_platform_db), _: PlatformAdmin = Depends(get_current_admin)):
    return exported(await generate(session, tenant_id, kind, filters))


@platform_router.get("/{kind}/pdf")
async def platform_pdf(tenant_id: uuid.UUID, kind: str, filters: dict = Depends(selection), session: AsyncSession = Depends(get_platform_db), _: PlatformAdmin = Depends(get_current_admin)):
    return await pdf_export(await generate(session, tenant_id, kind, filters))


@platform_router.get("/{kind}")
async def platform_report(tenant_id: uuid.UUID, kind: str, response: Response, filters: dict = Depends(selection), session: AsyncSession = Depends(get_platform_db), _: PlatformAdmin = Depends(get_current_admin)):
    no_cache(response)
    return paginated(await generate(session, tenant_id, kind, filters), filters)
