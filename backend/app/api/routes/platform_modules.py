"""Platform oversight uses explicit tenant/company scopes and never impersonates staff."""
import uuid
import csv
import io
from types import SimpleNamespace
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_admin, get_platform_db
from app.api.org import company_for_tenant
from app.models.performance import PerformanceCycle, PerformancePIP, PerformancePIPReview, PerformanceSettings, RatingScale, Competency
from app.models.recruitment import Vacancy, Candidate, Application, Interview, Offer, RecruitmentEvent
from app.services import performance
from app.services import access
from app.core.permissions import CATALOG
from app.models import Tenant, PlatformAdmin
from app.schemas.access import AccessRoleWrite, AccessUserRoleUpdate, AccessUserRead
from app.api.routes.recruitment import row as recruitment_row

router = APIRouter(prefix="/platform/tenants/{tenant_id}/modules", tags=["platform module oversight"], dependencies=[Depends(get_current_admin)])


async def tenant_exists(tenant_id: uuid.UUID, session: AsyncSession = Depends(get_platform_db)):
    if await session.get(Tenant, tenant_id) is None:
        raise HTTPException(404, "Workspace not found")


@router.get("/access/roles", dependencies=[Depends(tenant_exists)])
async def access_roles(tenant_id: uuid.UUID, session: AsyncSession = Depends(get_platform_db)):
    await access.ensure_system_roles(session, tenant_id)
    return await access.list_roles(session, tenant_id)


@router.get("/access/permissions", dependencies=[Depends(tenant_exists)])
async def access_permissions(tenant_id: uuid.UUID):
    return [{"key": p.key, "label": p.label, "group": p.group} for p in CATALOG]


@router.get("/access/users", response_model=list[AccessUserRead], dependencies=[Depends(tenant_exists)])
async def access_users(tenant_id: uuid.UUID, session: AsyncSession = Depends(get_platform_db)):
    return await access.list_users(session, tenant_id)


@router.post("/access/roles", status_code=201, dependencies=[Depends(tenant_exists)])
async def access_create_role(tenant_id: uuid.UUID, payload: AccessRoleWrite, session: AsyncSession = Depends(get_platform_db)):
    return await access.create_role(session, tenant_id, payload)


@router.patch("/access/roles/{identity}", dependencies=[Depends(tenant_exists)])
async def access_update_role(tenant_id: uuid.UUID, identity: uuid.UUID, payload: AccessRoleWrite, session: AsyncSession = Depends(get_platform_db)):
    return await access.update_role(session, tenant_id, identity, payload)


@router.delete("/access/roles/{identity}", status_code=204, dependencies=[Depends(tenant_exists)])
async def access_delete_role(tenant_id: uuid.UUID, identity: uuid.UUID, session: AsyncSession = Depends(get_platform_db)):
    await access.delete_role(session, tenant_id, identity)


@router.patch("/access/users/{identity}", response_model=AccessUserRead, dependencies=[Depends(tenant_exists)])
async def access_assign_role(tenant_id: uuid.UUID, identity: uuid.UUID, payload: AccessUserRoleUpdate, session: AsyncSession = Depends(get_platform_db), admin: PlatformAdmin = Depends(get_current_admin)):
    # The service changes only the target user and retains the last-owner safeguard.
    return await access.set_user_role(session, SimpleNamespace(tenant_id=tenant_id, role="OWNER", id=admin.id), identity, payload.role)


def observer(tenant_id):
    # Read-only service calls need a visibility scope, not a login or an actor.
    return SimpleNamespace(tenant_id=tenant_id, role="OWNER", employee_id=None)


async def scoped_rows(session, model, tenant_id, company_id):
    return list((await session.scalars(select(model).where(model.tenant_id == tenant_id, model.company_id == company_id).order_by(model.created_at.desc(), model.id))).all())


