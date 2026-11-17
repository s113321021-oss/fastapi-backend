import base64
import hashlib
import hmac
from io import BytesIO

import segno

from app.core.password_auth import get_auth_secret


def create_registration_qr_token(registration_id: int, user_id: int) -> str:
    payload = f"registration-qr:v1:{registration_id}:{user_id}".encode("ascii")
    signature = hmac.new(get_auth_secret(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


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