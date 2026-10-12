import hashlib
import hmac
import os
import secrets
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, Request
from pydantic import BaseModel

from app.core.db import get_db_connection

SESSION_COOKIE_NAME = "campus_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14
password_hasher = PasswordHasher()
DUMMY_PASSWORD_HASH = password_hasher.hash("invalid-account-password-check")


class AuthenticatedIdentity(BaseModel):
    email: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_student_email(email: str) -> bool:
    local_part, separator, domain = normalize_email(email).partition("@")
    return bool(separator and domain == "ncnu.edu.tw" and local_part.startswith("s")
                and local_part[1:].isdigit())


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_auth_secret() -> bytes:
    secret = os.getenv("SECRET_KEY", "")
    if len(secret) < 32 or "change-me" in secret.lower():
        raise RuntimeError("SECRET_KEY must be configured with a unique value of at least 32 characters.")
    return secret.encode("utf-8")


def keyed_hash(value: str) -> str:
    return hmac.new(get_auth_secret(), value.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    stored_hash = password_hash or DUMMY_PASSWORD_HASH
    try:
        valid = password_hasher.verify(stored_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False
    return valid and password_hash is not None


def create_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def get_authenticated_identity(request: Request) -> AuthenticatedIdentity:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lower(u.email)
                FROM user_sessions AS s
                JOIN users AS u ON u.id = s.user_id
                WHERE s.token_hash = %s
                  AND s.revoked_at IS NULL
                  AND s.expires_at > CURRENT_TIMESTAMP
                """,
                (hash_token(token),),
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return AuthenticatedIdentity(email=row[0])


def session_cookie_options(request: Request) -> dict:
    root_path = os.getenv("ROOT_PATH", "").strip().rstrip("/") or "/"
    secure_setting = os.getenv("SESSION_COOKIE_SECURE", "").strip().lower()
    if secure_setting:
        secure_cookie = secure_setting in {"1", "true", "yes"}
    else:
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        secure_cookie = request.url.scheme == "https" or forwarded_proto == "https"
    return {
        "key": SESSION_COOKIE_NAME,
        "httponly": True,
        "secure": secure_cookie,
        "samesite": "lax",
        "path": root_path,
    }