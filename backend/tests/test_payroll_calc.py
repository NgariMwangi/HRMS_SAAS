from decimal import Decimal

from app.models.payroll import (
    EmployeeCompensation,
    EmployeePayLine,
    PayrollPack,
    PayrollPackBand,
    PayrollPackComponent,
    PayrollPackConstant,
)
from app.services.payroll_calc import calculate_payslip

D = Decimal


def _tier(code: str, name: str, party: str, *, floor=None, cap, amount, order: int, reduces: bool = False) -> PayrollPackComponent:
    row = PayrollPackComponent(
        code=code,
        name=name,
        party=party,
        formula_kind="PERCENT",
        base="PENSIONABLE",
        percent=D("6"),
        floor=floor,
        cap=cap,
        amount=amount,
        relief_key=None,
        reduces_taxable=reduces,
        sort_order=order,
    )
    row.bands = []
    return row


def _kenya_nssf_pack() -> PayrollPack:
    pack = PayrollPack()
    pack.constants = []
    pack.components = [
        _tier("NSSF_I", "NSSF Tier I", "EMPLOYEE", cap=D("9000"), amount=D("540"), order=10, reduces=True),
        _tier("NSSF_I_ER", "NSSF Tier I (employer)", "EMPLOYER", cap=D("9000"), amount=D("540"), order=11),
        _tier(
            "NSSF_II",
            "NSSF Tier II",
            "EMPLOYEE",
            floor=D("9000"),
            cap=D("108000"),
            amount=D("5940"),
            order=12,
            reduces=True,
        ),
        _tier(
            "NSSF_II_ER",
            "NSSF Tier II (employer)",
            "EMPLOYER",
            floor=D("9000"),
            cap=D("108000"),
            amount=D("5940"),
            order=13,
        ),
    ]
    return pack


def _gross(amount: str, *, pension: str | None = None, scheme: str | None = None) -> EmployeeCompensation:
    row = EmployeeCompensation(
        structure="GROSS_ONLY",
        gross_amount=D(amount),
        basic_amount=None,
        voluntary_pension=None if pension is None else D(pension),
        pension_scheme=scheme,
    )
    row.lines = []
    return row


def _basic_plus(basic: str, allowances: list[tuple[str, str]]) -> EmployeeCompensation:
    row = EmployeeCompensation(
        structure="BASIC_PLUS_ALLOWANCES",
        gross_amount=None,
        basic_amount=D(basic),
    )
    row.lines = [
        EmployeePayLine(kind="ALLOWANCE", name=name, amount=D(amount), sort_order=index)
        for index, (name, amount) in enumerate(allowances)
    ]
    return row


def _line(result: dict, code: str) -> Decimal | None:
    for item in result["lines"]:
        if item["code"] == code:
            return item["amount"]
    return None


def test_kenya_nssf_tiers_and_employer_match() -> None:
    pack = _kenya_nssf_pack()
    cases = [
        ("5000", "300.00", None),
        ("9000", "540.00", None),
        ("9001", "540.00", "0.06"),
        ("100000", "540.00", "5460.00"),
        ("108000", "540.00", "5940.00"),
        ("200000", "540.00", "5940.00"),
    ]
    for gross, tier_i, tier_ii in cases:
        result = calculate_payslip(pack, _gross(gross))
        assert _line(result, "NSSF_I") == D(tier_i), gross
        assert _line(result, "NSSF_I_ER") == D(tier_i), gross
        if tier_ii is None:
            assert _line(result, "NSSF_II") is None, gross
            assert _line(result, "NSSF_II_ER") is None, gross
        else:
            assert _line(result, "NSSF_II") == D(tier_ii), gross
            assert _line(result, "NSSF_II_ER") == D(tier_ii), gross
        nssf = D(tier_i) + (D(tier_ii) if tier_ii else D("0"))
        assert _line(result, "TAXABLE") == D(gross) - nssf, gross


def test_kenya_nssf_uses_gross_when_salary_is_basic_plus_allowances() -> None:
    pack = _kenya_nssf_pack()
    result = calculate_payslip(
        pack,
        _basic_plus("70000", [("Housing", "25000"), ("Transport", "15000")]),
    )
    assert _line(result, "GROSS") == D("110000.00")
    assert _line(result, "NSSF_I") == D("540.00")
    assert _line(result, "NSSF_II") == D("5940.00")
    assert _line(result, "NSSF_I_ER") == D("540.00")
    assert _line(result, "NSSF_II_ER") == D("5940.00")
    assert _line(result, "TAXABLE") == D("103520.00")


def _percent(
    code: str,
    name: str,
    party: str,
    base: str,
    percent: str,
    *,
    reduces: bool = False,
    min_amount: str | None = None,
    order: int,
) -> PayrollPackComponent:
    row = PayrollPackComponent(
        code=code,
        name=name,
        party=party,
        formula_kind="PERCENT",
        base=base,
        percent=D(percent),
        floor=None,
        cap=None,
        amount=None,
        min_amount=None if min_amount is None else D(min_amount),
        relief_key=None,
        reduces_taxable=reduces,
        sort_order=order,
    )
    row.bands = []
    return row


