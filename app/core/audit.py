import json
import logging
from typing import Any

from fastapi import Request

from app.core.db import get_db_connection
from app.core.password_auth import trust_proxy_headers

logger = logging.getLogger(__name__)


def request_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    if trust_proxy_headers():
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip() or None
    if request.client and request.client.host:
        return request.client.host
    return None


def record_audit_event(
    *,
    action: str,
    user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    detail: dict[str, Any] | None = None,
    request: Request | None = None,
    conn=None,
) -> None:
    payload = json.dumps(detail, ensure_ascii=False, default=str) if detail else None
    ip_address = request_ip(request)
    user_agent = request.headers.get("user-agent", "")[:512] if request else None
    resource_id_str = str(resource_id) if resource_id is not None else None

    def _write(active_conn) -> None:
        with active_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audit_logs (user_id, action, resource_type, resource_id, detail, ip_address, user_agent)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, action, resource_type, resource_id_str, payload, ip_address, user_agent),
            )

    try:
        if conn is not None:
            _write(conn)
        else:
            with get_db_connection() as audit_conn:
                _write(audit_conn)
                audit_conn.commit()
    except Exception:
        logger.exception("Failed to record audit event: %s", action)
