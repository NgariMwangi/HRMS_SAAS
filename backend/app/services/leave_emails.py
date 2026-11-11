"""Queue leave emails atomically with workflow changes, deliver after commit."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from html import escape

import httpx
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.db.session import get_session_maker
from app.models import Company, Employee, EmployeeSupervisor, LeaveEmail, LeaveType, Tenant, User

logger = logging.getLogger("leave.email")


async def queue(session, request, event, *, decision=None, actor_employee_id=None, note=None):
    company = await session.get(Company, request.company_id)
    employee = await session.get(Employee, request.employee_id)
    leave_type = await session.get(LeaveType, request.leave_type_id)
    owners = (await session.scalars(select(User).where(User.tenant_id == company.tenant_id,
        User.role == "OWNER", User.status == "ACTIVE"))).all()
    recipients = []
    if event == "APPLIED":
        recipients.append(("employee", employee.id, "application_confirmation", "Leave application received",
            "Your leave application has been recorded."))
        supervisors = (await session.scalars(select(Employee).join(EmployeeSupervisor,
            EmployeeSupervisor.supervisor_id == Employee.id).where(EmployeeSupervisor.employee_id == employee.id,
                Employee.company_id == company.id, Employee.status == "ACTIVE"))).all()
        for supervisor in supervisors:
            action = "Please sign in and respond to the request." if request.status == "PENDING_SUPERVISOR" else "This is an application alert; the workspace owner handles the next step."
            recipients.append(("employee", supervisor.id, "supervisor_alert", "New leave application", action))
        for owner in owners:
            action = "The request is awaiting the supervisor's response." if request.status == "PENDING_SUPERVISOR" else "Please sign in and respond to the request."
            if request.status == "APPROVED": action = "This application was approved when it was recorded."
            recipients.append(("owner", owner.id, "owner_alert", "New leave application", action))
    elif event == "SUPERVISOR_DECISION":
        outcome = "approved" if decision == "APPROVED" else "declined"
        recipients.append(("employee", actor_employee_id, "supervisor_confirmation", "Supervisor response recorded",
            f"Your {outcome} response has been recorded. The workspace owner must now make the final decision."))
        for owner in owners:
            recipients.append(("owner", owner.id, "owner_action", f"Supervisor {outcome} leave application",
                f"The supervisor has {outcome} this application. Please sign in and approve or decline it as HR."))
    elif event == "HR_DECISION":
        outcome = "approved" if decision == "APPROVED" else "declined"
        for owner in owners:
            recipients.append(("owner", owner.id, "owner_confirmation", "HR response recorded",
                f"The final HR response ({outcome}) has been recorded."))
        recipients.append(("employee", employee.id, "employee_decision", f"Leave application {outcome}",
            f"The workspace owner has {outcome} your leave application."))
    name = " ".join(filter(None, [employee.first_name, employee.other_names, employee.last_name]))
    details = f"<p><strong>Employee:</strong> {escape(name)} ({escape(employee.employee_number)})<br/>" \
        f"<strong>Leave:</strong> {escape(leave_type.name)}<br/><strong>Dates:</strong> {request.start_on} to {request.end_on}<br/>" \
        f"<strong>Days:</strong> {request.days}<br/><strong>Reference:</strong> {request.id}</p>"
    if note: details += f"<p><strong>Decision note:</strong> {escape(note)}</p>"
    for kind, identity, purpose, title, message in recipients:
        path = "/employee/leave" if purpose in {"application_confirmation", "employee_decision"} else "/app/leave"
        url = f"https://{get_settings().hrms_base_domain}{path}"
        await session.execute(insert(LeaveEmail).values(tenant_id=company.tenant_id, company_id=company.id,
            request_id=request.id, event=event, purpose=purpose, recipient_kind=kind, recipient_id=identity,
            subject=f"{title} | {company.name}"[:500], html_body=f"<p>{escape(message)}</p>{details}<p><a href=\"{escape(url, quote=True)}\">Open leave requests</a></p><p>{escape(company.name)}</p>",
            status="PENDING", attempts=0).on_conflict_do_nothing(constraint="uq_leave_email_event"))


async def recipient_email(session, row):
    if row.recipient_kind == "owner":
        owner = await session.get(User, row.recipient_id)
        if not owner or owner.tenant_id != row.tenant_id or owner.role != "OWNER" or owner.status != "ACTIVE": return None
        if owner.employee_id:
            person = await session.get(Employee, owner.employee_id)
            company = await session.get(Company, person.company_id) if person else None
            address = person.email if person and company and company.tenant_id == row.tenant_id and person.status == "ACTIVE" else None
        else:
            address = owner.email
    else:
        person = await session.get(Employee, row.recipient_id)
        address = person.email if person and person.company_id == row.company_id and person.status == "ACTIVE" else None
    try: return str(TypeAdapter(EmailStr).validate_python(address))
    except ValidationError: return None


async def deliver_pending(limit=20):
    settings = get_settings()
    if not settings.brevo_api_key.get_secret_value() or not settings.brevo_sender_email: return 0
    try: sender = str(TypeAdapter(EmailStr).validate_python(settings.brevo_sender_email))
    except ValidationError: return 0
    processed = 0
    for _ in range(limit):
        async with get_session_maker()() as session:
            await session.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
            now = datetime.now(timezone.utc)
            row = await session.scalar(select(LeaveEmail).where(LeaveEmail.status.in_(["PENDING", "BLOCKED"]),
                LeaveEmail.next_attempt_at <= now).order_by(LeaveEmail.created_at, LeaveEmail.id).with_for_update(skip_locked=True).limit(1))
            if row is None: return processed
            company = await session.get(Company, row.company_id)
            tenant = await session.get(Tenant, row.tenant_id)
            if not company or company.status != "ACTIVE" or not tenant or tenant.status != "ACTIVE":
                row.status = "BLOCKED"; row.last_error = "workspace_inactive"
                row.next_attempt_at = now + timedelta(minutes=5)
                await session.commit(); continue
            address = await recipient_email(session, row)
            if not address:
                row.status = "BLOCKED"; row.last_error = "missing_work_email_or_inactive_recipient"
                row.next_attempt_at = now + timedelta(minutes=1)
                await session.commit(); continue
            row.recipient_email = address
            row.attempts += 1
            payload = {"sender":{"email":sender,"name":settings.brevo_sender_name},"to":[{"email":address}],
                "subject":row.subject,"htmlContent":row.html_body,"tags":["leave"],"headers":{"IdempotencyKey":str(row.id)}}
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post("https://api.brevo.com/v3/smtp/email",
                        headers={"api-key":settings.brevo_api_key.get_secret_value()},json=payload)
                if response.status_code == 201:
                    row.status = "SENT"; row.sent_at = now; row.last_error = None
                elif response.status_code == 429:
                    row.status = "PENDING"; row.last_error = "provider_rate_limit"
                else:
                    row.status = "UNCERTAIN" if response.status_code >= 500 else "FAILED"
                    row.last_error = f"provider_http_{response.status_code}"
            except (httpx.ConnectError, httpx.ConnectTimeout):
                row.status = "PENDING"; row.last_error = "provider_unreachable"
            except httpx.RequestError:
                row.status = "UNCERTAIN"; row.last_error = "check_brevo_logs_before_retry"
            if row.status == "PENDING":
                if row.attempts >= 5: row.status = "FAILED"
                row.next_attempt_at = now + timedelta(seconds=min(900, 30 * 2 ** row.attempts))
            if row.last_error:
                logger.warning("Leave email %s status=%s reason=%s", row.id, row.status, row.last_error)
            await session.commit()
            processed += 1
    return processed


async def serve():
    while True:
        try: await deliver_pending()
        except Exception:
            # Avoid logging provider payloads, credentials, or personal leave details.
            logger.error("Leave email delivery pass failed; queued messages remain available")
        await asyncio.sleep(5)
