"""Verify Google JWTs using Google's fixed JWKS endpoint; never trust decoded client claims."""
import jwt
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from app.core.config import get_settings

keys = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs", lifespan=300, timeout=5)


def decode_google_credential(credential: str, client_id: str) -> dict:
    key = keys.get_signing_key_from_jwt(credential)
    return jwt.decode(credential, key.key, algorithms=["RS256"], audience=client_id,
                      issuer=["accounts.google.com", "https://accounts.google.com"],
                      options={"require": ["exp", "iat", "sub", "aud", "iss", "nonce"]})


async def verify_google_credential(credential: str, nonce: str) -> dict:
    client_id = get_settings().google_client_id.strip()
    if not client_id:
        raise HTTPException(503, "Google sign-in has not been configured")
    try:
        claims = await run_in_threadpool(decode_google_credential, credential, client_id)
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(503, "Google sign-in is temporarily unavailable. Use your password or try again.") from exc
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise HTTPException(401, "Invalid or expired Google credential") from exc
    if claims.get("nonce") != nonce or claims.get("email_verified") is not True or not isinstance(claims.get("sub"), str) or not 1 <= len(claims["sub"]) <= 255:
        raise HTTPException(401, "Invalid Google credential")
    return claims