def test_percent_component_is_raised_to_pack_minimum() -> None:
    pack = PayrollPack()
    pack.constants = []
    pack.components = [
        _percent("SHIF", "SHIF", "EMPLOYEE", "GROSS", "2.75", reduces=True, min_amount="300", order=20),
    ]
    cases = [
        ("8000", "300.00"),
        ("10909", "300.00"),
        ("11000", "302.50"),
        ("100000", "2750.00"),
    ]
    for gross, shif in cases:
        result = calculate_payslip(pack, _gross(gross))
        assert _line(result, "SHIF") == D(shif), gross
        assert _line(result, "TAXABLE") == D(gross) - D(shif), gross

    pack.components[0].min_amount = D("500")
    assert _line(calculate_payslip(pack, _gross("8000")), "SHIF") == D("500.00")

    pack.components[0].min_amount = None
    assert _line(calculate_payslip(pack, _gross("8000")), "SHIF") == D("220.00")


def _paye(bands: list[tuple[str, str | None, str]]) -> PayrollPackComponent:
    row = PayrollPackComponent(
        code="PAYE",
        name="PAYE",
        party="EMPLOYEE",
        formula_kind="PROGRESSIVE_BANDS",
        base="TAXABLE",
        percent=None,
        floor=None,
        cap=None,
        amount=None,
        relief_key=None,
        reduces_taxable=False,
        sort_order=90,
    )
    row.bands = [
        PayrollPackBand(
            sort_order=index,
            from_amount=D(from_amount),
            to_amount=None if to_amount is None else D(to_amount),
            rate_percent=D(rate),
        )
        for index, (from_amount, to_amount, rate) in enumerate(bands)
    ]
    return row


KE_PAYE_BANDS = [
    ("0", "24000", "10"),
    ("24000", "32333", "25"),
    ("32333", "500000", "30"),
    ("500000", "800000", "32.5"),
    ("800000", None, "35"),
]


def test_kenya_paye_bands_with_personal_relief() -> None:
    pack = PayrollPack()
    pack.constants = [PayrollPackConstant(key="personal_relief", amount=D("2400"))]
    paye = _paye(KE_PAYE_BANDS)
    paye.relief_key = "personal_relief"
    pack.components = [paye]
    cases = [
        ("24000", "0.00"),
        ("32333", "2083.25"),
        ("100000", "22383.35"),
        ("500000", "142383.35"),
        ("600000", "174883.35"),
        ("800000", "239883.35"),
        ("1000000", "309883.35"),
    ]
    for taxable, expected in cases:
        result = calculate_payslip(pack, _gross(taxable))
        assert _line(result, "TAXABLE") == D(taxable), taxable
        assert _line(result, "PAYE") == D(expected), taxable


def _kenya_pension_pack() -> PayrollPack:
    pack = _kenya_nssf_pack()
    pack.constants = [
        PayrollPackConstant(key="personal_relief", amount=D("2400")),
        PayrollPackConstant(key="pension_relief_cap", amount=D("30000")),
        PayrollPackConstant(key="pension_relief_percent", amount=D("30")),
    ]
    paye = _paye(KE_PAYE_BANDS)
    paye.relief_key = "personal_relief"
    pack.components = [*pack.components, paye]
    return pack


def test_voluntary_pension_within_limit_is_fully_before_tax() -> None:
    result = calculate_payslip(_kenya_pension_pack(), _gross("100000", pension="10000"))
    assert _line(result, "NSSF_II") == D("5460.00")
    assert _line(result, "VOL_PENSION") == D("10000.00")
    assert _line(result, "VOL_PENSION_POST") is None
    assert _line(result, "TAXABLE") == D("84000.00")


def test_voluntary_pension_shares_30000_cap_with_nssf() -> None:
    result = calculate_payslip(_kenya_pension_pack(), _gross("200000", pension="40000", scheme="Britam"))
    assert _line(result, "VOL_PENSION") == D("23520.00")
    assert _line(result, "VOL_PENSION_POST") == D("16480.00")
    assert _line(result, "TAXABLE") == D("170000.00")
    names = {item["code"]: item["name"] for item in result["lines"]}
    assert names["VOL_PENSION"] == "Britam (before tax)"
    assert names["VOL_PENSION_POST"] == "Britam (after tax)"
    deductions = D("6480") + D("40000") + _line(result, "PAYE")
    assert result["employee_deductions"] == deductions
    assert result["net"] == D("200000.00") - deductions


def test_voluntary_pension_limited_to_30_percent_of_pensionable_pay() -> None:
    result = calculate_payslip(_kenya_pension_pack(), _gross("50000", pension="20000"))
    assert _line(result, "NSSF_II") == D("2460.00")
    assert _line(result, "VOL_PENSION") == D("12000.00")
    assert _line(result, "VOL_PENSION_POST") == D("8000.00")
    assert _line(result, "TAXABLE") == D("35000.00")


