from app.services.domain_scope import require_domain_account
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_tenant_db
from app.api.routes.auth import _token_response
from app.api.routes.employee_portal import portal_employee
from app.core.config import get_settings
from app.core.security import verify_password
from app.db.session import get_session
from app.models import Company, Employee, Tenant, User
from app.models.google_challenge import GoogleChallenge
from app.schemas.auth import TokenResponse
from app.services.google_auth import verify_google_credential

router = APIRouter(prefix="/auth/google", tags=["Google sign-in"])
COOKIE = "hrms_google_nonce"


@router.get("/config")
async def configuration(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return {"client_id": get_settings().google_client_id, "enabled": bool(get_settings().google_client_id.strip())}


@router.get("/challenge")
async def challenge(request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    if not get_settings().google_client_id.strip():
        raise HTTPException(503, "Google sign-in has not been configured")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await session.execute(delete(GoogleChallenge).where(GoogleChallenge.expires_at < now))
    previous = request.cookies.get(COOKIE)
    if previous:
        await session.execute(delete(GoogleChallenge).where(GoogleChallenge.digest == hashlib.sha256(previous.encode()).hexdigest()))
    nonce = secrets.token_urlsafe(32)
    session.add(GoogleChallenge(digest=hashlib.sha256(nonce.encode()).hexdigest(), expires_at=now + timedelta(minutes=5)))
    response.set_cookie(COOKIE, nonce, max_age=300, httponly=True, secure=get_settings().google_cookie_secure, samesite="lax", path="/auth/google")
    response.headers["Cache-Control"] = "no-store"
    return {"nonce": nonce}


class GoogleCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: str = Field(min_length=20, max_length=16000)
    # First-time linking requires possession of the existing HR-issued password.
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value):
        if value and len(value.encode()) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


async def verified(payload, request, response, session):
    nonce = request.cookies.get(COOKIE, "")
    if not nonce or len(nonce) > 100:
        raise HTTPException(401, "Google sign-in expired. Please try again.")
    claims = await verify_google_credential(payload.credential, nonce)
    consumed = await session.scalar(delete(GoogleChallenge).where(
        GoogleChallenge.digest == hashlib.sha256(nonce.encode()).hexdigest(), GoogleChallenge.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)).returning(GoogleChallenge.digest))
    if not consumed:
        raise HTTPException(401, "Google sign-in expired. Please try again.")
    response.delete_cookie(COOKIE, path="/auth/google")
    response.headers["Cache-Control"] = "no-store"
    return claims


@router.post("/login", response_model=TokenResponse)
async def login(payload: GoogleCredential, request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    claims = await verified(payload, request, response, session)
    user = await session.scalar(select(User).where(User.google_subject == claims["sub"]).with_for_update())
    if user is None:
        if not payload.email or not payload.password:
            raise HTTPException(409, "Link your existing employee account: enter your work login email and password, then select Google again.")
        user = await session.scalar(select(User).where(User.email == str(payload.email).lower()).with_for_update())
        if user is None or not verify_password(payload.password, user.password_hash):
            raise HTTPException(401, "Invalid employee email or password")
        if user.google_subject and user.google_subject != claims["sub"]:
            raise HTTPException(409, "This account is already linked to another Google account")
    if user.status != "ACTIVE":
        raise HTTPException(403, "Account is not active")
    tenant = await session.get(Tenant, user.tenant_id)
    employee = await session.scalar(select(Employee).join(Company, Employee.company_id == Company.id).where(
        Employee.id == user.employee_id, Company.tenant_id == user.tenant_id, Company.status == "ACTIVE", Employee.status == "ACTIVE"))
    if tenant is None or tenant.status != "ACTIVE" or employee is None:
        raise HTTPException(403, "An active employee account is required. Contact HR for help.")
    await require_domain_account(request, session, user, employee_login=True)
    user.google_subject = claims["sub"]
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "Google account is already linked") from exc
    return _token_response(user=user, tenant=tenant)


@router.post("/link")
async def link(payload: GoogleCredential, request: Request, response: Response, employee: Employee = Depends(portal_employee), user: User = Depends(get_current_user), session: AsyncSession = Depends(get_tenant_db)):
    # Password confirmation protects account binding even on an unattended session.
    await session.refresh(user, with_for_update=True)
    if not payload.password or not verify_password(payload.password, user.password_hash):
        raise HTTPException(400, "Enter your current password to link Google")
    claims = await verified(payload, request, response, session)
    if user.google_subject and user.google_subject != claims["sub"]:
        raise HTTPException(409, "Disconnect your existing Google account first")
    user.google_subject = claims["sub"]
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "Google account is already linked to another employee") from exc
    return {"message": "Google account linked"}


class PasswordConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value):
        if len(value.encode()) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


@router.post("/unlink")
async def unlink(payload: PasswordConfirmation, employee: Employee = Depends(portal_employee), user: User = Depends(get_current_user), session: AsyncSession = Depends(get_tenant_db)):
    await session.refresh(user, with_for_update=True)
    if not payload.password or not verify_password(payload.password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.google_subject = None
    return {"message": "Google account disconnected"}
