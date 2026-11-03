import json
import logging
import uuid
from typing import Any
from urllib.parse import parse_qsl, urlencode

import jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_session_maker
from app.models import AuditLog, PlatformAdmin, User

logger = logging.getLogger(__name__)

_SKIP_PATHS = {
    "/health",
    "/domains/context",
    "/domains/tls-allowed",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}
_SECRET_KEYS = {
    "credential",
    "nonce",
    "google_subject",
    "password",
    "password_hash",
    "current_password",
    "new_password",
    "refresh_token",
    "access_token",
    "token",
    "secret",
    "authorization",
    "jwt",
}
_MAX_STORED = 4000


def should_skip_audit(method: str, path: str) -> bool:
    if method.upper() == "OPTIONS":
        return True
    if path in _SKIP_PATHS:
        return True
    return method.upper() == "GET" and path.rstrip("/").endswith("audit-logs")


def redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in _SECRET_KEYS:
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = redact_value(item)
        return cleaned
    if isinstance(value, list):
        return [redact_value(item) for item in value[:50]]
    if isinstance(value, str) and len(value) > 500:
        return f"{value[:500]}…"
    return value


def _clip(value: str) -> str:
    if len(value) <= _MAX_STORED:
        return value
    return f"{value[:_MAX_STORED]}…"


def summarize_request(body: bytes, content_type: str, query: str) -> str:
    parts: list[str] = []
    if query:
        pairs = []
        for key, item in parse_qsl(query, keep_blank_values=True):
            if key.lower() in _SECRET_KEYS:
                pairs.append((key, "[redacted]"))
            else:
                pairs.append((key, item))
        encoded = urlencode(pairs)
        if encoded:
            parts.append(encoded)
    if not body:
        return _clip(" · ".join(parts))
    media = (content_type or "").split(";")[0].strip().lower()
    if media.startswith("multipart/"):
        parts.append("[file upload]")
        return _clip(" · ".join(parts))
    text_body = body.decode("utf-8", errors="replace")
    if media == "application/json" or text_body[:1] in "{[":
        try:
            parts.append(json.dumps(redact_value(json.loads(text_body)), ensure_ascii=False))
            return _clip(" · ".join(parts))
        except json.JSONDecodeError:
            pass
    parts.append(_clip(text_body))
    return _clip(" · ".join(parts))


def response_message(status_code: int, body: bytes | None) -> str:
    if 200 <= status_code < 300:
        return "Successful"
    if not body:
        return f"Failed ({status_code})"
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return _clip(body.decode("utf-8", errors="replace") or f"Failed ({status_code})")
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail.strip():
        return _clip(detail)
    if detail is not None:
        return _clip(json.dumps(detail, ensure_ascii=False))
    return f"Failed ({status_code})"


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def _requester_label(name: str | None, email: str | None) -> str:
    name = (name or "").strip()
    email = (email or "").strip()
    if name and email:
        return f"{name} ({email})"
    return name or email or "Anonymous"


async def _actor_from_token(session: AsyncSession, authorization: str | None) -> tuple[str, uuid.UUID | None, uuid.UUID | None, str]:
    token = _bearer(authorization)
    if token is None:
        return ("ANONYMOUS", None, None, "Anonymous")
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        return ("ANONYMOUS", None, None, "Anonymous")
    kind = str(payload.get("kind") or "tenant")
    try:
        actor_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError):
        return ("ANONYMOUS", None, None, payload.get("email") or "Anonymous")
    tenant_id = None
    raw_tenant = payload.get("tenant_id")
    if raw_tenant:
        try:
            tenant_id = uuid.UUID(str(raw_tenant))
        except ValueError:
            tenant_id = None
    if kind == "platform":
        admin = await session.get(PlatformAdmin, actor_id)
        label = _requester_label(admin.full_name if admin else None, payload.get("email") or (admin.email if admin else None))
        return ("PLATFORM", None, actor_id, label)
    user = await session.get(User, actor_id)
    if user is not None:
        return ("TENANT", user.tenant_id, user.id, _requester_label(user.full_name, user.email))
    return ("TENANT", tenant_id, actor_id, _requester_label(None, payload.get("email")))


async def _actor_from_body(session: AsyncSession, body: bytes) -> tuple[str, uuid.UUID | None, uuid.UUID | None, str]:
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return ("ANONYMOUS", None, None, "Anonymous")
    if not isinstance(payload, dict):
        return ("ANONYMOUS", None, None, "Anonymous")
    email = str(payload.get("email") or "").strip().lower()
    name = str(payload.get("owner_full_name") or "").strip()
    if not email:
        return ("ANONYMOUS", None, None, name or "Anonymous")
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None:
        return ("TENANT", user.tenant_id, user.id, _requester_label(user.full_name, user.email))
    admin = await session.scalar(select(PlatformAdmin).where(PlatformAdmin.email == email))
    if admin is not None:
        return ("PLATFORM", None, admin.id, _requester_label(admin.full_name, admin.email))
    return ("ANONYMOUS", None, None, _requester_label(name, email))


async def record_http_audit(
    *,
    method: str,
    path: str,
    query: str,
    body: bytes,
    content_type: str,
    authorization: str | None,
    status_code: int,
    response_body: bytes | None,
) -> None:
    maker = get_session_maker()
    async with maker() as session:
        try:
            await session.execute(text("SELECT set_config('app.is_platform_admin', 'true', true)"))
            actor_kind, tenant_id, actor_id, requester = await _actor_from_token(session, authorization)
            if actor_kind == "ANONYMOUS" and body:
                actor_kind, tenant_id, actor_id, requester = await _actor_from_body(session, body)
            row = AuditLog(
                tenant_id=tenant_id,
                actor_kind=actor_kind,
                actor_id=actor_id,
                requester=requester,
                action=f"{method.upper()} {path}",
                request=summarize_request(body, content_type, query),
                method=method.upper(),
                path=path[:500],
                status_code=status_code,
                outcome="SUCCESS" if 200 <= status_code < 300 else "FAILED",
                response=response_message(status_code, response_body),
            )
            session.add(row)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Could not write audit log for %s %s", method, path)
