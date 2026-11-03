from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

import bcrypt
import jwt

from app.core.config import get_settings

TokenUse = Literal["access", "refresh"]
TokenKind = Literal["tenant", "platform"]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def _encode_token(
    *,
    user_id: UUID,
    email: str,
    kind: TokenKind,
    token_use: TokenUse,
    expires_minutes: int,
    tenant_id: UUID | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "kind": kind,
        "token_use": token_use,
        "jti": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    if tenant_id is not None:
        payload["tenant_id"] = str(tenant_id)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    *,
    user_id: UUID,
    email: str,
    tenant_id: UUID | None = None,
    kind: TokenKind = "tenant",
) -> str:
    settings = get_settings()
    return _encode_token(
        user_id=user_id,
        email=email,
        kind=kind,
        token_use="access",
        expires_minutes=settings.access_token_expire_minutes,
        tenant_id=tenant_id,
    )


def create_refresh_token(
    *,
    user_id: UUID,
    email: str,
    tenant_id: UUID | None = None,
    kind: TokenKind = "tenant",
) -> str:
    settings = get_settings()
    return _encode_token(
        user_id=user_id,
        email=email,
        kind=kind,
        token_use="refresh",
        expires_minutes=settings.refresh_token_expire_minutes,
        tenant_id=tenant_id,
    )


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_in: int


def issue_token_pair(
    *,
    user_id: UUID,
    email: str,
    tenant_id: UUID | None = None,
    kind: TokenKind = "tenant",
) -> IssuedTokens:
    settings = get_settings()
    return IssuedTokens(
        access_token=create_access_token(
            user_id=user_id, email=email, tenant_id=tenant_id, kind=kind
        ),
        refresh_token=create_refresh_token(
            user_id=user_id, email=email, tenant_id=tenant_id, kind=kind
        ),
        expires_in=settings.access_token_expire_minutes * 60,
        refresh_expires_in=settings.refresh_token_expire_minutes * 60,
    )


def decode_token(token: str, *, token_use: TokenUse) -> dict[str, Any]:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("token_use") != token_use:
        raise jwt.InvalidTokenError("Wrong token type")
    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    return decode_token(token, token_use="access")


def decode_refresh_token(token: str) -> dict[str, Any]:
    return decode_token(token, token_use="refresh")
