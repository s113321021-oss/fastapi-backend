from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import Response as StarletteResponse

from app.core.db import get_db_connection
from app.core.password_auth import (
    get_authenticated_identity,
    hash_password,
    is_student_email,
    normalize_email,
)
from app.core.registration_qr import (
    create_registration_qr_token,
    hash_registration_qr_token,
    render_registration_qr,
)
from app.models.main import (
    AuthenticatedIdentity,
    ActivityCreate,
    ActivityReview,
    ActivityStatus,
    ActivityUpdate,
    CheckInQrLookup,
    Role,
    User,
    UserProvision,
)

router = APIRouter(prefix="/api")


def get_current_user(
    identity: AuthenticatedIdentity = Depends(get_authenticated_identity),
) -> User:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, display_name, role
                FROM users
                WHERE lower(email) = %s
                """,
                (normalize_email(identity.email),),
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return User(
        id=row[0],
        email=row[1],
        display_name=row[2],
        role=Role(row[3]),
    )


def require_role(user: User, required_role: Role) -> User:
    if user.role != required_role:
        raise HTTPException(status_code=403, detail="Insufficient permissions.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    return require_role(user, Role.ADMIN)


def require_student(user: User = Depends(get_current_user)) -> User:
    return require_role(user, Role.STUDENT)


def require_check_in_staff(user: User = Depends(get_current_user)) -> User:
    if user.role not in {Role.ADMIN, Role.CHECK_IN}:
        raise HTTPException(status_code=403, detail="Insufficient permissions.")
    return user


def activity_response(row: tuple) -> dict:
    return {
        "id": row[0],
        "title": row[1],
        "description": row[2],
        "location": row[3],
        "starts_at": row[4],
        "registration_deadline": row[5],
        "status": row[6],
        "review_note": row[7],
        "created_at": row[8],
        "published_at": row[9],
        "category": row[10],
        "organizer": row[11],
        "capacity": row[12],
        "duration": row[13],
        "registered_count": row[14],
        "ends_at": row[15],
        "registration_opens_at": row[16],
        "category_label": {
            "talk": "講座分享",
            "workshop": "工作坊",
            "club": "社團活動",
            "culture": "藝文展演",
            "sports": "運動休閒",
            "career": "職涯成長",
            "other": "其他活動",
        }.get(row[10], "其他活動"),
        "start_time": row[4].strftime("%H:%M"),
        "icon": {
            "talk": "💡",
            "workshop": "✳",
            "club": "♡",
            "culture": "♫",
            "sports": "🏃",
            "career": "📝",
            "other": "✦",
        }.get(row[10], "✦"),
        "theme": {
            "talk": "lavender",
            "workshop": "peach",
            "club": "mint",
            "culture": "blue",
            "sports": "yellow",
            "career": "rose",
            "other": "lavender",
        }.get(row[10], "lavender"),
        "featured": False,
        "tags": [],
    }


ACTIVITY_COLUMNS = """
    id, title, description, location, starts_at, registration_deadline,
    status, review_note, created_at, published_at, category, organizer,
    capacity, duration,
    (SELECT COUNT(*) FROM registrations WHERE activity_id = activities.id),
    ends_at, registration_opens_at
"""

@router.get("/auth/me", response_model=User)
def read_current_user(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/activities")
def browse_activities() -> list[dict]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {ACTIVITY_COLUMNS} FROM activities "
                "WHERE status = 'published' ORDER BY starts_at ASC"
            )
            rows = cur.fetchall()
    return [activity_response(row) for row in rows]


@router.get("/activities/{activity_id}")
def read_activity(activity_id: int) -> dict:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT {ACTIVITY_COLUMNS} FROM activities "
                "WHERE id = %s AND status = 'published'",
                (activity_id,),
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Activity not found.")
    return activity_response(row)


@router.post("/activities/{activity_id}/registrations", status_code=201)
def register_for_activity(
    activity_id: int,
    user: User = Depends(require_student),
) -> dict:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT registration_opens_at, registration_deadline, capacity
                FROM activities
                WHERE id = %s AND status = 'published'
                FOR UPDATE
                """,
                (activity_id,),
            )
            activity = cur.fetchone()
            if activity is None:
                raise HTTPException(status_code=404, detail="Activity not found.")
            now = datetime.now(activity[1].tzinfo)
            if activity[0] is not None and activity[0] > now:
                raise HTTPException(
                    status_code=409,
                    detail="Registration has not opened yet.",
                )
            if activity[1] < now:
                raise HTTPException(
                    status_code=409,
                    detail="Registration deadline has passed.",
                )
            cur.execute(
                "SELECT COUNT(*) FROM registrations WHERE activity_id = %s",
                (activity_id,),
            )
            registration_count = cur.fetchone()[0]
            if activity[2] and registration_count >= activity[2]:
                raise HTTPException(
                    status_code=409,
                    detail="Activity is full.",
                )
            cur.execute(
                """
                INSERT INTO registrations (activity_id, user_id)
                VALUES (%s, %s)
                ON CONFLICT (activity_id, user_id) DO NOTHING
                RETURNING id, activity_id, registered_at
                """,
                (activity_id, user.id),
            )
            row = cur.fetchone()
            if row is None:
                raise HTTPException(
                    status_code=409,
                    detail="You are already registered for this activity.",
                )
            conn.commit()
    return {"id": row[0], "activity_id": row[1], "registered_at": row[2]}


