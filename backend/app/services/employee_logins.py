from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from app.core.security import hash_password


async def update_credentials(session, user, email, password=None):
    """Caller authorizes and locks the account; uniqueness is enforced by the DB."""
    user.email = str(email).strip().lower()
    if password is not None:
        user.password_hash = hash_password(password)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(409, "An account with this email already exists") from exc
    return user
