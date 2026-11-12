import calendar
from datetime import date, datetime, timezone
from decimal import Decimal
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder as _encode
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.org import branch_for_company, company_for_tenant as _company_for_tenant
from app.models import Branch, Company, Country, Currency, Employee, EmployeeBenefit, PayrollPayslip, PayrollPayslipLine, PayrollRun
from app.models.workforce_payments import Consultant, ConsultantCompensation, ConsultantPay, OvertimeRequest, PaymentRecord
from app.services.payroll_calc import money, salary_days
from app.services.salary_item_types import resolve_type
from app.models import BenefitType


def jsonable_encoder(value):
    return _encode(value, custom_encoder={Decimal: str})


async def company_for_tenant(session, company_id, tenant_id):
    domain_company = session.info.get("domain_company_id")
    if domain_company is not None and str(domain_company) != str(company_id):
        bad("This address is restricted to its company", 403)
    return await _company_for_tenant(session, company_id, tenant_id)


def bad(message, code=400):
    raise HTTPException(code, message)


async def owned(session, model, identity, tenant_id, lock=False):
    query = select(model).where(model.id == identity, model.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is None:
        bad("Record not found", 404)
    await company_for_tenant(session, row.company_id, tenant_id)
    return row


async def company_lock(session, company_id, tenant_id):
    await company_for_tenant(session, company_id, tenant_id)
    await session.scalar(select(Company).where(Company.id == company_id).with_for_update())


async def flush(session):
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "A record with this number, date or payment reference already exists") from exc


async def currency_for_branch(session, branch):
    country = await session.get(Country, branch.country_id)
    currency = await session.get(Currency, branch.currency_id or country.default_currency_id)
    if currency is None:
        bad("Branch currency is not configured")
    return currency


async def save_consultant(session, tenant_id, payload, identity=None):
    row = await owned(session, Consultant, identity, tenant_id) if identity else None
    data = payload.model_dump()
    company_id = row.company_id if row else data.pop("company_id")
    await company_lock(session, company_id, tenant_id)
    new_branch = await branch_for_company(session, data["branch_id"], company_id)
    if row is not None and row.branch_id != new_branch.id:
        has_fees = await session.scalar(select(ConsultantCompensation.id).where(ConsultantCompensation.consultant_id == row.id).limit(1))
        if has_fees:
            old_currency = await currency_for_branch(session, await session.get(Branch, row.branch_id))
            new_currency = await currency_for_branch(session, new_branch)
            if old_currency.id != new_currency.id:
                bad("This consultant has fee history in another currency. Use a new consultant record for the new currency", 409)
    if row is None:
        row = Consultant(tenant_id=tenant_id, company_id=company_id)
        session.add(row)
    for key, value in data.items():
        setattr(row, key, value)
    await flush(session)
    return jsonable_encoder(row)


async def add_fee(session, tenant_id, consultant_id, payload):
    person = await owned(session, Consultant, consultant_id, tenant_id)
    await company_lock(session, person.company_id, tenant_id)
    row = ConsultantCompensation(tenant_id=tenant_id, company_id=person.company_id,
                                consultant_id=person.id, **payload.model_dump())
    session.add(row)
    await flush(session)
    return jsonable_encoder(row)


async def calculate_consultant(session, tenant_id, consultant_id, month):
    person = await owned(session, Consultant, consultant_id, tenant_id)
    await company_lock(session, person.company_id, tenant_id)
    start = month.replace(day=1)
    end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
    if person.status != "ACTIVE" or person.start_date > end or (person.end_date and person.end_date < start):
        bad("Consultant is not active during this month")
    fee = await session.scalar(select(ConsultantCompensation).where(
        ConsultantCompensation.consultant_id == person.id,
        ConsultantCompensation.effective_from <= end,
        or_(ConsultantCompensation.effective_to.is_(None), ConsultantCompensation.effective_to >= end),
    ).order_by(ConsultantCompensation.effective_from.desc()).limit(1))
    if fee is None:
        bad("No fee is configured for this month")
    row = await session.scalar(select(ConsultantPay).where(ConsultantPay.consultant_id == person.id, ConsultantPay.period_start == start).with_for_update())
    if row and row.status != "DRAFT":
        bad("Approved consultant pay cannot be recalculated", 409)
    branch = await branch_for_company(session, person.branch_id, person.company_id)
    currency = await currency_for_branch(session, branch)
    days = 30
    if person.prorate_payroll:
        eligible_end = min(end, person.end_date) if person.end_date else end
        days = salary_days(start, eligible_end, person.start_date)
        if person.end_date and person.end_date < end:
            days = min(30, max(0, (eligible_end - max(start, person.start_date)).days + 1))
    gross = money((fee.monthly_fee + fee.other_allowances) * Decimal(days) / 30, currency.decimal_places)
    tax = money(gross * person.withholding_rate / 100, currency.decimal_places)
    if gross <= 0:
        bad("Consultant has no payable fee")
    if row is None:
        row = ConsultantPay(tenant_id=tenant_id, company_id=person.company_id, consultant_id=person.id, period_start=start, status="DRAFT")
        session.add(row)
    for key, value in dict(branch_id=branch.id, compensation_id=fee.id, currency_id=currency.id,
        period_end=end, recipient_name=" ".join(filter(None, [person.first_name, person.other_names, person.last_name])),
        gross=gross, withholding_rate=person.withholding_rate, withholding_tax=tax, net=gross-tax, payable_days=days).items():
        setattr(row, key, value)
    await flush(session)
    return jsonable_encoder(row)