@router.get("/registrations/me")
def read_my_registrations(user: User = Depends(require_student)) -> list[dict]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, a.id, a.title, a.location, a.starts_at,
                       r.registered_at, r.checked_in_at
                FROM registrations AS r
                JOIN activities AS a ON a.id = r.activity_id
                WHERE r.user_id = %s
                ORDER BY r.registered_at DESC
                """,
                (user.id,),
            )
            rows = cur.fetchall()
    return [
        {
            "id": row[0],
            "activity_id": row[1],
            "activity_title": row[2],
            "location": row[3],
            "starts_at": row[4],
            "registered_at": row[5],
            "checked_in_at": row[6],
        }
        for row in rows
    ]


@router.get("/registrations/me/{registration_id}/qr")
def read_my_registration_qr(
    registration_id: int,
    user: User = Depends(require_student),
) -> StarletteResponse:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM registrations WHERE id = %s AND user_id = %s FOR UPDATE",
                (registration_id, user.id),
            )
            registration = cur.fetchone()
            if registration is None:
                raise HTTPException(status_code=404, detail="Registration not found.")

            try:
                token = create_registration_qr_token(registration_id, user.id)
            except RuntimeError:
                raise HTTPException(
                    status_code=503,
                    detail="QR Code 服務尚未完成安全設定。",
                ) from None
            token_hash = hash_registration_qr_token(token)
            cur.execute(
                "UPDATE registrations SET qr_token_hash = %s WHERE id = %s AND user_id = %s",
                (token_hash, registration_id, user.id),
            )
        conn.commit()

    response = StarletteResponse(render_registration_qr(token), media_type="image/svg+xml")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@router.post("/admin/users", status_code=201, response_model=User)
def provision_user(
    user_input: UserProvision,
    admin: User = Depends(require_admin),
) -> User:
    del admin
    if user_input.role is Role.STUDENT and not is_student_email(user_input.email):
        raise HTTPException(
            status_code=422,
            detail="Student accounts must use an NCNU student email address.",
        )
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            normalized_email = normalize_email(user_input.email)
            cur.execute(
                "SELECT id FROM users WHERE lower(email) = %s",
                (normalized_email,),
            )
            existing_user = cur.fetchone()
            if existing_user is None and user_input.password is None:
                raise HTTPException(
                    status_code=422,
                    detail="A password is required when creating an account.",
                )
            cur.execute(
                """
                INSERT INTO users (email, display_name, role, password_hash)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (lower(email))
                DO UPDATE SET display_name = EXCLUDED.display_name,
                              role = EXCLUDED.role,
                              password_hash = COALESCE(EXCLUDED.password_hash, users.password_hash)
                RETURNING id, email, display_name, role
                """,
                (
                    normalized_email,
                    user_input.display_name,
                    user_input.role.value,
                    hash_password(user_input.password) if user_input.password else None,
                ),
            )
            row = cur.fetchone()
            conn.commit()
    return User(
        id=row[0],
        email=row[1],
        display_name=row[2],
        role=Role(row[3]),
    )


@router.post("/admin/activities", status_code=201)
def create_activity_draft(
    activity: ActivityCreate,
    admin: User = Depends(require_admin),
) -> dict:
    if activity.registration_deadline > activity.starts_at:
        raise HTTPException(
            status_code=422,
            detail="Registration deadline must not be after the activity start.",
        )
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO activities (
                    title, description, location, organizer, category,
                    capacity, duration, starts_at,
                    ends_at, registration_opens_at, registration_deadline, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    activity.title,
                    activity.description,
                    activity.location,
                    activity.organizer,
                    activity.category.value,
                    activity.capacity,
                    activity.duration,
                    activity.starts_at,
                    activity.ends_at,
                    activity.registration_opens_at,
                    activity.registration_deadline,
                    admin.id,
                ),
            )
            activity_id = cur.fetchone()[0]
            cur.execute(
                f"SELECT {ACTIVITY_COLUMNS} FROM activities WHERE id = %s",
                (activity_id,),
            )
            row = cur.fetchone()
            conn.commit()
    return activity_response(row)


@router.put("/admin/activities/{activity_id}")
def update_activity(
    activity_id: int,
    activity: ActivityUpdate,
    admin: User = Depends(require_admin),
) -> dict:
    del admin
    if activity.registration_deadline > activity.starts_at:
        raise HTTPException(
            status_code=422,
            detail="Registration deadline must not be after the activity start.",
        )
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE activities
                SET title = %s, description = %s, location = %s,
                    organizer = %s, category = %s, capacity = %s,
                    duration = %s, starts_at = %s,
                    ends_at = %s, registration_opens_at = %s,
                    registration_deadline = %s, status = 'draft',
                    review_note = NULL
                WHERE id = %s AND status IN ('draft', 'approved', 'rejected')
                RETURNING id
                """,
                (
                    activity.title,
                    activity.description,
                    activity.location,
                    activity.organizer,
                    activity.category.value,
                    activity.capacity,
                    activity.duration,
                    activity.starts_at,
                    activity.ends_at,
                    activity.registration_opens_at,
                    activity.registration_deadline,
                    activity_id,
                ),
            )
            updated = cur.fetchone()
            if updated is None:
                cur.execute("SELECT id FROM activities WHERE id = %s", (activity_id,))
                exists = cur.fetchone()
                if exists is None:
                    raise HTTPException(status_code=404, detail="Activity not found.")
                raise HTTPException(
                    status_code=409,
                    detail="Only unpublished activities can be edited.",
                )
            cur.execute(
                f"SELECT {ACTIVITY_COLUMNS} FROM activities WHERE id = %s",
                (activity_id,),
            )
            row = cur.fetchone()
            conn.commit()
    return activity_response(row)


