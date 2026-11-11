import uuid
from datetime import date
from fastapi import APIRouter, Depends
from app.services.workforce_payments import jsonable_encoder
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_admin, get_current_user, get_platform_db, get_tenant_db
from app.services.workforce_payments import company_for_tenant
from app.models import Branch, Currency, Employee, EmployeeBenefit, PayrollPayslip, PayrollPayslipLine, PayrollRun, User
from app.models.workforce_payments import Consultant, ConsultantCompensation, ConsultantPay, OvertimeRequest, PaymentRecord
from app.schemas.workforce_payments import ConsultantCreate, ConsultantWrite, DecisionWrite, FeeWrite, MonthWrite, OvertimeWrite, PaymentWrite, VoidWrite
from app.services import workforce_payments as service
from app.services.access import require_permission


async def tenant_context(session: AsyncSession = Depends(get_tenant_db), user: User = Depends(get_current_user)):
    await require_permission(session, user, "payroll.manage")
    return session, user.tenant_id, user.id


async def platform_context(tenant_id: uuid.UUID, session: AsyncSession = Depends(get_platform_db), admin=Depends(get_current_admin)):
    return session, tenant_id, None


def build_router(platform=False):
    router = APIRouter(prefix=("/platform/tenants/{tenant_id}" if platform else "") + "/workforce", tags=["workforce payments"])
    context = platform_context if platform else tenant_context

    @router.get("/currencies")
    async def currencies(ctx=Depends(context)):
        return jsonable_encoder((await ctx[0].scalars(select(Currency).order_by(Currency.code))).all())

    @router.get("/consultants")
    async def consultants(company_id: uuid.UUID, ctx=Depends(context)):
        session, tenant_id, _ = ctx
        await company_for_tenant(session, company_id, tenant_id)
        rows = (await session.scalars(select(Consultant).where(Consultant.company_id == company_id,
            Consultant.tenant_id == tenant_id).order_by(Consultant.first_name, Consultant.id))).all()
        return jsonable_encoder(rows)

    @router.post("/consultants", status_code=201)
    async def create_consultant(payload: ConsultantCreate, ctx=Depends(context)):
        return await service.save_consultant(ctx[0], ctx[1], payload)

    @router.put("/consultants/{identity}")
    async def update_consultant(identity: uuid.UUID, payload: ConsultantWrite, ctx=Depends(context)):
        return await service.save_consultant(ctx[0], ctx[1], payload, identity)

    @router.get("/consultants/{identity}/fees")
    async def fees(identity: uuid.UUID, ctx=Depends(context)):
        session, tenant_id, _ = ctx
        await service.owned(session, Consultant, identity, tenant_id)
        return jsonable_encoder((await session.scalars(select(ConsultantCompensation).where(
            ConsultantCompensation.consultant_id == identity).order_by(ConsultantCompensation.effective_from.desc()))).all())

    @router.post("/consultants/{identity}/fees", status_code=201)
    async def create_fee(identity: uuid.UUID, payload: FeeWrite, ctx=Depends(context)):
        return await service.add_fee(ctx[0], ctx[1], identity, payload)

    @router.post("/consultants/{identity}/calculate")
    async def calculate(identity: uuid.UUID, payload: MonthWrite, ctx=Depends(context)):
        return await service.calculate_consultant(ctx[0], ctx[1], identity, payload.month)

    @router.get("/consultant-pay")
    async def consultant_pay(company_id: uuid.UUID, month: date, ctx=Depends(context)):
        session, tenant_id, _ = ctx
        await company_for_tenant(session, company_id, tenant_id)
        return jsonable_encoder((await session.scalars(select(ConsultantPay).where(ConsultantPay.company_id == company_id,
            ConsultantPay.tenant_id == tenant_id, ConsultantPay.period_start == month.replace(day=1)).order_by(ConsultantPay.recipient_name))).all())

    @router.post("/consultant-pay/{identity}/approve")
    async def approve(identity: uuid.UUID, ctx=Depends(context)):
        return await service.approve_consultant(ctx[0], ctx[1], identity, ctx[2])

    @router.get("/overtime")
    async def overtime(company_id: uuid.UUID, month: date, ctx=Depends(context)):
        session, tenant_id, _ = ctx
        await company_for_tenant(session, company_id, tenant_id)
        rows = (await session.execute(select(OvertimeRequest, Employee.first_name, Employee.last_name).join(Employee,
            Employee.id == OvertimeRequest.employee_id).where(OvertimeRequest.company_id == company_id,
            OvertimeRequest.tenant_id == tenant_id, OvertimeRequest.payroll_month == month.replace(day=1)).order_by(OvertimeRequest.created_at.desc()))).all()
        return [{**jsonable_encoder(row), "employee_name": f"{first} {last}"} for row, first, last in rows]

    @router.post("/overtime", status_code=201)
    async def create_overtime(payload: OvertimeWrite, ctx=Depends(context)):
        return await service.create_overtime(ctx[0], ctx[1], payload, ctx[2])

    @router.post("/overtime/{identity}/review")
    async def review_overtime(identity: uuid.UUID, payload: DecisionWrite, ctx=Depends(context)):
        return await service.review_overtime(ctx[0], ctx[1], identity, payload, ctx[2])

    @router.get("/payments")
    async def payments(company_id: uuid.UUID, month: date, ctx=Depends(context)):
        session, tenant_id, _ = ctx
        await company_for_tenant(session, company_id, tenant_id)
        return jsonable_encoder((await session.scalars(select(PaymentRecord).where(PaymentRecord.company_id == company_id,
            PaymentRecord.tenant_id == tenant_id, PaymentRecord.period_start == month.replace(day=1)).order_by(PaymentRecord.created_at.desc()))).all())

    @router.get("/payment-targets")
    async def payment_targets(company_id: uuid.UUID, month: date, ctx=Depends(context)):
        session, tenant_id, _ = ctx
        await company_for_tenant(session, company_id, tenant_id)
        period = month.replace(day=1)
        consultant_rows = (await session.scalars(select(ConsultantPay).where(ConsultantPay.company_id == company_id,
            ConsultantPay.tenant_id == tenant_id, ConsultantPay.period_start == period, ConsultantPay.status == "APPROVED"))).all()
        employee_rows = (await session.execute(select(PayrollPayslip, PayrollRun.currency_id).join(PayrollRun).where(
            PayrollPayslip.company_id == company_id, PayrollRun.period_start == period, PayrollRun.status == "APPROVED"))).all()
        targets = [dict(id=row.id, kind="CONSULTANT", name=row.recipient_name, due=row.net, currency_id=row.currency_id) for row in consultant_rows]
        targets += [dict(id=row.id, kind="PAYROLL", name=row.employee_name, due=row.net, currency_id=currency_id) for row, currency_id in employee_rows]
        import calendar
        end = period.replace(day=calendar.monthrange(period.year, period.month)[1])
        benefit_rows = (await session.execute(select(EmployeeBenefit, Employee).join(Employee,
            EmployeeBenefit.employee_id == Employee.id).where(EmployeeBenefit.company_id == company_id,
            EmployeeBenefit.status == "ACTIVE", EmployeeBenefit.start_date <= end,
            or_(EmployeeBenefit.frequency == "RECURRING", EmployeeBenefit.start_date >= period),
            or_(EmployeeBenefit.end_date.is_(None), EmployeeBenefit.end_date >= period)))).all()
        for benefit, person in benefit_rows:
            included = await session.scalar(select(PayrollPayslipLine.id).join(PayrollPayslip).join(PayrollRun).where(
                PayrollPayslipLine.employee_benefit_id == benefit.id, PayrollRun.period_start <= end, PayrollRun.period_end >= period).limit(1))
            if included is None:
                currency = await service.currency_for_branch(session, await session.get(Branch, person.branch_id))
                targets.append(dict(id=benefit.id, kind="BENEFIT", name=f"{person.first_name} {person.last_name} - benefit {benefit.start_date}", due=benefit.amount, currency_id=currency.id))
        payments = (await session.scalars(select(PaymentRecord).where(PaymentRecord.company_id == company_id,
            PaymentRecord.period_start == period, PaymentRecord.status == "POSTED"))).all()
        for target in targets:
            target["paid"] = sum((p.amount for p in payments if (p.payslip_id or p.consultant_pay_id or p.benefit_id) == target["id"]), start=0)
            target["outstanding"] = target["due"] - target["paid"]
        return jsonable_encoder(targets)

    @router.post("/payments", status_code=201)
    async def create_payment(payload: PaymentWrite, ctx=Depends(context)):
        return await service.record_payment(ctx[0], ctx[1], payload, ctx[2])

    @router.post("/payments/{identity}/void")
    async def void_payment(identity: uuid.UUID, payload: VoidWrite, ctx=Depends(context)):
        return await service.void_payment(ctx[0], ctx[1], identity, payload.reason, ctx[2])

    return router


router = build_router()
platform_router = build_router(platform=True)
