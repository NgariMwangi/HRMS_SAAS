import uuid
from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from app.api.access_control import require_access
from app.api.deps import get_current_user, get_tenant_db, get_current_admin, get_platform_db
from app.api.routes.employee_portal import portal_employee
from app.models import Employee, User
from app.services.payslips import document

router = APIRouter(prefix="/payroll/payslips", tags=["payslips"], dependencies=[Depends(require_access("payroll.manage"))])
employee_router = APIRouter(prefix="/employee-portal/payslips", tags=["employee payslips"], dependencies=[Depends(require_access("payroll.view_own"))])
platform_router = APIRouter(prefix="/platform/tenants/{tenant_id}/payroll/payslips", tags=["platform payslips"], dependencies=[Depends(get_current_admin)])


async def pdf(data):
    from app.services.payslip_pdf import render
    return Response(await run_in_threadpool(render, data), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{data["filename"]}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{identity}")
async def detail(identity: uuid.UUID, response: Response, session: AsyncSession = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return await document(session, identity, user.tenant_id)


@router.get("/{identity}/pdf")
async def download(identity: uuid.UUID, session: AsyncSession = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    return await pdf(await document(session, identity, user.tenant_id))


@employee_router.get("/{identity}/pdf")
async def own_download(identity: uuid.UUID, employee: Employee = Depends(portal_employee), session: AsyncSession = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    return await pdf(await document(session, identity, user.tenant_id, employee))


@platform_router.get("/{identity}")
async def platform_detail(tenant_id: uuid.UUID, identity: uuid.UUID, response: Response, session: AsyncSession = Depends(get_platform_db)):
    response.headers["Cache-Control"] = "private, no-store"
    return await document(session, identity, tenant_id)


@platform_router.get("/{identity}/pdf")
async def platform_download(tenant_id: uuid.UUID, identity: uuid.UUID, session: AsyncSession = Depends(get_platform_db)):
    return await pdf(await document(session, identity, tenant_id))
