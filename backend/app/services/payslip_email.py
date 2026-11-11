"""Email saved payslips; label unapproved statements as drafts."""
import base64
from html import escape

import httpx
from fastapi import HTTPException
from pydantic import EmailStr, TypeAdapter, ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.services.payslip_pdf import render


async def send(data):
    try:
        recipient = str(TypeAdapter(EmailStr).validate_python(data.get("employee_primary_email")))
    except ValidationError:
        raise HTTPException(422, "Add a valid work email to the employee record before sending.")
    settings = get_settings()
    key = settings.brevo_api_key.get_secret_value()
    if not key or not settings.brevo_sender_email:
        raise HTTPException(503, "Payslip email is not configured. Set the Brevo API key and sender email on the server.")
    try:
        sender = str(TypeAdapter(EmailStr).validate_python(settings.brevo_sender_email))
    except ValidationError:
        raise HTTPException(503, "The configured Brevo sender email is invalid.")
    pdf = await run_in_threadpool(render, data)
    period = f"{data['period_start']} to {data['period_end']}"
    draft = data["status"] != "APPROVED"
    payload = {
        "sender": {"email": sender, "name": settings.brevo_sender_name},
        "to": [{"email": recipient, "name": data["employee_name"]}],
        "subject": f"{'DRAFT - ' if draft else ''}Your payslip | {data['company_name']} | {period}",
        "htmlContent": f"<p>Hello {escape(data['employee_name'])},</p>"
            f"<p>Your payslip for {escape(period)} is attached.</p>"
            + ("<p><strong>DRAFT: This payroll has not been approved. Amounts may change.</strong></p>" if draft else "")
            + f"<p>{escape(data['company_name'])}</p><p>This payslip is confidential.</p>",
        "attachment": [{"name": data["filename"], "content": base64.b64encode(pdf).decode("ascii")}],
        "tags": ["payslip"],
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post("https://api.brevo.com/v3/smtp/email",
                headers={"api-key": key, "Accept": "application/json"}, json=payload)
    except httpx.RequestError:
        # A timed-out send may already have been accepted; never automatically retry it.
        raise HTTPException(502, "Could not confirm the email submission. Check Brevo's transactional logs before retrying.")
    if response.status_code != 201:
        raise HTTPException(502, "Brevo did not accept the email. Check the sender verification, API key and transactional email quota.")
    return {"recipient": recipient, "message": "Payslip submitted to Brevo for delivery."}