@router.get("/admin/activities")
def list_admin_activities(
    status: ActivityStatus | None = None,
    admin: User = Depends(require_admin),
) -> list[dict]:
    del admin
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if status is None:
                cur.execute(
                    f"SELECT {ACTIVITY_COLUMNS} FROM activities ORDER BY created_at DESC"
                )
            else:
                cur.execute(
                    f"SELECT {ACTIVITY_COLUMNS} FROM activities "
                    "WHERE status = %s ORDER BY created_at DESC",
                    (status.value,),
                )
            rows = cur.fetchall()
    return [activity_response(row) for row in rows]


@router.delete("/admin/activities/{activity_id}", status_code=204)
def discard_activity(
    activity_id: int,
    admin: User = Depends(require_admin),
) -> None:
    del admin
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM activities
                WHERE id = %s AND status IN ('draft', 'approved', 'rejected')
                RETURNING id
                """,
                (activity_id,),
            )
            deleted = cur.fetchone()
            if deleted is None:
                cur.execute("SELECT id FROM activities WHERE id = %s", (activity_id,))
                exists = cur.fetchone()
                if exists is None:
                    raise HTTPException(status_code=404, detail="Activity not found.")
                raise HTTPException(
                    status_code=409,
                    detail="Only unpublished activities can be discarded.",
                )
            conn.commit()


@router.post("/admin/activities/{activity_id}/review")
def review_activity(
    activity_id: int,
    review: ActivityReview,
    admin: User = Depends(require_admin),
) -> dict:
    del admin
    if not review.approved and not (review.note and review.note.strip()):
        raise HTTPException(
            status_code=422,
            detail="A review note is required when rejecting an activity.",
        )
    next_status = (
        ActivityStatus.APPROVED if review.approved else ActivityStatus.REJECTED
    )
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE activities
                SET status = %s, review_note = %s
                WHERE id = %s AND status = 'draft'
                RETURNING id
                """,
                (next_status.value, review.note, activity_id),
            )
            updated = cur.fetchone()
            if updated is None:
                cur.execute("SELECT id FROM activities WHERE id = %s", (activity_id,))
                exists = cur.fetchone()
                if exists is None:
                    raise HTTPException(status_code=404, detail="Activity not found.")
                raise HTTPException(
                    status_code=409,
                    detail="Only draft activities can be reviewed.",
                )
            cur.execute(
                f"SELECT {ACTIVITY_COLUMNS} FROM activities WHERE id = %s",
                (activity_id,),
            )
            row = cur.fetchone()
            conn.commit()
    return activity_response(row)


