import base64
from types import SimpleNamespace
import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from app.services import payslip_email
from tests.test_payslip_pdf import sample_document


@pytest.fixture
def mail(monkeypatch):
    settings = SimpleNamespace(brevo_api_key=SecretStr("test-only-key"),
        brevo_sender_email="sender@example.com", brevo_sender_name="HRMS")
    monkeypatch.setattr(payslip_email, "get_settings", lambda: settings)
    calls = []
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(201, json={"messageId": "test-message"})
    monkeypatch.setattr(payslip_email.httpx, "AsyncClient", Client)
    return settings, calls


async def test_brevo_sends_pdf_to_primary_email(mail):
    settings, calls = mail
    data = {**sample_document(), "employee_primary_email": "primary@example.com", "employee_name": "Mary <b>Test</b>"}
    result = await payslip_email.send(data)
    assert result["recipient"] == "primary@example.com"
    url, request = calls[0]
    assert url == "https://api.brevo.com/v3/smtp/email"
    assert request["headers"]["api-key"] == "test-only-key"
    payload = request["json"]
    assert payload["to"] == [{"email": "primary@example.com", "name": data["employee_name"]}]
    assert "&lt;b&gt;Test&lt;/b&gt;" in payload["htmlContent"]
    assert base64.b64decode(payload["attachment"][0]["content"]).startswith(b"%PDF-")
    assert payload["attachment"][0]["name"] == data["filename"]


@pytest.mark.parametrize("change,code", [({"status": "DRAFT"},409),
    ({"employee_primary_email": None},422), ({"employee_primary_email": "invalid"},422)])
async def test_unsendable_payslips_never_call_brevo(mail, change, code):
    data = {**sample_document(), "employee_primary_email": "primary@example.com", **change}
    with pytest.raises(HTTPException) as exc:
        await payslip_email.send(data)
    assert exc.value.status_code == code and not mail[1]


async def test_missing_configuration_never_calls_brevo(mail):
    mail[0].brevo_api_key = SecretStr("")
    with pytest.raises(HTTPException) as exc:
        await payslip_email.send({**sample_document(), "employee_primary_email": "primary@example.com"})
    assert exc.value.status_code == 503 and not mail[1]


@pytest.mark.parametrize("timeout", [False,True])
async def test_provider_failure_is_safe_and_not_retried(mail, monkeypatch, timeout):
    calls = []
    async def fail(self, url, **kwargs):
        calls.append(url)
        if timeout:
            raise httpx.ReadTimeout("private provider detail")
        return httpx.Response(401, text="private provider detail")
    monkeypatch.setattr(payslip_email.httpx.AsyncClient, "post", fail)
    with pytest.raises(HTTPException) as exc:
        await payslip_email.send({**sample_document(), "employee_primary_email": "primary@example.com"})
    assert exc.value.status_code == 502 and len(calls) == 1
    assert "private provider detail" not in exc.value.detail