def test_voluntary_pension_is_after_tax_when_pack_has_no_relief() -> None:
    pack = _uganda_pack(UG_BANDS_FROM_JULY_2026)
    result = calculate_payslip(pack, _gross("2000000", pension="100000"), places=0)
    assert _line(result, "VOL_PENSION") is None
    assert _line(result, "VOL_PENSION_POST") == D("100000")
    assert _line(result, "TAXABLE") == D("2000000")
    assert _line(result, "PAYE") == D("488250")
    assert result["net"] == D("2000000") - D("100000") - D("100000") - D("488250")


def test_other_deductions_come_after_tax_and_never_make_net_negative() -> None:
    pack = _kenya_pension_pack()
    base = calculate_payslip(pack, _gross("20000"))
    result = calculate_payslip(
        pack,
        _gross("20000"),
        other_deductions=[
            {"id": "loan", "name": "Staff loan", "amount": D("5000")},
            {"id": "sacco", "name": "Sacco", "amount": D("50000")},
        ],
    )
    assert _line(result, "TAXABLE") == _line(base, "TAXABLE")
    assert _line(result, "PAYE") == _line(base, "PAYE")
    others = [item for item in result["lines"] if item["code"] == "OTHER"]
    assert [item["employee_deduction_id"] for item in others] == ["loan", "sacco"]
    assert others[0]["amount"] == D("5000.00")
    assert others[1]["amount"] == base["net"] - D("5000")
    assert result["net"] == D("0.00")


def test_benefit_is_taxable_and_pensionable() -> None:
    pack = _kenya_pension_pack()
    base = calculate_payslip(pack, _gross("50000"))
    result = calculate_payslip(
        pack,
        _gross("50000"),
        benefits=[{"id": "b1", "name": "Commission", "amount": D("30000")}],
    )
    assert result["gross"] == D("80000.00")
    assert _line(result, "GROSS") == D("80000.00")
    assert _line(result, "BENEFIT") == D("30000.00")
    assert _line(result, "NSSF_II") == D("4260.00")
    assert _line(result, "TAXABLE") == D("75200.00")
    assert _line(result, "PAYE") > _line(base, "PAYE")
    benefit = next(item for item in result["lines"] if item["code"] == "BENEFIT")
    assert benefit["employee_benefit_id"] == "b1"


def _uganda_pack(bands: list[tuple[str, str | None, str]]) -> PayrollPack:
    pack = PayrollPack()
    pack.constants = []
    pack.components = [
        _percent("NSSF", "NSSF", "EMPLOYEE", "GROSS", "5", order=10),
        _percent("NSSF_ER", "NSSF (employer)", "EMPLOYER", "GROSS", "10", order=11),
        _paye(bands),
    ]
    return pack


UG_BANDS_TO_JUNE_2026 = [
    ("0", "235000", "0"),
    ("235000", "335000", "10"),
    ("335000", "410000", "20"),
    ("410000", "10000000", "30"),
    ("10000000", None, "40"),
]

UG_BANDS_FROM_JULY_2026 = [
    ("0", "335000", "0"),
    ("335000", "410000", "20"),
    ("410000", "485000", "25"),
    ("485000", "10000000", "30"),
    ("10000000", None, "40"),
]


def test_uganda_nssf_and_paye_to_june_2026() -> None:
    pack = _uganda_pack(UG_BANDS_TO_JUNE_2026)
    result = calculate_payslip(pack, _gross("2000000"), places=0)
    assert _line(result, "NSSF") == D("100000")
    assert _line(result, "NSSF_ER") == D("200000")
    assert _line(result, "TAXABLE") == D("2000000")
    assert _line(result, "PAYE") == D("502000")
    low = calculate_payslip(pack, _gross("200000"), places=0)
    assert _line(low, "NSSF") == D("10000")
    assert _line(low, "TAXABLE") == D("200000")
    assert _line(low, "PAYE") == D("0")


def test_uganda_paye_from_july_2026() -> None:
    pack = _uganda_pack(UG_BANDS_FROM_JULY_2026)
    result = calculate_payslip(pack, _gross("2000000"), places=0)
    assert _line(result, "NSSF") == D("100000")
    assert _line(result, "TAXABLE") == D("2000000")
    assert _line(result, "PAYE") == D("488250")
    threshold = calculate_payslip(pack, _gross("350000"), places=0)
    assert _line(threshold, "NSSF") == D("17500")
    assert _line(threshold, "TAXABLE") == D("350000")
    assert _line(threshold, "PAYE") == D("3000")


def test_uganda_paye_matches_ura_july_2026_examples() -> None:
    pack = _uganda_pack(UG_BANDS_FROM_JULY_2026)
    cases = [
        ("335000", "0"),
        ("350000", "3000"),
        ("450000", "25000"),
        ("485000", "33750"),
        ("500000", "38250"),
        ("1000000", "188250"),
        ("12000000", "3688250"),
    ]
    for chargeable, paye in cases:
        result = calculate_payslip(pack, _gross(chargeable), places=0)
        assert _line(result, "TAXABLE") == D(chargeable), chargeable
        assert _line(result, "PAYE") == D(paye), chargeable