@router.get("/performance")
async def performance_overview(tenant_id: uuid.UUID, company_id: uuid.UUID, response: Response, session: AsyncSession = Depends(get_platform_db)):
    await company_for_tenant(session, company_id, tenant_id)
    response.headers["Cache-Control"] = "no-store"
    user = observer(tenant_id)
    pips = []
    for pip in await scoped_rows(session, PerformancePIP, tenant_id, company_id):
        reviews = (await session.scalars(select(PerformancePIPReview).where(PerformancePIPReview.tenant_id == tenant_id, PerformancePIPReview.company_id == company_id, PerformancePIPReview.pip_id == pip.id).order_by(PerformancePIPReview.meeting_date))).all()
        pips.append({**performance.row(pip), "reviews": [performance.row(r) for r in reviews]})
    return {
        "reviews": [performance.row(r) for r in await scoped_rows(session, PerformanceCycle, tenant_id, company_id)],
        "appraisals": await performance.list_appraisals(session, user, company_id),
        "report": await performance.dashboard(session, user, company_id),
        "pips": pips,
        "settings": [performance.row(r) for r in await scoped_rows(session, PerformanceSettings, tenant_id, company_id)],
        "scales": [performance.row(r) for r in await scoped_rows(session, RatingScale, tenant_id, company_id)],
        "competencies": [performance.row(r) for r in await scoped_rows(session, Competency, tenant_id, company_id)],
    }


@router.get("/performance/appraisals/{identity}")
async def performance_detail(tenant_id: uuid.UUID, company_id: uuid.UUID, identity: uuid.UUID, response: Response, session: AsyncSession = Depends(get_platform_db)):
    await company_for_tenant(session, company_id, tenant_id)
    record = await performance.detail(session, observer(tenant_id), identity)
    if record["company_id"] != str(company_id):
        raise HTTPException(404, "Review not found in this company")
    response.headers["Cache-Control"] = "no-store"
    return record


@router.get("/performance/export")
async def performance_export(tenant_id: uuid.UUID, company_id: uuid.UUID, session: AsyncSession = Depends(get_platform_db)):
    report = await performance.dashboard(session, observer(tenant_id), company_id)
    stream = io.StringIO()
    writer = csv.writer(stream)
    fields = ("employee_name", "department_name", "branch_name", "manager_name", "cycle", "status", "score", "rating")
    writer.writerow(("Employee", "Department", "Branch", "Manager", "Review", "Status", "Score", "Rating"))
    def safe(value):
        text = str(value) if value is not None else ""
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
    for record in report["records"]:
        writer.writerow([safe(record.get(key)) for key in fields])
    return Response(stream.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8", headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="performance.csv"'})


@router.get("/recruitment")
async def recruitment_overview(tenant_id: uuid.UUID, company_id: uuid.UUID, response: Response, session: AsyncSession = Depends(get_platform_db)):
    await company_for_tenant(session, company_id, tenant_id)
    response.headers["Cache-Control"] = "no-store"
    return {key: [recruitment_row(r) for r in await scoped_rows(session, model, tenant_id, company_id)] for key, model in (
        ("jobs", Vacancy), ("candidates", Candidate), ("applications", Application), ("interviews", Interview), ("offers", Offer), ("events", RecruitmentEvent))}


@router.get("/recruitment/candidates/{identity}/cv")
async def candidate_cv(tenant_id: uuid.UUID, company_id: uuid.UUID, identity: uuid.UUID, session: AsyncSession = Depends(get_platform_db)):
    await company_for_tenant(session, company_id, tenant_id)
    candidate = await session.scalar(select(Candidate).where(Candidate.id == identity, Candidate.tenant_id == tenant_id, Candidate.company_id == company_id))
    if candidate is None:
        raise HTTPException(404, "Candidate not found")
    await session.refresh(candidate, attribute_names=["cv_data"])
    if not candidate.cv_data:
        raise HTTPException(404, "No CV uploaded")
    return Response(candidate.cv_data, media_type="application/octet-stream", headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Disposition": 'attachment; filename="candidate-cv"'})