@router.post("/admin/activities/{activity_id}/publish")
def publish_activity(
    activity_id: int,
    admin: User = Depends(require_admin),
) -> dict:
    del admin
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE activities
                SET status = 'published', published_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'approved'
                RETURNING id
                """,
                (activity_id,),
            )
            updated = cur.fetchone()
            if updated is None:
                cur.execute("SELECT id FROM activities WHERE id = %s", (activity_id,))
                exists = cur.fetchone()
                if exists is None:
                    raise HTTPException(status_code=404, detail="Activity not found.")
                raise HTTPException(
                    status_code=409,
                    detail="Only approved activities can be published.",
                )
            cur.execute(
                f"SELECT {ACTIVITY_COLUMNS} FROM activities WHERE id = %s",
                (activity_id,),
            )
            row = cur.fetchone()
            conn.commit()
    return activity_response(row)


@router.get("/admin/activities/statistics")
def activity_statistics(admin: User = Depends(require_admin)) -> list[dict]:
    del admin
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.id, a.title, a.status, a.capacity,
                       COUNT(r.id)::INTEGER AS registration_count,
                       COUNT(r.checked_in_at)::INTEGER AS check_in_count,
                       (COUNT(r.id) - COUNT(r.checked_in_at))::INTEGER AS not_checked_in_count,
                       CASE WHEN a.capacity > 0
                            THEN GREATEST(a.capacity - COUNT(r.id)::INTEGER, 0)
                            ELSE NULL
                       END AS remaining_capacity,
                       COALESCE(
                           ROUND(100.0 * COUNT(r.checked_in_at) / NULLIF(COUNT(r.id), 0), 1),
                           0
                       ) AS check_in_rate
                FROM activities AS a
                LEFT JOIN registrations AS r ON r.activity_id = a.id
                GROUP BY a.id
                ORDER BY a.id
                """
            )
            rows = cur.fetchall()
    return [
        {
            "activity_id": row[0],
            "title": row[1],
            "status": row[2],
            "capacity": row[3],
            "registration_count": row[4],
            "check_in_count": row[5],
            "not_checked_in_count": row[6],
            "remaining_capacity": row[7],
            "check_in_rate": float(row[8]),
        }
        for row in rows
    ]


@router.get("/check-in/registrations")
def find_registrations_for_check_in(
    activity_id: int,
    search: str | None = Query(default=None, max_length=255),
    staff: User = Depends(require_check_in_staff),
) -> list[dict]:
    del staff
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, a.id, a.title, u.display_name, u.email,
                       r.registered_at, r.checked_in_at
                FROM registrations AS r
                JOIN activities AS a ON a.id = r.activity_id
                JOIN users AS u ON u.id = r.user_id
                WHERE a.id = %s
                                      AND (%s::text IS NULL OR u.display_name ILIKE %s OR u.email ILIKE %s OR r.id::text = %s)
                ORDER BY u.display_name
                """,
                (
                    activity_id,
                    search,
                    f"%{search}%" if search is not None else None,
                    f"%{search}%" if search is not None else None,
                    search,
                ),
            )
            rows = cur.fetchall()
    return [
        {
            "registration_id": row[0],
            "activity_id": row[1],
            "activity_title": row[2],
            "student_name": row[3],
            "student_email": row[4],
            "registered_at": row[5],
            "checked_in_at": row[6],
        }
        for row in rows
    ]


@router.post("/check-in/qr/lookup")
def find_registration_by_qr(
    payload: CheckInQrLookup,
    staff: User = Depends(require_check_in_staff),
) -> dict:
    del staff
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, a.id, a.title, u.display_name, u.email,
                       r.registered_at, r.checked_in_at
                FROM registrations AS r
                JOIN activities AS a ON a.id = r.activity_id
                JOIN users AS u ON u.id = r.user_id
                WHERE r.qr_token_hash = %s
                                      AND (%s::integer IS NULL OR a.id = %s)
                """,
                                (
                                        hash_registration_qr_token(payload.token),
                                        payload.activity_id,
                                        payload.activity_id,
                                ),
            )
            row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="QR Code not found.")
    return {
        "registration_id": row[0],
        "activity_id": row[1],
        "activity_title": row[2],
        "student_name": row[3],
        "student_email": row[4],
        "registered_at": row[5],
        "checked_in_at": row[6],
    }


@router.post("/check-in/registrations/{registration_id}/confirm")
def confirm_check_in(
    registration_id: int,
    staff: User = Depends(require_check_in_staff),
) -> dict:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE registrations
                SET checked_in_at = CURRENT_TIMESTAMP, checked_in_by = %s
                WHERE id = %s AND checked_in_at IS NULL
                RETURNING id, activity_id, checked_in_at
                """,
                (staff.id, registration_id),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "SELECT id FROM registrations WHERE id = %s",
                    (registration_id,),
                )
                exists = cur.fetchone()
                if exists is None:
                    raise HTTPException(
                        status_code=404,
                        detail="Registration not found.",
                    )
                raise HTTPException(
                    status_code=409,
                    detail="This registration has already been checked in.",
                )
            conn.commit()
    return {
        "registration_id": row[0],
        "activity_id": row[1],
        "checked_in_at": row[2],
    }
