"""Demo tenant, companies, branches, and employees for local testing.

Idempotent: creates the demo tenants once, then tops up EXTRA_STAFF by work email.
Not run on backend start — invoke with `python -m app.db.seed_demo`.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.lifecycle import record_hired
from app.api.org import ensure_document_categories, next_employee_number
from app.api.supervisors import replace_supervisors
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.payroll_packs import seed_payroll_packs
from app.db.seed import seed_countries, seed_platform_admin
from app.db.session import dispose_engine, get_session_maker
from app.models import (
    Branch,
    Company,
    Country,
    Department,
    Employee,
    JobTitle,
    LeaveType,
    Tenant,
    User,
)
from app.schemas.payroll import CompensationCreate, PayLineWrite
from app.services.holidays import ensure_country_holidays
from app.services.organization import apply_country_defaults
from app.services.payroll import add_compensation, save_settings

DEMO_OWNER_EMAIL = "demo@example.com"
DEMO_PASSWORD = "DemoPass12"
DEMO_TENANT_NAME = "East Africa Demo"
SECOND_OWNER_EMAIL = "acme@example.com"
SECOND_TENANT_NAME = "Acme Coffee"

D = Decimal

RIFT = (DEMO_OWNER_EMAIL, "Rift Valley Trading Ltd")
NILE = (DEMO_OWNER_EMAIL, "Nile Logistics Ltd")
COASTAL = (DEMO_OWNER_EMAIL, "Coastal Packers Ltd")
ACME = (SECOND_OWNER_EMAIL, "Acme Coffee Ltd")

# Salaries chosen to hit statutory edges: KE Tier I only, 24k PAYE band, 35% band;
# UG nil threshold, 25% band, 10m surtax; TZ nil threshold and top band.
EXTRA_STAFF: list[dict] = [
    {"org": RIFT, "branch": "NBO", "department": "FIN", "title": "ACC", "first_name": "Mercy", "last_name": "Achieng",
     "email": "mercy@riftvalley.example", "id_number": "KE-10007", "nssf_no": "NSSF-KE-10007", "shif_no": "SHIF-KE-10007",
     "basic": "150000", "allowances": [("Housing", "40000"), ("Car", "30000")]},
    {"org": RIFT, "branch": "NBO", "department": "OPS", "title": "MGR", "first_name": "Daniel", "last_name": "Kiprop",
     "email": "daniel@riftvalley.example", "id_number": "KE-10008", "nssf_no": "NSSF-KE-10008", "shif_no": "SHIF-KE-10008",
     "gross": "650000"},
    {"org": RIFT, "branch": "NBO", "department": "PEO", "title": "HR", "first_name": "Esther", "last_name": "Njeri",
     "email": "esther@riftvalley.example", "id_number": "KE-10009", "nssf_no": "NSSF-KE-10009", "shif_no": "SHIF-KE-10009",
     "employment_type": "PROBATION", "date_joined": date(2026, 8, 1), "date_ended": date(2026, 10, 31), "gross": "85000"},
    {"org": RIFT, "branch": "NBO", "department": "OPS", "title": "DRV", "first_name": "Samuel", "last_name": "Ochieng",
     "email": "samuel@riftvalley.example", "id_number": "KE-10010", "nssf_no": "NSSF-KE-10010", "shif_no": "SHIF-KE-10010",
     "gross": "24000", "supervisor": "john@riftvalley.example"},
    {"org": RIFT, "branch": "NBO", "department": "FIN", "title": "ACC", "first_name": "Joyce", "last_name": "Wambui",
     "email": "joyce@riftvalley.example", "id_number": "KE-10011", "nssf_no": "NSSF-KE-10011", "shif_no": "SHIF-KE-10011",
     "basic": "40000", "allowances": [("Housing", "12000"), ("Transport", "8000")], "supervisor": "faith@riftvalley.example"},
    {"org": RIFT, "branch": "MBA", "department": "OPS", "title": "DRV", "first_name": "Said", "last_name": "Mwinyi",
     "email": "said@riftvalley.example", "id_number": "KE-10012", "nssf_no": "NSSF-KE-10012", "shif_no": "SHIF-KE-10012",
     "gross": "32000", "supervisor": "john@riftvalley.example"},
    {"org": RIFT, "branch": "MBA", "department": "OPS", "title": "CLK", "first_name": "Rose", "last_name": "Akinyi",
     "email": "rose@riftvalley.example", "id_number": "KE-10013", "nssf_no": "NSSF-KE-10013", "shif_no": "SHIF-KE-10013",
     "gross": "8000", "login": "rose.clock@riftvalley.example"},
    {"org": RIFT, "branch": "MBA", "department": "OPS", "title": "CLK", "first_name": "Kevin", "last_name": "Mutua",
     "email": "kevin@riftvalley.example", "id_number": "KE-10014", "nssf_no": "NSSF-KE-10014", "shif_no": "SHIF-KE-10014",
     "employment_type": "CONTRACT", "date_joined": date(2025, 4, 1), "date_ended": date(2027, 3, 31), "gross": "55000"},
    {"org": NILE, "branch": "KLA", "department": "FLT", "title": "DRV", "first_name": "Moses", "last_name": "Ssemakula",
     "email": "moses@nilelogistics.example", "id_number": "UG-20005", "nssf_no": "NSSF-UG-20005",
     "gross": "335000", "supervisor": "sara@nilelogistics.example"},
    {"org": NILE, "branch": "KLA", "department": "FLT", "title": "DRV", "first_name": "Ivan", "last_name": "Kato",
     "email": "ivan@nilelogistics.example", "id_number": "UG-20006", "nssf_no": "NSSF-UG-20006",
     "gross": "450000", "supervisor": "sara@nilelogistics.example", "login": "ivan.clock@nilelogistics.example"},
    {"org": NILE, "branch": "KLA", "department": "FIN", "title": "ACC", "first_name": "Patricia", "last_name": "Nakato",
     "email": "patricia@nilelogistics.example", "id_number": "UG-20007", "nssf_no": "NSSF-UG-20007",
     "gross": "12000000"},
    {"org": NILE, "branch": "KLA", "department": "FIN", "title": "CLK", "first_name": "Agnes", "last_name": "Namuli",
     "email": "agnes@nilelogistics.example", "id_number": "UG-20008", "nssf_no": "NSSF-UG-20008",
     "basic": "600000", "allowances": [("Transport", "150000"), ("Lunch", "100000")]},
    {"org": NILE, "branch": "JJA", "department": "FIN", "title": "CLK", "first_name": "Ruth", "last_name": "Auma",
     "email": "ruth@nilelogistics.example", "id_number": "UG-20009", "nssf_no": "NSSF-UG-20009",
     "gross": "280000", "supervisor": "grace@nilelogistics.example"},
    {"org": NILE, "branch": "JJA", "department": "FLT", "title": "DRV", "first_name": "Robert", "last_name": "Ouma",
     "email": "robert@nilelogistics.example", "id_number": "UG-20010", "nssf_no": "NSSF-UG-20010",
     "employment_type": "CONTRACT", "date_joined": date(2025, 7, 1), "date_ended": date(2027, 6, 30), "gross": "1000000"},
    {"org": COASTAL, "branch": "DAR", "department": "PLT", "title": "OPR", "first_name": "Fatuma", "last_name": "Said",
     "email": "fatuma@coastalpackers.example", "id_number": "TZ-30003", "nssf_no": "NSSF-TZ-30003",
     "gross": "270000", "supervisor": "neema@coastalpackers.example"},
    {"org": COASTAL, "branch": "DAR", "department": "PLT", "title": "OPR", "first_name": "Juma", "last_name": "Mohamed",
     "email": "juma@coastalpackers.example", "id_number": "TZ-30004", "nssf_no": "NSSF-TZ-30004",
     "gross": "600000", "supervisor": "neema@coastalpackers.example", "login": "juma.clock@coastalpackers.example"},
    {"org": COASTAL, "branch": "DAR", "department": "PLT", "title": "OPR", "first_name": "Zawadi", "last_name": "Kimaro",
     "email": "zawadi@coastalpackers.example", "id_number": "TZ-30005", "nssf_no": "NSSF-TZ-30005",
     "basic": "700000", "allowances": [("Housing", "200000")]},
    {"org": COASTAL, "branch": "ARU", "department": "PLT", "title": "OPR", "first_name": "Rehema", "last_name": "Mushi",
     "email": "rehema@coastalpackers.example", "id_number": "TZ-30006", "nssf_no": "NSSF-TZ-30006",
     "gross": "1500000"},
    {"org": COASTAL, "branch": "ARU", "department": "PLT", "title": "OPR", "first_name": "Baraka", "last_name": "Mollel",
     "email": "baraka@coastalpackers.example", "id_number": "TZ-30007", "nssf_no": "NSSF-TZ-30007",
     "employment_type": "PROBATION", "date_joined": date(2026, 9, 1), "date_ended": date(2026, 11, 30), "gross": "450000"},
    {"org": ACME, "branch": "KLA", "department": "FRM", "title": "PCK", "first_name": "Sarah", "last_name": "Akello",
     "email": "sarah@acme.example", "id_number": "UG-90003", "nssf_no": "NSSF-UG-90003", "gross": "400000"},
    {"org": ACME, "branch": "MBL", "department": "FRM", "title": "PCK", "first_name": "Paul", "last_name": "Wandera",
     "email": "paul@acme.example", "id_number": "UG-90004", "nssf_no": "NSSF-UG-90004", "gross": "300000"},
    {"org": ACME, "branch": "MBL", "department": "FRM", "title": "PCK", "first_name": "Joan", "last_name": "Nekesa",
     "email": "joan@acme.example", "id_number": "UG-90005", "nssf_no": "NSSF-UG-90005", "gross": "500000"},
]


async def _platform(session: AsyncSession) -> None:
    await session.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))


async def _country(session: AsyncSession, code: str) -> Country:
    row = await session.scalar(select(Country).where(Country.code == code))
    if row is None:
        raise RuntimeError(f"Country {code} is missing. Seed countries first.")
    return row


async def _company(
    session: AsyncSession,
    tenant_id,
    *,
    name: str,
    legal_name: str,
    email: str,
) -> Company:
    row = Company(
        tenant_id=tenant_id,
        name=name,
        legal_name=legal_name,
        email=email,
        status="ACTIVE",
    )
    session.add(row)
    await session.flush()
    await ensure_document_categories(session, row.id)
    return row


async def _branch(
    session: AsyncSession,
    company: Company,
    country: Country,
    *,
    name: str,
    code: str,
    city: str,
) -> Branch:
    row = Branch(
        company_id=company.id,
        country_id=country.id,
        name=name,
        code=code,
        city=city,
        status="ACTIVE",
    )
    apply_country_defaults(row, country)
    session.add(row)
    await session.flush()
    await ensure_country_holidays(session, company.id, country)
    return row


async def _department(session: AsyncSession, company: Company, name: str, code: str) -> Department:
    row = Department(company_id=company.id, name=name, code=code, status="ACTIVE")
    session.add(row)
    await session.flush()
    return row


async def _title(
    session: AsyncSession,
    company: Company,
    name: str,
    code: str,
    department: Department | None = None,
) -> JobTitle:
    row = JobTitle(
        company_id=company.id,
        department_id=department.id if department else None,
        name=name,
        code=code,
        status="ACTIVE",
    )
    session.add(row)
    await session.flush()
    return row


async def _leave_types(session: AsyncSession, company: Company) -> None:
    session.add(
        LeaveType(
            company_id=company.id,
            name="Annual",
            days=D("21"),
            accrued=True,
            accrual_per_month=D("1.75"),
            day_basis="WORKING",
            sort_order=10,
        )
    )
    session.add(
        LeaveType(
            company_id=company.id,
            name="Sick",
            days=D("7"),
            accrued=False,
            accrual_per_month=D("0"),
            day_basis="CALENDAR",
            sort_order=20,
        )
    )
    await session.flush()


async def _employee(
    session: AsyncSession,
    *,
    company: Company,
    branch: Branch,
    department: Department | None,
    title: JobTitle | None,
    first_name: str,
    last_name: str,
    other_names: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    id_number: str | None = None,
    nssf_no: str | None = None,
    shif_no: str | None = None,
    employment_type: str = "FULL_TIME",
    date_joined: date = date(2024, 3, 1),
    date_ended: date | None = None,
) -> Employee:
    number = await next_employee_number(session, company.id)
    row = Employee(
        company_id=company.id,
        branch_id=branch.id,
        department_id=department.id if department else None,
        job_title_id=title.id if title else None,
        employee_number=number,
        first_name=first_name,
        other_names=other_names,
        last_name=last_name,
        email=email,
        phone=phone,
        id_number=id_number,
        nssf_no=nssf_no,
        shif_no=shif_no,
        employment_type=employment_type,
        date_joined=date_joined,
        date_ended=date_ended,
        status="ACTIVE",
    )
    session.add(row)
    await session.flush()
    await record_hired(session, row)
    return row


async def _gross(
    session: AsyncSession,
    employee: Employee,
    amount: str,
    *,
    from_date: date = date(2024, 3, 1),
) -> None:
    await add_compensation(
        session,
        employee,
        CompensationCreate(effective_from=from_date, structure="GROSS_ONLY", gross_amount=D(amount)),
    )


async def _basic_plus(
    session: AsyncSession,
    employee: Employee,
    basic: str,
    allowances: list[tuple[str, str]],
    *,
    from_date: date = date(2024, 3, 1),
) -> None:
    await add_compensation(
        session,
        employee,
        CompensationCreate(
            effective_from=from_date,
            structure="BASIC_PLUS_ALLOWANCES",
            basic_amount=D(basic),
            lines=[
                PayLineWrite(name=name, amount=D(amount), sort_order=index)
                for index, (name, amount) in enumerate(allowances)
            ],
        ),
    )


async def _login(
    session: AsyncSession,
    tenant_id,
    employee: Employee,
    email: str,
    *,
    role: str = "EMPLOYEE",
    full_name: str | None = None,
) -> User:
    user = User(
        tenant_id=tenant_id,
        email=email,
        password_hash=hash_password(DEMO_PASSWORD),
        full_name=full_name or f"{employee.first_name} {employee.last_name}",
        role=role,
        status="ACTIVE",
        employee_id=employee.id,
    )
    session.add(user)
    await session.flush()
    return user


async def _seed_rift(session: AsyncSession, tenant: Tenant, kenya: Country) -> None:
    company = await _company(
        session,
        tenant.id,
        name="Rift Valley Trading Ltd",
        legal_name="Rift Valley Trading Limited",
        email="hello@riftvalley.example",
    )
    nairobi = await _branch(session, company, kenya, name="Nairobi HQ", code="NBO", city="Nairobi")
    mombasa = await _branch(session, company, kenya, name="Mombasa", code="MBA", city="Mombasa")
    people = await _department(session, company, "People", "PEO")
    finance = await _department(session, company, "Finance", "FIN")
    operations = await _department(session, company, "Operations", "OPS")
    hr_title = await _title(session, company, "HR Officer", "HR", people)
    manager = await _title(session, company, "Branch Manager", "MGR", operations)
    accountant = await _title(session, company, "Accountant", "ACC", finance)
    driver = await _title(session, company, "Driver", "DRV", operations)
    clerk = await _title(session, company, "Warehouse Clerk", "CLK", operations)
    intern_title = await _title(session, company, "Intern", "INT", people)
    await _leave_types(session, company)
    await save_settings(session, company.id, tenant.id, "MONTHLY", "GROSS_ONLY")

    amina = await _employee(
        session,
        company=company,
        branch=nairobi,
        department=people,
        title=hr_title,
        first_name="Amina",
        last_name="Otieno",
        email="amina@riftvalley.example",
        phone="+254700000001",
        id_number="KE-10001",
        nssf_no="NSSF-KE-10001",
        shif_no="SHIF-KE-10001",
    )
    john = await _employee(
        session,
        company=company,
        branch=nairobi,
        department=operations,
        title=manager,
        first_name="John",
        last_name="Kamau",
        email="john@riftvalley.example",
        phone="+254700000002",
        id_number="KE-10002",
        nssf_no="NSSF-KE-10002",
        shif_no="SHIF-KE-10002",
    )
    faith = await _employee(
        session,
        company=company,
        branch=nairobi,
        department=finance,
        title=accountant,
        first_name="Faith",
        last_name="Wanjiku",
        email="faith@riftvalley.example",
        phone="+254700000003",
        id_number="KE-10003",
        nssf_no="NSSF-KE-10003",
        shif_no="SHIF-KE-10003",
    )
    peter = await _employee(
        session,
        company=company,
        branch=mombasa,
        department=operations,
        title=driver,
        first_name="Peter",
        last_name="Mwangi",
        email="peter@riftvalley.example",
        phone="+254700000004",
        id_number="KE-10004",
        nssf_no="NSSF-KE-10004",
        shif_no="SHIF-KE-10004",
    )
    lucy = await _employee(
        session,
        company=company,
        branch=mombasa,
        department=operations,
        title=clerk,
        first_name="Lucy",
        last_name="Cherono",
        email="lucy@riftvalley.example",
        phone="+254700000005",
        id_number="KE-10005",
        nssf_no="NSSF-KE-10005",
        shif_no="SHIF-KE-10005",
    )
    brian = await _employee(
        session,
        company=company,
        branch=nairobi,
        department=people,
        title=intern_title,
        first_name="Brian",
        last_name="Omondi",
        email="brian@riftvalley.example",
        employment_type="INTERN",
        date_joined=date(2026, 7, 1),
        date_ended=date(2026, 12, 31),
        id_number="KE-10006",
    )
    await _gross(session, amina, "120000")
    await _gross(session, john, "180000")
    await _basic_plus(session, faith, "70000", [("Housing", "25000"), ("Transport", "15000")])
    await _gross(session, peter, "65000")
    await _gross(session, lucy, "45000")
    await _gross(session, brian, "25000", from_date=date(2026, 7, 1))
    await replace_supervisors(session, faith, [john.id])
    await replace_supervisors(session, peter, [john.id])
    await _login(session, tenant.id, amina, "hr@riftvalley.example", role="HR")
    await _login(session, tenant.id, peter, "peter.clock@riftvalley.example")


async def _seed_nile(session: AsyncSession, tenant: Tenant, uganda: Country) -> None:
    company = await _company(
        session,
        tenant.id,
        name="Nile Logistics Ltd",
        legal_name="Nile Logistics Limited",
        email="hello@nilelogistics.example",
    )
    kampala = await _branch(session, company, uganda, name="Kampala", code="KLA", city="Kampala")
    jinja = await _branch(session, company, uganda, name="Jinja", code="JJA", city="Jinja")
    fleet = await _department(session, company, "Fleet", "FLT")
    finance = await _department(session, company, "Finance", "FIN")
    manager = await _title(session, company, "Country Manager", "MGR", fleet)
    driver = await _title(session, company, "Driver", "DRV", fleet)
    accountant = await _title(session, company, "Accountant", "ACC", finance)
    clerk = await _title(session, company, "Clerk", "CLK", finance)
    await _leave_types(session, company)
    await save_settings(session, company.id, tenant.id, "MONTHLY", "GROSS_ONLY")

    sara = await _employee(
        session,
        company=company,
        branch=kampala,
        department=fleet,
        title=manager,
        first_name="Sara",
        last_name="Nambi",
        email="sara@nilelogistics.example",
        phone="+256700000001",
        id_number="UG-20001",
        nssf_no="NSSF-UG-20001",
    )
    david = await _employee(
        session,
        company=company,
        branch=kampala,
        department=fleet,
        title=driver,
        first_name="David",
        last_name="Okello",
        email="david@nilelogistics.example",
        phone="+256700000002",
        id_number="UG-20002",
        nssf_no="NSSF-UG-20002",
    )
    grace = await _employee(
        session,
        company=company,
        branch=jinja,
        department=finance,
        title=accountant,
        first_name="Grace",
        last_name="Atim",
        email="grace@nilelogistics.example",
        phone="+256700000003",
        id_number="UG-20003",
        nssf_no="NSSF-UG-20003",
    )
    joseph = await _employee(
        session,
        company=company,
        branch=jinja,
        department=finance,
        title=clerk,
        first_name="Joseph",
        last_name="Mukasa",
        email="joseph@nilelogistics.example",
        phone="+256700000004",
        id_number="UG-20004",
        nssf_no="NSSF-UG-20004",
    )
    await _gross(session, sara, "3500000")
    await _gross(session, david, "1200000")
    await _basic_plus(session, grace, "1800000", [("Housing", "400000"), ("Transport", "300000")])
    await _gross(session, joseph, "900000")
    await replace_supervisors(session, david, [sara.id])


async def _seed_coastal(session: AsyncSession, tenant: Tenant, tanzania: Country) -> None:
    company = await _company(
        session,
        tenant.id,
        name="Coastal Packers Ltd",
        legal_name="Coastal Packers Limited",
        email="hello@coastalpackers.example",
    )
    dar = await _branch(session, company, tanzania, name="Dar es Salaam", code="DAR", city="Dar es Salaam")
    arusha = await _branch(session, company, tanzania, name="Arusha", code="ARU", city="Arusha")
    plant = await _department(session, company, "Plant", "PLT")
    manager = await _title(session, company, "Plant Manager", "MGR", plant)
    operator = await _title(session, company, "Machine Operator", "OPR", plant)
    await _leave_types(session, company)
    await save_settings(session, company.id, tenant.id, "MONTHLY", "GROSS_ONLY")

    neema = await _employee(
        session,
        company=company,
        branch=dar,
        department=plant,
        title=manager,
        first_name="Neema",
        last_name="Juma",
        email="neema@coastalpackers.example",
        phone="+255700000001",
        id_number="TZ-30001",
        nssf_no="NSSF-TZ-30001",
    )
    ali = await _employee(
        session,
        company=company,
        branch=arusha,
        department=plant,
        title=operator,
        first_name="Ali",
        last_name="Hassan",
        email="ali@coastalpackers.example",
        phone="+255700000002",
        id_number="TZ-30002",
        nssf_no="NSSF-TZ-30002",
    )
    await _gross(session, neema, "1800000")
    await _gross(session, ali, "850000")


async def _seed_acme(session: AsyncSession, uganda: Country) -> None:
    settings = get_settings()
    trial_ends_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=settings.trial_days)
    tenant = Tenant(
        name=SECOND_TENANT_NAME,
        subscription_tier="TRIAL",
        status="ACTIVE",
        trial_ends_at=trial_ends_at,
    )
    session.add(tenant)
    await session.flush()
    owner = User(
        tenant_id=tenant.id,
        email=SECOND_OWNER_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        full_name="Acme Owner",
        role="OWNER",
        status="ACTIVE",
    )
    session.add(owner)
    company = await _company(
        session,
        tenant.id,
        name="Acme Coffee Ltd",
        legal_name="Acme Coffee Limited",
        email=SECOND_OWNER_EMAIL,
    )
    kampala = await _branch(session, company, uganda, name="Kampala", code="KLA", city="Kampala")
    mbale = await _branch(session, company, uganda, name="Mbale", code="MBL", city="Mbale")
    farm = await _department(session, company, "Farm", "FRM")
    picker = await _title(session, company, "Picker", "PCK", farm)
    await _leave_types(session, company)
    await save_settings(session, company.id, tenant.id, "MONTHLY", "GROSS_ONLY")
    person = await _employee(
        session,
        company=company,
        branch=kampala,
        department=farm,
        title=picker,
        first_name="Rita",
        last_name="Nabirye",
        email="rita@acme.example",
        id_number="UG-90001",
        nssf_no="NSSF-UG-90001",
    )
    tom = await _employee(
        session,
        company=company,
        branch=mbale,
        department=farm,
        title=picker,
        first_name="Tom",
        last_name="Wekesa",
        email="tom@acme.example",
        id_number="UG-90002",
        nssf_no="NSSF-UG-90002",
    )
    await _gross(session, person, "800000")
    await _gross(session, tom, "650000")


async def _top_up_staff(session: AsyncSession) -> int:
    added = 0
    for spec in EXTRA_STAFF:
        owner_email, company_name = spec["org"]
        tenant_id = await session.scalar(select(User.tenant_id).where(User.email == owner_email))
        if tenant_id is None:
            continue
        company = await session.scalar(
            select(Company).where(Company.tenant_id == tenant_id, Company.name == company_name)
        )
        if company is None:
            continue
        taken = await session.scalar(
            select(Employee.id).where(Employee.company_id == company.id, Employee.email == spec["email"])
        )
        if taken is not None:
            continue
        branch = await session.scalar(
            select(Branch).where(Branch.company_id == company.id, Branch.code == spec["branch"])
        )
        if branch is None:
            continue
        department = await session.scalar(
            select(Department).where(Department.company_id == company.id, Department.code == spec["department"])
        )
        title = await session.scalar(
            select(JobTitle).where(JobTitle.company_id == company.id, JobTitle.code == spec["title"])
        )
        joined = spec.get("date_joined", date(2024, 3, 1))
        person = await _employee(
            session,
            company=company,
            branch=branch,
            department=department,
            title=title,
            first_name=spec["first_name"],
            last_name=spec["last_name"],
            email=spec["email"],
            id_number=spec.get("id_number"),
            nssf_no=spec.get("nssf_no"),
            shif_no=spec.get("shif_no"),
            employment_type=spec.get("employment_type", "FULL_TIME"),
            date_joined=joined,
            date_ended=spec.get("date_ended"),
        )
        if "basic" in spec:
            await _basic_plus(session, person, spec["basic"], spec["allowances"], from_date=joined)
        else:
            await _gross(session, person, spec["gross"], from_date=joined)
        supervisor_email = spec.get("supervisor")
        if supervisor_email:
            boss = await session.scalar(
                select(Employee).where(Employee.company_id == company.id, Employee.email == supervisor_email)
            )
            if boss is not None:
                await replace_supervisors(session, person, [boss.id])
        login = spec.get("login")
        if login and await session.scalar(select(User.id).where(User.email == login)) is None:
            await _login(session, tenant_id, person, login)
        added += 1
    await session.flush()
    return added


async def seed_demo(session: AsyncSession) -> dict:
    await _platform(session)
    existing = await session.scalar(select(User).where(User.email == DEMO_OWNER_EMAIL))
    if existing is not None:
        added = await _top_up_staff(session)
        return {"created": False, "tenant_id": str(existing.tenant_id), "added": added}

    kenya = await _country(session, "KE")
    uganda = await _country(session, "UG")
    tanzania = await _country(session, "TZ")
    settings = get_settings()
    trial_ends_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=settings.trial_days)
    tenant = Tenant(
        name=DEMO_TENANT_NAME,
        subscription_tier="TRIAL",
        status="ACTIVE",
        trial_ends_at=trial_ends_at,
    )
    session.add(tenant)
    await session.flush()
    session.add(
        User(
            tenant_id=tenant.id,
            email=DEMO_OWNER_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            full_name="Demo Owner",
            role="OWNER",
            status="ACTIVE",
        )
    )
    await _seed_rift(session, tenant, kenya)
    await _seed_nile(session, tenant, uganda)
    await _seed_coastal(session, tenant, tanzania)
    await _seed_acme(session, uganda)
    await session.flush()
    added = await _top_up_staff(session)
    return {"created": True, "tenant_id": str(tenant.id), "added": added}


async def main() -> None:
    maker = get_session_maker()
    async with maker() as session:
        await seed_countries(session)
        await seed_payroll_packs(session)
        await seed_platform_admin(session)
        result = await seed_demo(session)
        await session.commit()
        if result["created"]:
            print("Demo workspace created.")
            print(f"  Owner login: {DEMO_OWNER_EMAIL} / {DEMO_PASSWORD}")
            print("  Companies: Rift Valley Trading (KE), Nile Logistics (UG), Coastal Packers (TZ)")
            print(f"  Second tenant: {SECOND_OWNER_EMAIL} / {DEMO_PASSWORD}  ({SECOND_TENANT_NAME})")
            print("  HR login: hr@riftvalley.example / " + DEMO_PASSWORD)
            print("  Clock-in login: peter.clock@riftvalley.example / " + DEMO_PASSWORD)
        else:
            print("Demo workspace already exists. Log in as demo@example.com")
        print(f"  Extra staff added this run: {result['added']}")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
