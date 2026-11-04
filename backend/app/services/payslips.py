"""Payslip presentation uses persisted payroll amounts, never current tax rules."""
import re
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models import Branch, Company, Currency, Employee, PayrollPayslip, PayrollRun
from app.schemas.payroll import PayslipRead


def split_lines(lines, gross):
    ordered = sorted(lines, key=lambda item: (item.sort_order, str(item.id)))
    def item(line):
        return dict(id=str(line.id), name=line.name, code=line.code, amount=str(line.amount))
    earnings = [item(line) for line in ordered if line.party == "EMPLOYEE" and line.kind == "EARNING" and line.code not in {"GROSS", "TAXABLE"}]
    # Gross-only salaries have a GROSS summary, not a BASIC line. Avoid counting
    # GROSS again alongside basic/allowances/benefits, or TAXABLE as an earning.
    remainder = Decimal(gross) - sum((Decimal(line["amount"]) for line in earnings), Decimal(0))
    if remainder != 0 or not earnings:
        earnings.insert(0, dict(id="salary", code="SALARY", name="Salary" if remainder >= 0 else "Salary adjustment", amount=str(remainder)))
    deductions = [item(line) for line in ordered if line.party == "EMPLOYEE" and line.kind == "DEDUCTION"]
    employer = [item(line) for line in ordered if line.party == "EMPLOYER"]
    taxable = next((str(line.amount) for line in ordered if line.code == "TAXABLE"), None)
    return earnings, deductions, employer, taxable


async def document(session, identity, tenant_id, employee=None):
    query = (select(PayrollPayslip, PayrollRun, Company, Currency, Branch, Employee)
        .join(PayrollRun, PayrollRun.id == PayrollPayslip.run_id)
        .join(Company, Company.id == PayrollPayslip.company_id)
        .join(Currency, Currency.id == PayrollRun.currency_id)
        .join(Branch, Branch.id == PayrollRun.branch_id)
        .outerjoin(Employee, (Employee.id == PayrollPayslip.employee_id) & (Employee.company_id == Company.id))
        .options(selectinload(PayrollPayslip.lines))
        .where(PayrollPayslip.id == identity, Company.tenant_id == tenant_id,
            PayrollRun.company_id == Company.id, Branch.company_id == Company.id))
    if employee is not None:
        query = query.where(PayrollPayslip.employee_id == employee.id, Company.id == employee.company_id, PayrollRun.status == "APPROVED")
    result = (await session.execute(query)).first()
    if result is None:
        raise HTTPException(404, "Payslip not found")
    slip, run, company, currency, branch, record = result
    earnings, deductions, employer, taxable = split_lines(slip.lines, slip.gross)
    number = re.sub(r"[^A-Za-z0-9_-]", "-", slip.employee_number or "employee")[:60]
    data = dict(id=str(slip.id), employee_id=str(slip.employee_id), employee_name=slip.employee_name,
        employee_number=slip.employee_number, company_name=company.name, company_legal_name=company.legal_name,
        pin_number=record.pin_number if record else None, shif_no=record.shif_no if record else None,
        nssf_no=record.nssf_no if record else None,
        company_email=company.email, company_phone=company.phone, branch_name=branch.name,
        period_start=run.period_start.isoformat(), period_end=run.period_end.isoformat(), status=run.status,
        currency_code=currency.code, decimal_places=currency.decimal_places,
        gross=str(slip.gross), employee_deductions=str(slip.employee_deductions), net=str(slip.net),
        employer_contributions=str(slip.employer_contributions), taxable=taxable,
        earnings=earnings, deductions=deductions, employer=employer,
        reference=f"PS-{slip.id.hex[:12].upper()}",
        filename=f"payslip-{number}-{run.period_start.isoformat()}-{run.period_end.isoformat()}.pdf")
    return {**PayslipRead.model_validate(slip).model_dump(mode="json"), **data}
