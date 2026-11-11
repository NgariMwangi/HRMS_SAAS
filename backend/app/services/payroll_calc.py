from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.models.payroll import EmployeeCompensation, PayrollPack, PayrollPackComponent

ZERO = Decimal("0")


def salary_days(period_start: date, period_end: date, date_joined: date | None) -> int:
    """Full periods retain monthly pay; new starters accrue inclusive calendar days."""
    if date_joined is None or date_joined <= period_start:
        return 30
    return min(30, max(0, (period_end - date_joined).days + 1))


def money(value: Decimal, places: int = 2) -> Decimal:
    quant = Decimal("1").scaleb(-places)
    return Decimal(value).quantize(quant, rounding=ROUND_HALF_UP)


def compensation_gross(row: EmployeeCompensation) -> Decimal:
    return row.computed_gross


def compensation_basic(row: EmployeeCompensation) -> Decimal:
    if row.structure == "GROSS_ONLY":
        return row.computed_gross
    return row.basic_amount or ZERO


def _base_amount(kind: str, gross: Decimal, basic: Decimal, taxable: Decimal, pensionable: Decimal) -> Decimal:
    if kind == "GROSS":
        return gross
    if kind == "BASIC":
        return basic
    if kind == "TAXABLE":
        return taxable
    return pensionable


def _earnings_slice(base: Decimal, floor: Decimal | None, cap: Decimal | None) -> Decimal:
    """Portion of `base` that sits between floor (exclusive start) and cap (inclusive)."""
    lower = floor if floor is not None else ZERO
    upper = min(base, cap) if cap is not None else base
    return max(ZERO, upper - lower)


def _progressive(base: Decimal, component: PayrollPackComponent) -> Decimal:
    tax = ZERO
    for band in component.bands:
        lower = Decimal(band.from_amount)
        upper = Decimal(band.to_amount) if band.to_amount is not None else None
        if base <= lower:
            continue
        slice_end = base if upper is None else min(base, upper)
        slice_amt = slice_end - lower
        if slice_amt > 0:
            tax += slice_amt * (Decimal(band.rate_percent) / Decimal("100"))
    return tax


def apply_component(
    component: PayrollPackComponent,
    *,
    gross: Decimal,
    basic: Decimal,
    taxable: Decimal,
    pensionable: Decimal,
    constants: dict[str, Decimal],
    places: int,
) -> Decimal:
    base = _base_amount(component.base, gross, basic, taxable, pensionable)
    if component.formula_kind == "PERCENT":
        sliced = _earnings_slice(base, component.floor, component.cap)
        rate = Decimal(component.percent or 0) / Decimal("100")
        amount = sliced * rate
        if component.min_amount is not None and sliced > ZERO:
            amount = max(amount, Decimal(component.min_amount))
        if component.amount is not None:
            amount = min(amount, Decimal(component.amount))
    elif component.formula_kind == "FIXED":
        amount = Decimal(component.amount or 0)
    elif component.formula_kind == "PROGRESSIVE_BANDS":
        amount = _progressive(base, component)
        if component.relief_key:
            amount -= constants.get(component.relief_key, ZERO)
        amount = max(amount, ZERO)
    else:
        amount = ZERO
    return money(amount, places)


def pension_relief(
    voluntary: Decimal,
    statutory: Decimal,
    pensionable: Decimal,
    constants: dict[str, Decimal],
) -> Decimal:
    """Tax-deductible share of a voluntary pension.

    The pack limit (Kenya ITA s.22A: lowest of actual, 30% of pensionable pay, 30,000/month)
    covers all employee pension contributions, so statutory pension already uses part of it.
    Packs without `pension_relief_cap` give no relief; the whole contribution is after tax.
    """
    cap = constants.get("pension_relief_cap")
    if cap is None or voluntary <= ZERO:
        return ZERO
    limit = cap
    percent = constants.get("pension_relief_percent")
    if percent is not None:
        limit = min(limit, pensionable * percent / Decimal("100"))
    return max(ZERO, min(voluntary, limit - statutory))


