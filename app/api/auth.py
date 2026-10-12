import psycopg
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.core.db import get_db_connection
from app.core.password_auth import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_session_token,
    get_auth_secret,
    hash_password,
    hash_token,
    is_student_email,
    keyed_hash,
    normalize_email,
    session_cookie_options,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class AccountRegistration(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=128)


class PasswordLogin(BaseModel):
    email: str = Field(
        min_length=3,
        max_length=320,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    password: str = Field(min_length=1, max_length=128)


def _request_is_limited(email: str, client_ip: str) -> bool:
    email_hash = keyed_hash(f"email:{email}")
    ip_hash = keyed_hash(f"ip:{client_ip}")
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM auth_login_attempts "
                "WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 day'"
            )
            cur.execute(
                """
                  SELECT COUNT(*) FILTER (WHERE email_hash = %s AND ip_hash = %s),
                      COUNT(*) FILTER (WHERE ip_hash = %s)
                FROM auth_login_attempts
                WHERE created_at > CURRENT_TIMESTAMP - INTERVAL '15 minutes'
                """,
                  (email_hash, ip_hash, ip_hash),
            )
            email_count, ip_count = cur.fetchone()
            cur.execute(
                "INSERT INTO auth_login_attempts (email_hash, ip_hash) VALUES (%s, %s)",
                (email_hash, ip_hash),
            )
            conn.commit()
    return email_count >= 5 or ip_count >= 30


def _set_session(user_id: int, request: Request, response: Response) -> str:
    session_token, session_hash = create_session_token()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_sessions (token_hash, user_id, expires_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'))
                """,
                (session_hash, user_id, SESSION_MAX_AGE_SECONDS),
            )
        conn.commit()
    response.set_cookie(
        value=session_token,
        max_age=SESSION_MAX_AGE_SECONDS,
        **session_cookie_options(request),
    )
    response.headers["Cache-Control"] = "no-store"
    return session_token


@router.post("/register", status_code=201)
def register_account(
    payload: AccountRegistration,
    request: Request,
    response: Response,
) -> dict:
    email = normalize_email(payload.email)
    display_name = payload.display_name.strip()
    if not is_student_email(email):
        raise HTTPException(
            status_code=422,
            detail="請使用 s學號@ncnu.edu.tw 格式的學生信箱。",
        )
    if not display_name:
        raise HTTPException(status_code=422, detail="請填寫姓名。")

    client_ip = request.client.host if request.client else "unknown"
    response.headers["Cache-Control"] = "no-store"
    try:
        get_auth_secret()
        limited = _request_is_limited(email, client_ip)
    except (RuntimeError, psycopg.Error):
        raise HTTPException(status_code=503, detail="帳號服務目前無法使用。") from None
    if limited:
        raise HTTPException(status_code=429, detail="註冊嘗試過於頻繁，請稍後再試。")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (external_subject, email, display_name, password_hash, role)
                VALUES (NULL, %s, %s, %s, 'student')
                ON CONFLICT DO NOTHING
                RETURNING id, email, display_name, role
                """,
                (email, display_name, hash_password(payload.password)),
            )
            user_row = cur.fetchone()
            if user_row is None:
                raise HTTPException(status_code=409, detail="此信箱已有帳號，請直接登入。")
            conn.commit()
    _set_session(user_row[0], request, response)
    return dict(zip(("id", "email", "display_name", "role"), user_row))


@router.post("/login")
def login(
    payload: PasswordLogin,
    request: Request,
    response: Response,
) -> dict:
    email = normalize_email(payload.email)
    client_ip = request.client.host if request.client else "unknown"
    try:
        get_auth_secret()
        limited = _request_is_limited(email, client_ip)
    except (RuntimeError, psycopg.Error):
        raise HTTPException(status_code=503, detail="帳號服務目前無法使用。") from None
    if limited:
        raise HTTPException(status_code=429, detail="登入嘗試過於頻繁，請稍後再試。")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, display_name, role, password_hash "
                "FROM users WHERE lower(email) = %s",
                (email,),
            )
            user_row = cur.fetchone()

    password_hash = user_row[4] if user_row else None
    if not verify_password(password_hash, payload.password):
        raise HTTPException(status_code=401, detail="信箱或密碼錯誤。")

    _set_session(user_row[0], request, response)
    return dict(zip(("id", "email", "display_name", "role"), user_row[:4]))


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE user_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE token_hash = %s",
                    (hash_token(token),),
                )
                conn.commit()
    response.delete_cookie(**session_cookie_options(request))
    response.headers["Cache-Control"] = "no-store"
    return response