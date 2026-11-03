import uuid
from typing import Literal
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_tenant_db, get_current_admin, get_platform_db
from app.api.org import company_for_tenant
from app.api.access_control import require_access
from app.models import User
from app.models.appraisals import AppraisalReview, AppraisalTemplate, EmployeeAppraisal
from app.schemas.appraisals import TemplateInput, ReviewInput, PreparationInput, Version, AssessmentInput, DiscussionInput, ActionInput, DevelopmentUpdate
from app.services import appraisals as service
from app.services.access import require_permission

router = APIRouter(prefix="/performance/simple", tags=["appraisals"])
Session = Depends(get_tenant_db)
Actor = Depends(get_current_user)


@router.get("/people")
async def people(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return await service.people(session, user, company_id)


@router.get("/templates")
async def templates(company_id: uuid.UUID, response: Response, session: AsyncSession = Session, user: User = Actor):
    await require_permission(session, user, "performance.manage_cycles")
    await company_for_tenant(session, company_id, user.tenant_id)
    response.headers["Cache-Control"] = "no-store"
    return [service.row(t) for t in (await session.scalars(select(AppraisalTemplate).where(AppraisalTemplate.company_id == company_id, AppraisalTemplate.tenant_id == user.tenant_id).order_by(AppraisalTemplate.name))).all()]


@router.post("/templates", status_code=201, dependencies=[Depends(require_access("performance.manage_cycles"))])
async def create_template(company_id: uuid.UUID, payload: TemplateInput, session: AsyncSession = Session, user: User = Actor):
    return await service.save_template(session, user, company_id, payload)


@router.put("/templates/{identity}", dependencies=[Depends(require_access("performance.manage_cycles"))])
async def edit_template(identity: uuid.UUID, company_id: uuid.UUID, payload: TemplateInput, session: AsyncSession = Session, user: User = Actor):
    return await service.save_template(session, user, company_id, payload, identity)


@router.get("/reviews")
async def reviews(company_id: uuid.UUID, response: Response, session: AsyncSession = Session, user: User = Actor):
    await require_permission(session, user, "performance.manage_cycles", "performance.view_all")
    await company_for_tenant(session, company_id, user.tenant_id)
    response.headers["Cache-Control"] = "no-store"
    return [service.row(r) for r in (await session.scalars(select(AppraisalReview).where(AppraisalReview.company_id == company_id, AppraisalReview.tenant_id == user.tenant_id).order_by(AppraisalReview.created_at.desc()))).all()]


@router.post("/reviews", status_code=201, dependencies=[Depends(require_access("performance.manage_cycles"))])
async def create_review(company_id: uuid.UUID, payload: ReviewInput, session: AsyncSession = Session, user: User = Actor):
    return await service.save_review(session, user, company_id, payload)


@router.put("/reviews/{identity}", dependencies=[Depends(require_access("performance.manage_cycles"))])
async def edit_review(identity: uuid.UUID, company_id: uuid.UUID, payload: ReviewInput, session: AsyncSession = Session, user: User = Actor):
    return await service.save_review(session, user, company_id, payload, identity)


@router.post("/reviews/{identity}/publish", dependencies=[Depends(require_access("performance.manage_cycles"))])
async def publish(identity: uuid.UUID, payload: Version, session: AsyncSession = Session, user: User = Actor):
    return await service.publish(session, user, identity, payload)


@router.get("/records")
async def records(company_id: uuid.UUID, response: Response, scope: Literal["my", "team", "manage"] = "my", review_id: uuid.UUID | None = None, employee_id: uuid.UUID | None = None, session: AsyncSession = Session, user: User = Actor):
    response.headers["Cache-Control"] = "no-store"
    return await service.list_records(session, user, company_id, scope, review_id, employee_id)


@router.get("/records/{identity}")
async def record(identity: uuid.UUID, response: Response, session: AsyncSession = Session, user: User = Actor):
    response.headers["Cache-Control"] = "no-store"
    return await service.present(session, user, await service.get(session, user, EmployeeAppraisal, identity))


@router.put("/records/{identity}/prepare", dependencies=[Depends(require_access("performance.manage_cycles", "performance.assess_team"))])
async def prepare(identity: uuid.UUID, payload: PreparationInput, session: AsyncSession = Session, user: User = Actor):
    return await service.prepare(session, user, identity, payload)


@router.put("/records/{identity}/self-review", dependencies=[Depends(require_access("performance.self_assess"))])
async def self_review(identity: uuid.UUID, payload: AssessmentInput, session: AsyncSession = Session, user: User = Actor):
    return await service.assess(session, user, identity, payload)


@router.put("/records/{identity}/manager-review", dependencies=[Depends(require_access("performance.assess_team"))])
async def manager_review(identity: uuid.UUID, payload: AssessmentInput, session: AsyncSession = Session, user: User = Actor):
    return await service.assess(session, user, identity, payload, manager=True)


@router.put("/records/{identity}/discussion", dependencies=[Depends(require_access("performance.assess_team"))])
async def discussion(identity: uuid.UUID, payload: DiscussionInput, session: AsyncSession = Session, user: User = Actor):
    return await service.discussion(session, user, identity, payload)


@router.post("/records/{identity}/action", dependencies=[Depends(require_access("performance.view_own", "performance.assess_team", "performance.finalize", "performance.reopen_appraisal"))])
async def action(identity: uuid.UUID, payload: ActionInput, session: AsyncSession = Session, user: User = Actor):
    return await service.act(session, user, identity, payload)


@router.patch("/records/{identity}/development", dependencies=[Depends(require_access("performance.view_own", "performance.assess_team", "performance.finalize"))])
async def development(identity: uuid.UUID, payload: DevelopmentUpdate, session: AsyncSession = Session, user: User = Actor):
    return await service.development(session, user, identity, payload)


@router.get("/export")
async def export(company_id: uuid.UUID, session: AsyncSession = Session, user: User = Actor):
    return Response(await service.export(session, user, company_id), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="appraisals.csv"', "Cache-Control": "no-store"})


@router.get("/results")
async def results(company_id: uuid.UUID, response: Response, session: AsyncSession = Session, user: User = Actor):
    response.headers["Cache-Control"] = "no-store"
    return await service.results(session, user, company_id)


platform_router = APIRouter(prefix="/platform/tenants/{tenant_id}/modules/simple-appraisals", tags=["platform appraisal oversight"], dependencies=[Depends(get_current_admin)])


@platform_router.get("")
async def oversight(tenant_id: uuid.UUID, company_id: uuid.UUID, response: Response, session: AsyncSession = Depends(get_platform_db)):
    from app.api.routes.platform_modules import observer
    response.headers["Cache-Control"] = "no-store"
    return await service.list_records(session, observer(tenant_id), company_id, "manage")