async def approve_consultant(session, tenant_id, identity, actor_id):
    row = await owned(session, ConsultantPay, identity, tenant_id, lock=True)
    if row.status != "APPROVED":
        row.status = "APPROVED"
        row.approved_by_id = actor_id
        row.approved_at = datetime.now(timezone.utc)
        await flush(session)
    return jsonable_encoder(row)


async def create_overtime(session, tenant_id, payload, actor_id):
    person = await session.get(Employee, payload.employee_id)
    if person is None:
        bad("Employee not found", 404)
    await company_lock(session, person.company_id, tenant_id)
    await session.refresh(person)
    if person.status != "ACTIVE":
        bad("Overtime requires an active employee")
    if person.date_joined and min(payload.worked_dates) < person.date_joined:
        bad("Worked dates cannot precede the joining date")
    dates = {value.isoformat() for value in payload.worked_dates}
    existing = (await session.scalars(select(OvertimeRequest).where(OvertimeRequest.employee_id == person.id,
        OvertimeRequest.status.in_(["PENDING", "APPROVED"])))).all()
    if any(dates.intersection(row.worked_dates) for row in existing):
        bad("An overtime request already covers one of these worked dates", 409)
    branch = await session.get(Branch, person.branch_id)
    currency = await currency_for_branch(session, branch)
    amount = money(payload.days * payload.daily_rate, currency.decimal_places)
    if amount <= 0:
        bad("Overtime amount must be positive after rounding")
    row = OvertimeRequest(tenant_id=tenant_id, company_id=person.company_id, employee_id=person.id,
        branch_id=branch.id, currency_id=currency.id,
        worked_dates=sorted(dates), days=payload.days, daily_rate=payload.daily_rate, amount=amount,
        payroll_month=payload.month, reason=payload.reason, submitted_by_id=actor_id, status="PENDING")
    session.add(row)
    await flush(session)
    return jsonable_encoder(row)


async def review_overtime(session, tenant_id, identity, payload, actor_id):
    row = await owned(session, OvertimeRequest, identity, tenant_id, lock=True)
    if row.status == payload.decision:
        return jsonable_encoder(row)
    if row.status != "PENDING":
        bad("Only pending overtime can be reviewed", 409)
    person = await session.get(Employee, row.employee_id)
    await company_lock(session, row.company_id, tenant_id)
    # A draft payroll must be rerun; an approved payroll is closed to new earnings.
    closed = await session.scalar(select(PayrollRun.id).where(PayrollRun.company_id == row.company_id,
        PayrollRun.branch_id == person.branch_id, PayrollRun.period_start <= row.payroll_month,
        PayrollRun.period_end >= row.payroll_month, PayrollRun.status == "APPROVED"))
    if payload.decision == "APPROVED":
        if closed:
            bad("Payroll is already approved for this month. Reopen it before approving overtime", 409)
        if person.status != "ACTIVE":
            bad("Employee is no longer active")
        current_currency = await currency_for_branch(session, await session.get(Branch, person.branch_id))
        if current_currency.id != row.currency_id:
            bad("Employee currency changed. Cancel this request and enter overtime in the new currency", 409)
        kind = await resolve_type(session, BenefitType, row.company_id, None, "Overtime")
        benefit = EmployeeBenefit(company_id=row.company_id, employee_id=row.employee_id, benefit_type_id=kind.id,
            frequency="ONE_OFF", amount=row.amount, start_date=row.payroll_month, end_date=None,
            note=f"Overtime {row.id.hex[:8]}", status="ACTIVE")
        session.add(benefit)
        await session.flush()
        row.employee_benefit_id = benefit.id
    row.status = payload.decision
    row.reviewed_by_id = actor_id
    row.reviewed_at = datetime.now(timezone.utc)
    row.review_notes = payload.note
    await flush(session)
    return jsonable_encoder(row)


