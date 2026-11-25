import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from io import BytesIO

import segno


DEFAULT_REGISTRATION_QR_TTL_SECONDS = 600


def registration_qr_ttl_seconds() -> int:
    raw = os.getenv("REGISTRATION_QR_TTL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_REGISTRATION_QR_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("REGISTRATION_QR_TTL_SECONDS must be an integer.") from exc
    if value < 30 or value > 86400:
        raise RuntimeError("REGISTRATION_QR_TTL_SECONDS must be between 30 and 86400.")
    return value


def create_registration_qr_token() -> str:
    return secrets.token_urlsafe(32)


def registration_qr_expires_at(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    return current + timedelta(seconds=registration_qr_ttl_seconds())


def hash_registration_qr_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def render_registration_qr(token: str) -> bytes:
    qr = segno.make(token, error="m")
    output = BytesIO()
    qr.save(
        output,
        kind="svg",
        scale=6,
        border=4,
        dark="#172554",
        light="#ffffff",
    )
    return output.getvalue()