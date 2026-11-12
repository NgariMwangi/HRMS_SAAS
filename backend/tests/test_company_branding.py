import base64
from io import BytesIO
import pytest
from PIL import Image
from app.services.branding import NEXGEN_LOGO, NEXGEN_COLOR, normalise_logo
from app.services.payslip_pdf import render
from tests.test_access import workspace, staff_login
from tests.test_payslip_pdf import sample_document
from tests.test_workforce_payments import salary, run


def test_logo_validation_and_vector_pdf():
    output = BytesIO()
    Image.new("RGB", (200, 40), "blue").save(output, format="PNG")
    logo = normalise_logo("data:image/png;base64," + base64.b64encode(output.getvalue()).decode())
    assert logo.startswith("data:image/png;base64,")
    with pytest.raises(ValueError):
        normalise_logo("data:image/svg+xml;base64," + base64.b64encode(b'<svg onload="alert(1)"/>').decode())
    with pytest.raises(ValueError):
        normalise_logo("https://example.com/logo.png")
    sample = {**sample_document(), "company_name": "Nexgen Fuel Works", "logo_data_url": NEXGEN_LOGO, "theme_color": NEXGEN_COLOR}
    pdf = render(sample)
    assert pdf.startswith(b"%PDF-") and pdf.endswith(b"%%EOF\n")
    assert len(pdf) > len(render({**sample, "logo_data_url": None}))


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_branding_is_per_company_and_used_by_documents(client):
    w, owner = await workspace(client)
    person, _, staff = await staff_login(client, owner, w, "Branded")
    second = (await client.post("/companies", headers=owner, json={"name": "Unchanged company"})).json()
    endpoint = f"/companies/{w['company']['id']}"
    payload = {"theme_color": NEXGEN_COLOR, "logo_data_url": NEXGEN_LOGO}
    assert (await client.patch(endpoint, headers=staff, json=payload)).status_code == 403
    assert (await client.patch(endpoint, headers=owner, json={"theme_color": "red;display:none"})).status_code == 422
    response = await client.patch(endpoint, headers=owner, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["logo_data_url"] == NEXGEN_LOGO
    assert (await client.get(f"/companies/{second['id']}", headers=owner)).json()["logo_data_url"] is None
    assert (await client.get(f"/companies/{second['id']}", headers=owner)).json()["theme_color"] == "#4F46E5"
    host = (await client.get(f"/domains?company_id={w['company']['id']}", headers=owner)).json()[0]["hostname"]
    assert (await client.get("/domains/context", headers={"Host": host})).json()["company"]["logo_data_url"] == NEXGEN_LOGO
    query = f"company_id={w['company']['id']}"
    report = await client.get(f"/reports/headcount?{query}", headers=owner)
    assert report.status_code == 200, report.text
    assert report.json()["theme_color"] == NEXGEN_COLOR
    pdf = await client.get(f"/reports/headcount/pdf?{query}", headers=owner)
    assert pdf.status_code == 200, pdf.text[:200]
    assert pdf.content.startswith(b"%PDF-")
    assert (await client.get(f"/reports/headcount/pdf?{query}", headers=staff)).status_code == 403
    await salary(client, owner, person["id"])
    payroll = await run(client, owner, w)
    slip_id = payroll["payslips"][0]["id"]
    slip = await client.get(f"/payroll/payslips/{slip_id}", headers=owner)
    assert slip.json()["logo_data_url"] == NEXGEN_LOGO
    assert slip.json()["theme_color"] == NEXGEN_COLOR
    assert (await client.get(f"/payroll/payslips/{slip_id}/pdf", headers=owner)).content.startswith(b"%PDF-")
    assert (await client.patch(endpoint, headers=owner, json={"logo_data_url": None})).json()["logo_data_url"] is None
