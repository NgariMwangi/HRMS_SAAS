import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer

from app.schemas.base import ApiModel


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(Decimal(value), "f")


class PayrollMoneyModel(BaseModel):
    @field_serializer(
        "percent",
        "cap",
        "floor",
        "amount",
        "min_amount",
        "from_amount",
        "to_amount",
        "rate_percent",
        "gross_amount",
        "basic_amount",
        "voluntary_pension",
        "gross",
        "basic",
        "employee_deductions",
        "employer_contributions",
        "net",
        "gross_total",
        "deduction_total",
        "employer_total",
        "net_total",
        "computed_gross",
        "computed_basic",
        "default_amount",
        "total_amount",
        "recovered",
        "balance",
        "paid",
        check_fields=False,
    )
    def serialize_money(self, value: Decimal | None) -> str | None:
        return _money(value)


class PackBandRead(PayrollMoneyModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    sort_order: int
    from_amount: Decimal
    to_amount: Decimal | None
    rate_percent: Decimal


class PackComponentRead(PayrollMoneyModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    code: str
    name: str
    party: str
    formula_kind: str
    base: str
    percent: Decimal | None = None
    cap: Decimal | None = None
    floor: Decimal | None = None
    amount: Decimal | None = None
    min_amount: Decimal | None = None
    relief_key: str | None = None
    reduces_taxable: bool
    sort_order: int
    bands: list[PackBandRead] = Field(default_factory=list)


class PackConstantRead(PayrollMoneyModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    key: str
    amount: Decimal


class PayrollPackSummary(ApiModel):
    id: uuid.UUID
    country_id: uuid.UUID
    country_code: str | None = None
    version: int
    effective_from: date
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PayrollPackRead(PayrollPackSummary):
    components: list[PackComponentRead] = Field(default_factory=list)
    constants: list[PackConstantRead] = Field(default_factory=list)


class PackBandWrite(BaseModel):
    from_amount: Decimal
    to_amount: Decimal | None = None
    rate_percent: Decimal
    sort_order: int = 0


class PackComponentWrite(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=100)
    party: str
    formula_kind: str
    base: str
    percent: Decimal | None = None
    cap: Decimal | None = None
    floor: Decimal | None = None
    amount: Decimal | None = None
    min_amount: Decimal | None = None
    relief_key: str | None = None
    reduces_taxable: bool = False
    sort_order: int = 0
    bands: list[PackBandWrite] = Field(default_factory=list)


class PackConstantWrite(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    amount: Decimal


class PayrollPackUpdate(BaseModel):
    effective_from: date | None = None
    components: list[PackComponentWrite] | None = None
    constants: list[PackConstantWrite] | None = None


class PayrollPackCreate(BaseModel):
    country_id: uuid.UUID
    effective_from: date
    copy_from_id: uuid.UUID | None = None


class PayLineWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0)
    sort_order: int = 0


class PayLineRead(PayrollMoneyModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    kind: str
    name: str
    amount: Decimal
    sort_order: int


class CompensationCreate(BaseModel):
    effective_from: date
    structure: str
    gross_amount: Decimal | None = None
    basic_amount: Decimal | None = None
    voluntary_pension: Decimal | None = Field(default=None, ge=0)
    pension_scheme: str | None = Field(default=None, max_length=100)
    lines: list[PayLineWrite] = Field(default_factory=list)


class CompensationUpdate(CompensationCreate):
    pass


class CompensationRead(PayrollMoneyModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    company_id: uuid.UUID
    employee_id: uuid.UUID
    effective_from: date
    structure: str
    gross_amount: Decimal | None = None
    basic_amount: Decimal | None = None
    computed_gross: Decimal
    computed_basic: Decimal | None = None
    voluntary_pension: Decimal | None = None
    pension_scheme: str | None = None
    currency_id: uuid.UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None
    lines: list[PayLineRead] = Field(default_factory=list)


class DeductionTypeWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: str
    default_amount: Decimal | None = Field(default=None, gt=0)
    is_active: bool = True


class DeductionTypeCreate(DeductionTypeWrite):
    company_id: uuid.UUID


class DeductionTypeRead(PayrollMoneyModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    category: str
    default_amount: Decimal | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DeductionEnrol(BaseModel):
    branch_id: uuid.UUID | None = None
    employee_ids: list[uuid.UUID] | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    start_date: date


class DeductionEnrolCandidate(BaseModel):
    employee_id: uuid.UUID
    name: str
    employee_number: str
    branch_id: uuid.UUID
    enrolled: bool


class DeductionEnrolResult(BaseModel):
    enrolled: int
    already_enrolled: int


class EmployeeDeductionWrite(BaseModel):
    deduction_type_id: uuid.UUID
    frequency: str
    amount: Decimal = Field(gt=0)
    start_date: date
    end_date: date | None = None
    total_amount: Decimal | None = Field(default=None, gt=0)
    reference: str | None = Field(default=None, max_length=100)
    status: str = "ACTIVE"


class EmployeeDeductionRead(PayrollMoneyModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    deduction_type_id: uuid.UUID
    type_name: str
    category: str
    frequency: str
    amount: Decimal
    start_date: date
    end_date: date | None = None
    total_amount: Decimal | None = None
    reference: str | None = None
    status: str
    recovered: Decimal
    balance: Decimal | None = None
    created_at: datetime | None = None


class BenefitTypeWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    default_amount: Decimal | None = Field(default=None, gt=0)
    is_active: bool = True


class BenefitTypeCreate(BenefitTypeWrite):
    company_id: uuid.UUID


class BenefitTypeRead(PayrollMoneyModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    default_amount: Decimal | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EmployeeBenefitWrite(BaseModel):
    benefit_type_id: uuid.UUID
    note: str | None = Field(default=None, max_length=100)
    frequency: str
    amount: Decimal = Field(gt=0)
    start_date: date
    end_date: date | None = None
    status: str = "ACTIVE"


class EmployeeBenefitRead(PayrollMoneyModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    benefit_type_id: uuid.UUID
    type_name: str
    note: str | None = None
    frequency: str
    amount: Decimal
    start_date: date
    end_date: date | None = None
    status: str
    paid: Decimal
    created_at: datetime | None = None


class PayrollSettingsRead(ApiModel):
    company_id: uuid.UUID
    frequency: str
    salary_structure: str
    country_id: uuid.UUID | None = None
    country_code: str | None = None
    country_name: str | None = None
    currency_id: uuid.UUID | None = None
    currency_code: str | None = None
    currency_symbol: str | None = None
    pack_status: str | None = None
    pack_version: int | None = None
    pack_effective_from: date | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PayrollSettingsUpdate(BaseModel):
    frequency: str
    salary_structure: str


class PayrollRunCreate(BaseModel):
    company_id: uuid.UUID
    branch_id: uuid.UUID
    period_start: date
    period_end: date
    excluded_employee_ids: list[uuid.UUID] | None = Field(default=None, max_length=10000)


class PayslipLineRead(PayrollMoneyModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    code: str
    name: str
    party: str
    kind: str
    amount: Decimal
    sort_order: int
    employee_deduction_id: uuid.UUID | None = None
    employee_benefit_id: uuid.UUID | None = None


class PayslipRead(PayrollMoneyModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    employee_number: str
    gross: Decimal
    basic: Decimal | None = None
    employee_deductions: Decimal
    employer_contributions: Decimal
    net: Decimal
    lines: list[PayslipLineRead] = Field(default_factory=list)


class PayrollRunRead(PayrollMoneyModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    company_id: uuid.UUID
    branch_id: uuid.UUID
    period_start: date
    period_end: date
    excluded_employee_ids: list[uuid.UUID] = Field(default_factory=list)
    status: str
    payroll_pack_id: uuid.UUID
    pack_version: int | None = None
    country_code: str | None = None
    currency_id: uuid.UUID
    currency_code: str | None = None
    gross_total: Decimal
    deduction_total: Decimal
    employer_total: Decimal
    net_total: Decimal
    skipped: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    payslips: list[PayslipRead] = Field(default_factory=list)
