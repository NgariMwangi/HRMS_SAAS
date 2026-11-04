import re
from decimal import Decimal
from types import SimpleNamespace
import pytest
from app.services.payslip_pdf import render
from app.services.payslips import split_lines
from tests.test_access import workspace, staff_login
from tests.test_platform import _admin_login


def sample_document():
    return dict(company_name="Acacia Healthcare", company_legal_name="Acacia Healthcare Limited",
        company_email="people@acacia.example", company_phone="+254 700 123 456", employee_name="Mary Wanjiku",
        employee_number="EMP-0042", branch_name="Nairobi Head Office", period_start="2026-10-01", period_end="2026-10-31",
        status="APPROVED", currency_code="KES", decimal_places=2, reference="PS-4E8A7C92D1F0",
        filename="payslip-EMP-0042-2026-10.pdf", gross="120000.00", employee_deductions="34645.30",
        employer_contributions="6480.00", net="85354.70", taxable="102470.00",
        earnings=[dict(id="1", name="Basic salary", amount="90000.00"), dict(id="2", name="Housing allowance", amount="20000.00"), dict(id="3", name="Transport allowance", amount="10000.00")],
        deductions=[dict(id="4", name="PAYE", amount="23665.30"), dict(id="5", name="NSSF — Tier I", amount="540.00"), dict(id="6", name="NSSF — Tier II", amount="5940.00"), dict(id="7", name="Social Health Insurance", amount="3300.00"), dict(id="8", name="Housing levy", amount="1200.00")],
        employer=[dict(id="9", name="NSSF — employer contribution", amount="6480.00")])


def test_pdf_layout_handles_unicode_long_tables_and_draft_without_markup():
    sample = sample_document()
    pdf = render(sample)
    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 1
    sample.update(employee_name="Zoë <b>O'Connor</b> & Wanjikũ", company_name="A&B <Company>", status="DRAFT")
    sample["deductions"] = [dict(id=str(i), name="A long deduction description with employee loan and cooperative reference " + str(i), amount="10.00") for i in range(100)]
    pdf = render(sample)
    assert pdf.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) > 1


@pytest.mark.parametrize("basic", [False, True])
def test_earnings_reconcile_without_counting_gross_or_taxable_twice(basic):
    def line(code, amount, kind="EARNING", party="EMPLOYEE"):
        return SimpleNamespace(id=code, code=code, name=code, amount=Decimal(amount), kind=kind, party=party, sort_order=1)
    lines = [line("GROSS", "110000"), line("TAXABLE", "95000"), line("BENEFIT", "10000"), line("PAYE", "20000", "DEDUCTION"), line("NSSF_ER", "5000", "EMPLOYER", "EMPLOYER")]
    if basic:
        lines += [line("BASIC", "80000"), line("ALLOWANCE_1", "20000")]
    earnings, deductions, employer, taxable = split_lines(lines, Decimal("110000"))
    assert sum(Decimal(row["amount"]) for row in earnings) == Decimal("110000")
    assert not {"GROSS", "TAXABLE"} & {row["code"] for row in earnings}
    assert len(deductions) == len(employer) == 1 and taxable == "95000"


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_pdf_download_permissions_approval_and_saved_amounts(client):
    w, owner = await workspace(client)
    a, _, employee = await staff_login(client, owner, w, "PdfEmployee")
    _, _, other_employee = await staff_login(client, owner, w, "PdfOther")
    foreign, foreign_owner = await workspace(client, "pdf-foreign@example.com")
    saved = await client.post(f"/employees/{a['id']}/compensation", headers=owner, json={"effective_from": "2026-01-01", "structure": "BASIC_PLUS_ALLOWANCES", "basic_amount": "80000", "lines": [{"name": "Housing allowance", "amount": "20000"}]})
    assert saved.status_code == 201, saved.text
    response = await client.post("/payroll/runs", headers=owner, json={"company_id": w["company"]["id"], "branch_id": w["branch"]["id"], "period_start": "2026-03-01", "period_end": "2026-03-31"})
    assert response.status_code == 201, response.text
    run = response.json(); slip = run["payslips"][0]
    path = f"/payroll/payslips/{slip['id']}"
    own_path = f"/employee-portal/payslips/{slip['id']}"
    assert (await client.get(own_path + "/pdf", headers=employee)).status_code == 404
    assert (await client.get(path + "/pdf", headers=owner)).status_code == 200
    assert (await client.get(path + "/pdf", headers=employee)).status_code == 403
    assert (await client.get(path + "/pdf", headers=foreign_owner)).status_code == 404
    assert (await client.get(path + "/pdf")).status_code == 401
    approved = await client.post(f"/payroll/runs/{run['id']}/approve", headers=owner)
    assert approved.status_code == 200, approved.text
    detail = await client.get(own_path, headers=employee)
    assert detail.status_code == 200, detail.text
    data = detail.json()
    assert data["employee_name"] == slip["employee_name"] and data["net"] == slip["net"]
    assert Decimal(data["gross"]) == sum(Decimal(r["amount"]) for r in data["earnings"])
    assert Decimal(data["employee_deductions"]) == sum(Decimal(r["amount"]) for r in data["deductions"])
    assert Decimal(data["net"]) == Decimal(data["gross"]) - Decimal(data["employee_deductions"])
    pdf = await client.get(own_path + "/pdf", headers=employee)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-") and "attachment" in pdf.headers["content-disposition"]
    assert ".pdf" in pdf.headers["content-disposition"] and "no-store" in pdf.headers["cache-control"]
    assert (await client.get(own_path + "/pdf", headers=other_employee)).status_code == 404
    admin = await _admin_login(client)
    platform_path = f"/platform/tenants/{w['tenant']['id']}/payroll/payslips/{slip['id']}"
    assert (await client.get(platform_path + "/pdf", headers=admin)).status_code == 200
    assert (await client.get(f"/platform/tenants/{foreign['tenant']['id']}/payroll/payslips/{slip['id']}/pdf", headers=admin)).status_code == 404
    # Updating today's salary must not change amounts in an already approved payslip.
    await client.patch(f"/employees/{a['id']}/compensation/{saved.json()['id']}", headers=owner, json={"effective_from": "2026-01-01", "structure": "GROSS_ONLY", "gross_amount": "200000"})
    assert (await client.get(own_path, headers=employee)).json()["gross"] == data["gross"]