async def target_details(session, tenant_id, kind, identity, month, lock=False):
    """Return the target, snapshot name, currency and permitted payment amount."""
    if kind == "CONSULTANT":
        row = await owned(session, ConsultantPay, identity, tenant_id, lock=lock)
        if row.status != "APPROVED":
            bad("Approve consultant pay before recording payment")
        return row, row.recipient_name, row.currency_id, row.net, row.period_start, "consultant_pay_id"
    if kind == "PAYROLL":
        slip = await session.get(PayrollPayslip, identity)
        if slip is None:
            bad("Payslip not found", 404)
        await company_for_tenant(session, slip.company_id, tenant_id)
        run = await session.scalar(select(PayrollRun).where(PayrollRun.id == slip.run_id).with_for_update())
        if run.status != "APPROVED":
            bad("Approve payroll before recording payment")
        return slip, slip.employee_name, run.currency_id, slip.net, run.period_start, "payslip_id"
    row = await session.scalar(select(EmployeeBenefit).where(EmployeeBenefit.id == identity).with_for_update())
    if row is None:
        bad("Benefit not found", 404)
    await company_for_tenant(session, row.company_id, tenant_id)
    if row.status != "ACTIVE":
        bad("Benefit is stopped")
    period = month.replace(day=1)
    end = period.replace(day=calendar.monthrange(period.year, period.month)[1])
    if row.start_date > end or (row.end_date and row.end_date < period) or (row.frequency == "ONE_OFF" and row.start_date < period):
        bad("Benefit is not scheduled for this month")
    already_in_payroll = await session.scalar(select(PayrollPayslipLine.id).join(PayrollPayslip).join(PayrollRun).where(
        PayrollPayslipLine.employee_benefit_id == row.id, PayrollRun.period_start <= end, PayrollRun.period_end >= period))
    if already_in_payroll:
        bad("Benefit is already included in payroll. Record payment against its payslip", 409)
    person = await session.get(Employee, row.employee_id)
    currency = await currency_for_branch(session, await session.get(Branch, person.branch_id))
    return row, f"{person.first_name} {person.last_name}", currency.id, row.amount, period, "benefit_id"


async def record_payment(session, tenant_id, payload, actor_id):
    model = {"PAYROLL": PayrollPayslip, "CONSULTANT": ConsultantPay, "BENEFIT": EmployeeBenefit}[payload.kind]
    target = await session.get(model, payload.target_id)
    if target is None:
        bad("Payable record not found", 404)
    await company_lock(session, target.company_id, tenant_id)
    row, name, currency_id, due, period, field = await target_details(session, tenant_id, payload.kind, payload.target_id, payload.month, True)
    if payload.month.replace(day=1) != period.replace(day=1):
        bad("Payment month does not match this record")
    currency = await session.get(Currency, currency_id)
    if money(payload.amount, currency.decimal_places) != payload.amount:
        bad("Amount has more decimal places than the payment currency supports")
    paid = await session.scalar(select(func.coalesce(func.sum(PaymentRecord.amount), 0)).where(
        getattr(PaymentRecord, field) == row.id, PaymentRecord.period_start == period, PaymentRecord.status == "POSTED"))
    if payload.amount > due - paid:
        bad("Payment exceeds the outstanding balance", 409)
    if payload.kind == "BENEFIT" and payload.amount != due - paid:
        bad("A benefit paid outside payroll must be settled in full")
    payment = PaymentRecord(tenant_id=tenant_id, company_id=row.company_id, **{field: row.id},
        period_start=period, currency_id=currency_id, recipient_name=name, amount=payload.amount,
        paid_on=payload.paid_on, method=payload.method, reference=payload.reference, note=payload.note,
        status="POSTED", recorded_by_id=actor_id)
    session.add(payment)
    await flush(session)
    return jsonable_encoder(payment)


async def void_payment(session, tenant_id, identity, reason, actor_id):
    row = await owned(session, PaymentRecord, identity, tenant_id, lock=True)
    if row.benefit_id is not None and row.status == "POSTED":
        accounted = await session.scalar(select(PayrollPayslipLine.id).join(PayrollPayslip).join(PayrollRun).where(
            PayrollPayslipLine.employee_benefit_id == row.benefit_id, PayrollRun.status == "APPROVED",
            PayrollRun.period_start <= row.period_start, PayrollRun.period_end >= row.period_start).limit(1))
        if accounted is not None:
            bad("Reopen this month's payroll before voiding a benefit payment it has accounted for", 409)
    row.status = "VOID"
    if row.voided_at is None:
        row.void_reason = reason
        row.voided_at = datetime.now(timezone.utc)
        row.voided_by_id = actor_id
    await flush(session)
    return jsonable_encoder(row)
