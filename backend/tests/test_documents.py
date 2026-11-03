import base64

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header
from tests.test_lifecycle import _hire
from tests.test_tenancy import _kenya, _register

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.mark.usefixtures("clean_tenant_tables")
async def test_document_categories_and_employee_files(client: AsyncClient) -> None:
    kenya = await _kenya()
    tenant_a = await _register(
        client,
        email="files-a@example.com",
        tenant_name="Files A",
        company_name="Files A Corp",
        country_id=kenya.id,
    )
    tenant_b = await _register(
        client,
        email="files-b@example.com",
        tenant_name="Files B",
        company_name="Files B Corp",
        country_id=kenya.id,
    )
    headers_a = auth_header(tenant_a["access_token"])
    headers_b = auth_header(tenant_b["access_token"])
    company_a = tenant_a["company"]["id"]
    branch_a = tenant_a["branch"]["id"]

    listed = await client.get("/document-categories", headers=headers_a, params={"company_id": company_a})
    assert listed.status_code == 200, listed.text
    categories = listed.json()
    by_key = {row["system_key"]: row for row in categories}
    assert set(by_key) >= {"PERSONAL", "ACADEMIC", "WORK", "PERFORMANCE", "LIFECYCLE"}
    assert by_key["LIFECYCLE"]["locked"] is True
    assert by_key["PERSONAL"]["locked"] is False
    personal_id = by_key["PERSONAL"]["id"]
    lifecycle_id = by_key["LIFECYCLE"]["id"]

    locked_edit = await client.patch(
        f"/document-categories/{lifecycle_id}",
        headers=headers_a,
        json={"name": "History"},
    )
    assert locked_edit.status_code == 400

    locked_delete = await client.delete(f"/document-categories/{lifecycle_id}", headers=headers_a)
    assert locked_delete.status_code == 400

    renamed = await client.patch(
        f"/document-categories/{personal_id}",
        headers=headers_a,
        json={"name": "Identity"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Identity"

    created = await client.post(
        "/document-categories",
        headers=headers_a,
        json={"company_id": company_a, "name": "Legal"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["locked"] is False

    other_company = await client.post(
        "/document-categories",
        headers=headers_a,
        json={"company_id": tenant_b["company"]["id"], "name": "Stolen"},
    )
    assert other_company.status_code == 403

    employee = await _hire(client, tenant_a["access_token"], company_a, branch_a, email="files@a-corp.example")

    lifecycle_upload = await client.post(
        f"/employees/{employee['id']}/documents",
        headers=headers_a,
        files={"file": ("id.png", TINY_PNG, "image/png")},
        data={"category_id": lifecycle_id},
    )
    assert lifecycle_upload.status_code == 400

    uploaded = await client.post(
        f"/employees/{employee['id']}/documents",
        headers=headers_a,
        files={"file": ("id.png", TINY_PNG, "image/png")},
        data={
            "category_id": personal_id,
            "issued_on": "2020-01-01",
            "expires_on": "2030-01-01",
            "note": "Certified copy",
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    document = uploaded.json()
    assert document["source"] == "UPLOAD"
    assert document["category"] == "Identity"
    assert document["category_id"] == personal_id
    assert document["filename"] == "id.png"
    assert document["size"] == len(TINY_PNG)
    assert document["content_type"] == "image/png"
    assert document["created_at"]

    download = await client.get(
        f"/employees/{employee['id']}/documents/{document['id']}",
        headers=headers_a,
    )
    assert download.status_code == 200
    assert download.content == TINY_PNG

    stolen = await client.get(f"/employees/{employee['id']}/documents", headers=headers_b)
    assert stolen.status_code in {403, 404}

    suspended = await client.post(
        f"/employees/{employee['id']}/lifecycle",
        headers=headers_a,
        json={
            "event_type": "SUSPENDED",
            "reason": "Investigation",
            "effective_on": "2026-02-01",
            "pay_treatment": "WITH_PAY",
        },
    )
    assert suspended.status_code == 200, suspended.text
    event_id = suspended.json()["event"]["id"]
    attached = await client.post(
        f"/employees/{employee['id']}/lifecycle/{event_id}/attachments",
        headers=headers_a,
        files={"files": ("notice.pdf", b"%PDF-1.4 notice", "application/pdf")},
    )
    assert attached.status_code == 200, attached.text

    company_files = await client.get("/documents", headers=headers_a, params={"company_id": company_a})
    assert company_files.status_code == 200
    listed_files = company_files.json()
    sources = {row["source"] for row in listed_files}
    assert sources == {"UPLOAD", "LIFECYCLE"}
    upload_row = next(row for row in listed_files if row["source"] == "UPLOAD")
    assert upload_row["size"] == len(TINY_PNG)
    lifecycle_row = next(row for row in listed_files if row["source"] == "LIFECYCLE")
    assert lifecycle_row["size"] == len(b"%PDF-1.4 notice")
    assert lifecycle_row["category"] == "Lifecycle"
    assert lifecycle_row["category_id"] == lifecycle_id
    assert lifecycle_row["event_label"] == "Suspended"

    personal_only = await client.get(
        "/documents",
        headers=headers_a,
        params={"company_id": company_a, "category_id": personal_id},
    )
    assert personal_only.status_code == 200
    assert {row["source"] for row in personal_only.json()} == {"UPLOAD"}

    lifecycle_only = await client.get(
        "/documents",
        headers=headers_a,
        params={"company_id": company_a, "category_id": lifecycle_id},
    )
    assert lifecycle_only.status_code == 200
    assert {row["source"] for row in lifecycle_only.json()} == {"LIFECYCLE"}

    removed = await client.delete(
        f"/employees/{employee['id']}/documents/{document['id']}",
        headers=headers_a,
    )
    assert removed.status_code == 204