def calculate_payslip(
    pack: PayrollPack,
    compensation: EmployeeCompensation,
    *,
    places: int = 2,
    other_deductions: list[dict] | None = None,
    benefits: list[dict] | None = None,
    payable_days: int = 30,
) -> dict:
    if not 0 <= payable_days <= 30:
        raise ValueError("payable_days must be between 0 and 30")
    monthly_basic = compensation_basic(compensation)
    basic = money(monthly_basic * Decimal(payable_days) / Decimal(30), places)
    benefit_lines = [{**item, "amount": money(Decimal(item["amount"]), places)} for item in benefits or []]
    # Cash benefits (commission, bonus…) are employment income: they raise gross,
    # so PAYE, NSSF, SHIF and housing levy are calculated on them.
    gross = money(
        compensation_gross(compensation) - monthly_basic + basic
        + sum((item["amount"] for item in benefit_lines), ZERO),
        places,
    )
    basic_value = compensation.computed_basic
    taxable = gross
    # Kenya NSSF pensionable earnings are monthly pay (gross), not the basic line alone.
    pensionable = gross
    constants = {row.key: Decimal(row.amount) for row in pack.constants}

    lines: list[dict] = [
        {
            "code": "GROSS",
            "name": "Gross pay",
            "party": "EMPLOYEE",
            "kind": "EARNING",
            "amount": gross,
            "sort_order": 0,
        }
    ]
    if compensation.structure == "BASIC_PLUS_ALLOWANCES":
        lines.append(
            {
                "code": "BASIC",
                "name": "Basic pay" if payable_days == 30 else f"Basic pay ({payable_days}/30 days)",
                "party": "EMPLOYEE",
                "kind": "EARNING",
                "amount": basic,
                "sort_order": 1,
            }
        )
        for index, item in enumerate(compensation.lines, start=2):
            lines.append(
                {
                    "code": f"ALLOWANCE_{index}",
                    "name": item.name,
                    "party": "EMPLOYEE",
                    "kind": "EARNING",
                    "amount": money(item.amount, places),
                    "sort_order": index,
                }
            )
    elif payable_days != 30:
        lines.append({
            "code": "SALARY", "name": f"Salary ({payable_days}/30 days)",
            "party": "EMPLOYEE", "kind": "EARNING", "amount": basic, "sort_order": 1,
        })
    for index, item in enumerate(benefit_lines):
        lines.append(
            {
                "code": "BENEFIT",
                "name": item["name"],
                "party": "EMPLOYEE",
                "kind": "EARNING",
                "amount": item["amount"],
                "sort_order": 50 + index,
                "employee_benefit_id": item["id"],
            }
        )

    voluntary = money(compensation.voluntary_pension or ZERO, places)
    scheme = (compensation.pension_scheme or "").strip()[:80] or "Voluntary pension"
    statutory_pension = ZERO
    pension_done = False

    def apply_voluntary_pension() -> None:
        nonlocal taxable, employee_deductions, pension_done
        pension_done = True
        if voluntary <= ZERO:
            return
        relieved = money(pension_relief(voluntary, statutory_pension, pensionable, constants), places)
        after_tax = voluntary - relieved
        if relieved > ZERO:
            lines.append(
                {
                    "code": "VOL_PENSION",
                    "name": f"{scheme} (before tax)",
                    "party": "EMPLOYEE",
                    "kind": "DEDUCTION",
                    "amount": relieved,
                    "sort_order": 180,
                }
            )
            taxable = max(ZERO, taxable - relieved)
        if after_tax > ZERO:
            lines.append(
                {
                    "code": "VOL_PENSION_POST",
                    "name": f"{scheme} (after tax)",
                    "party": "EMPLOYEE",
                    "kind": "DEDUCTION",
                    "amount": after_tax,
                    "sort_order": 250,
                }
            )
        employee_deductions += voluntary

    employee_deductions = ZERO
    employer_total = ZERO
    for component in pack.components:
        if component.base == "TAXABLE" and not pension_done:
            apply_voluntary_pension()
        amount = apply_component(
            component,
            gross=gross,
            basic=basic,
            taxable=taxable,
            pensionable=pensionable,
            constants=constants,
            places=places,
        )
        if amount <= ZERO and component.formula_kind != "PROGRESSIVE_BANDS":
            if amount == ZERO:
                continue
        kind = "EMPLOYER" if component.party == "EMPLOYER" else "DEDUCTION"
        lines.append(
            {
                "code": component.code,
                "name": component.name,
                "party": component.party,
                "kind": kind,
                "amount": amount,
                "sort_order": 100 + component.sort_order,
            }
        )
        if component.party == "EMPLOYER":
            employer_total += amount
        else:
            employee_deductions += amount
            if component.reduces_taxable:
                taxable = max(ZERO, taxable - amount)
                if component.base == "PENSIONABLE":
                    statutory_pension += amount

    if not pension_done:
        apply_voluntary_pension()

    # Loans, SACCO, welfare etc. come off net pay after tax, and never push net below zero.
    for index, item in enumerate(other_deductions or []):
        available = max(ZERO, gross - employee_deductions)
        amount = money(min(Decimal(item["amount"]), available), places)
        if amount <= ZERO:
            continue
        lines.append(
            {
                "code": "OTHER",
                "name": item["name"],
                "party": "EMPLOYEE",
                "kind": "DEDUCTION",
                "amount": amount,
                "sort_order": 300 + index,
                "employee_deduction_id": item["id"],
            }
        )
        employee_deductions += amount

    taxable = money(taxable, places)
    lines.append(
        {
            "code": "TAXABLE",
            "name": "Taxable pay",
            "party": "EMPLOYEE",
            "kind": "EARNING",
            "amount": taxable,
            "sort_order": 189,
        }
    )

    net = money(gross - employee_deductions, places)
    return {
        "gross": gross,
        "basic": None if basic_value is None else basic,
        "taxable": taxable,
        "employee_deductions": money(employee_deductions, places),
        "employer_contributions": money(employer_total, places),
        "net": net,
        "lines": lines,
    }


def pack_as_of(packs: list[PayrollPack], on: date) -> PayrollPack | None:
    published = [
        row
        for row in packs
        if row.status == "PUBLISHED" and row.effective_from <= on and row.components
    ]
    if not published:
        return None
    published.sort(key=lambda row: (row.effective_from, row.version), reverse=True)
    return published[0]
