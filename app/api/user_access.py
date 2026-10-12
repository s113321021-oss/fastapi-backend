from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from psycopg.types.json import Jsonb

from app.core.db import get_db_connection
from app.core.password_auth import (
    AuthenticatedIdentity,
    get_authenticated_identity,
    hash_password,
    is_student_email,
    normalize_email,
)
from app.services.activity_importer import (
    ACTIVITY_SOURCES,
    SOURCE_BY_ID,
    fetch_source,
)

router = APIRouter(prefix="/api")


class Role(StrEnum):
    ADMIN = "admin"
    STUDENT = "student"
    CHECK_IN = "checkin"


class ActivityStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class ActivityImportStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    DRAFT_CREATED = "draft_created"
    IGNORED = "ignored"


class ActivityImportSyncRequest(BaseModel):
    source_id: str | None = Field(default=None, min_length=1, max_length=30)


class ActivityCategory(StrEnum):
    TALK = "talk"
    WORKSHOP = "workshop"
    CLUB = "club"
    CULTURE = "culture"
    SPORTS = "sports"
    CAREER = "career"
    OTHER = "other"


class User(BaseModel):
    id: int
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str
    role: Role


class UserProvision(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    display_name: str = Field(min_length=1, max_length=255)
    role: Role
    password: str | None = Field(default=None, min_length=12, max_length=128)


class ActivityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10000)
    location: str = Field(min_length=1, max_length=255)
    organizer: str = Field(min_length=1, max_length=255)
    category: ActivityCategory = ActivityCategory.OTHER
    capacity: int = Field(ge=1, le=100000)
    duration: str = Field(default="", max_length=100)
    source_url: str | None = Field(default=None, max_length=2000)
    starts_at: datetime
    registration_deadline: datetime

    @field_validator("starts_at", "registration_deadline")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime values must include a timezone.")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.hostname not in {
            "ccweb.ncnu.edu.tw",
            "ltrc.ncnu.edu.tw",
            "ctld.ncnu.edu.tw",
        }:
            raise ValueError("Source URL must use one of the configured NCNU sources.")
        return value


class ActivityUpdate(ActivityCreate):
    pass


class ActivityReview(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=2000)


class MailExtractionSettings(BaseModel):
    enabled: bool = False
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    mailbox: str = Field(default="INBOX", min_length=1, max_length=255)


def initialize_access_tables(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                external_subject VARCHAR(255) UNIQUE,
                email VARCHAR(320) NOT NULL,
                display_name VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL
                    CHECK (role IN ('admin', 'student', 'checkin')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)"
        )
        cur.execute("ALTER TABLE users ALTER COLUMN external_subject DROP NOT NULL")
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS users_email_normalized_uq ON users (lower(email))"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                token_hash CHAR(64) PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMPTZ NOT NULL,
                revoked_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS user_sessions_user_idx ON user_sessions (user_id, expires_at)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_login_attempts (
                id BIGSERIAL PRIMARY KEY,
                email_hash CHAR(64) NOT NULL,
                ip_hash CHAR(64) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS auth_login_attempts_email_idx "
            "ON auth_login_attempts (email_hash, created_at DESC)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS auth_login_attempts_ip_idx "
            "ON auth_login_attempts (ip_hash, created_at DESC)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS activities (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                location VARCHAR(255) NOT NULL,
                organizer VARCHAR(255) NOT NULL DEFAULT '',
                category VARCHAR(30) NOT NULL DEFAULT 'other',
                capacity INTEGER NOT NULL DEFAULT 0 CHECK (capacity >= 0),
                duration VARCHAR(100) NOT NULL DEFAULT '',
                source_url TEXT,
                starts_at TIMESTAMPTZ NOT NULL,
                registration_deadline TIMESTAMPTZ NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'approved', 'rejected', 'published')),
                review_note TEXT,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                published_at TIMESTAMPTZ
            )
            """
        )
        cur.execute(
            """
            ALTER TABLE activities
                ADD COLUMN IF NOT EXISTS organizer VARCHAR(255) NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS category VARCHAR(30) NOT NULL DEFAULT 'other',
                ADD COLUMN IF NOT EXISTS capacity INTEGER NOT NULL DEFAULT 0,
                ADD COLUMN IF NOT EXISTS duration VARCHAR(100) NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS source_url TEXT
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS activities_status_starts_at_idx
            ON activities (status, starts_at)
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS registrations (
                id SERIAL PRIMARY KEY,
                activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                checked_in_at TIMESTAMPTZ,
                checked_in_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                UNIQUE (activity_id, user_id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_imports (
                id SERIAL PRIMARY KEY,
                source_id VARCHAR(30) NOT NULL,
                source_name VARCHAR(255) NOT NULL,
                source_url TEXT NOT NULL UNIQUE,
                title VARCHAR(255) NOT NULL,
                published_at TIMESTAMPTZ,
                parsed_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                status VARCHAR(30) NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review', 'draft_created', 'ignored')),
                error_message TEXT,
                activity_id INTEGER REFERENCES activities(id) ON DELETE SET NULL,
                first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS activity_imports_status_seen_idx "
            "ON activity_imports (status, first_seen_at DESC)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_import_runs (
                id SERIAL PRIMARY KEY,
                source_id VARCHAR(30) NOT NULL,
                source_name VARCHAR(255) NOT NULL,
                source_url TEXT NOT NULL,
                status VARCHAR(20) NOT NULL CHECK (status IN ('completed', 'failed')),
                items_found INTEGER NOT NULL DEFAULT 0,
                items_new INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS activity_import_runs_source_started_idx "
            "ON activity_import_runs (source_id, started_at DESC)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mail_extraction_settings (
                id SMALLINT PRIMARY KEY CHECK (id = 1),
                enabled BOOLEAN NOT NULL DEFAULT FALSE,
                host VARCHAR(255),
                port INTEGER CHECK (port IS NULL OR port BETWEEN 1 AND 65535),
                username VARCHAR(255),
                mailbox VARCHAR(255) NOT NULL DEFAULT 'INBOX',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    conn.commit()


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
    return require_role(user, Role.CHECK_IN)


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
        "source_url": row[14],
        "registered_count": row[15],
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
    capacity, duration, source_url,
    (SELECT COUNT(*) FROM registrations WHERE activity_id = activities.id)
"""

@router.get("/auth/me", response_model=User)
def read_current_user(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/activity-sources")
def list_activity_sources() -> list[dict]:
    return [
        {"id": source.id, "name": source.name, "url": source.url}
        for source in ACTIVITY_SOURCES
    ]


@router.post("/admin/activity-imports/sync")
def sync_activity_sources(
    request_data: ActivityImportSyncRequest,
    admin: User = Depends(require_admin),
) -> dict:
    del admin
    if request_data.source_id and request_data.source_id not in SOURCE_BY_ID:
        raise HTTPException(status_code=422, detail="Unknown activity source.")

    sources = (
        [SOURCE_BY_ID[request_data.source_id]]
        if request_data.source_id
        else list(ACTIVITY_SOURCES)
    )
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source_url FROM activity_imports")
            known_urls = {row[0] for row in cur.fetchall()}

    run_summaries = []
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for source in sources:
                result = fetch_source(source.id, known_urls)
                new_count = 0
                for candidate in result.candidates:
                    if candidate.source_url in known_urls:
                        cur.execute(
                            """
                            UPDATE activity_imports
                            SET fetched_at = CURRENT_TIMESTAMP,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE source_url = %s AND status = 'pending_review'
                            """,
                            (candidate.source_url,),
                        )
                        continue
                    cur.execute(
                        """
                        INSERT INTO activity_imports (
                            source_id, source_name, source_url, title,
                            parsed_data, error_message
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (source_url) DO NOTHING
                        RETURNING id
                        """,
                        (
                            candidate.source_id,
                            candidate.source_name,
                            candidate.source_url,
                            candidate.title or "未命名公告",
                            Jsonb(candidate.parsed_data),
                            candidate.error_message,
                        ),
                    )
                    if cur.fetchone():
                        new_count += 1

                cur.execute(
                    """
                    INSERT INTO activity_import_runs (
                        source_id, source_name, source_url, status,
                        items_found, items_new, error_message
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, started_at, finished_at
                    """,
                    (
                        source.id,
                        source.name,
                        source.url,
                        result.status,
                        result.items_found,
                        new_count,
                        result.error_message,
                    ),
                )
                run_row = cur.fetchone()
                run_summaries.append(
                    {
                        "run_id": run_row[0],
                        "source_id": source.id,
                        "source_name": source.name,
                        "status": result.status,
                        "items_found": result.items_found,
                        "items_new": new_count,
                        "error_message": result.error_message,
                        "started_at": run_row[1],
                        "finished_at": run_row[2],
                    }
                )
        conn.commit()
    return {"sources": run_summaries}


@router.get("/admin/activity-imports")
def list_activity_imports(
    status: ActivityImportStatus | None = None,
    admin: User = Depends(require_admin),
) -> list[dict]:
    del admin
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if status:
                cur.execute(
                    """
                    SELECT id, source_id, source_name, source_url, title,
                           published_at, parsed_data, status, error_message,
                           activity_id, first_seen_at, fetched_at
                    FROM activity_imports
                    WHERE status = %s
                    ORDER BY first_seen_at DESC
                    LIMIT 300
                    """,
                    (status.value,),
                )
            else:
                cur.execute(
                    """
                    SELECT id, source_id, source_name, source_url, title,
                           published_at, parsed_data, status, error_message,
                           activity_id, first_seen_at, fetched_at
                    FROM activity_imports
                    ORDER BY first_seen_at DESC
                    LIMIT 300
                    """
                )
            rows = cur.fetchall()
    return [
        {
            "id": row[0],
            "source_id": row[1],
            "source_name": row[2],
            "source_url": row[3],
            "title": row[4],
            "published_at": row[5],
            "parsed_data": row[6],
            "status": row[7],
            "error_message": row[8],
            "activity_id": row[9],
            "first_seen_at": row[10],
            "fetched_at": row[11],
        }
        for row in rows
    ]


@router.get("/admin/activity-import-runs")
def list_activity_import_runs(admin: User = Depends(require_admin)) -> list[dict]:
    del admin
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, source_id, source_name, source_url, status,
                       items_found, items_new, error_message, started_at, finished_at
                FROM activity_import_runs
                ORDER BY started_at DESC
                LIMIT 30
                """
            )
            rows = cur.fetchall()
    return [
        {
            "id": row[0],
            "source_id": row[1],
            "source_name": row[2],
            "source_url": row[3],
            "status": row[4],
            "items_found": row[5],
            "items_new": row[6],
            "error_message": row[7],
            "started_at": row[8],
            "finished_at": row[9],
        }
        for row in rows
    ]


@router.post("/admin/activity-imports/{import_id}/create-draft", status_code=201)
def create_activity_draft_from_import(
    import_id: int,
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
                "SELECT source_url, status FROM activity_imports WHERE id = %s FOR UPDATE",
                (import_id,),
            )
            import_row = cur.fetchone()
            if import_row is None:
                raise HTTPException(status_code=404, detail="Imported announcement not found.")
            if import_row[1] != ActivityImportStatus.PENDING_REVIEW.value:
                raise HTTPException(status_code=409, detail="This import is no longer pending review.")

            cur.execute(
                """
                INSERT INTO activities (
                    title, description, location, organizer, category,
                    capacity, duration, source_url, starts_at,
                    registration_deadline, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    import_row[0],
                    activity.starts_at,
                    activity.registration_deadline,
                    admin.id,
                ),
            )
            activity_id = cur.fetchone()[0]
            cur.execute(
                """
                UPDATE activity_imports
                SET status = 'draft_created', activity_id = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (activity_id, import_id),
            )
            cur.execute(
                f"SELECT {ACTIVITY_COLUMNS} FROM activities WHERE id = %s",
                (activity_id,),
            )
            row = cur.fetchone()
        conn.commit()
    return activity_response(row)


@router.post("/admin/activity-imports/{import_id}/ignore", status_code=204)
def ignore_activity_import(
    import_id: int,
    admin: User = Depends(require_admin),
) -> None:
    del admin
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE activity_imports
                SET status = 'ignored', updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND status = 'pending_review'
                RETURNING id
                """,
                (import_id,),
            )
            if cur.fetchone() is None:
                cur.execute("SELECT id FROM activity_imports WHERE id = %s", (import_id,))
                if cur.fetchone() is None:
                    raise HTTPException(status_code=404, detail="Imported announcement not found.")
                raise HTTPException(status_code=409, detail="This import is no longer pending review.")
        conn.commit()


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
                SELECT registration_deadline, capacity
                FROM activities
                WHERE id = %s AND status = 'published'
                FOR UPDATE
                """,
                (activity_id,),
            )
            activity = cur.fetchone()
            if activity is None:
                raise HTTPException(status_code=404, detail="Activity not found.")
            if activity[0] < datetime.now(activity[0].tzinfo):
                raise HTTPException(
                    status_code=409,
                    detail="Registration deadline has passed.",
                )
            cur.execute(
                "SELECT COUNT(*) FROM registrations WHERE activity_id = %s",
                (activity_id,),
            )
            registration_count = cur.fetchone()[0]
            if activity[1] and registration_count >= activity[1]:
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
                    capacity, duration, source_url, starts_at,
                    registration_deadline, created_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    activity.source_url,
                    activity.starts_at,
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
                    duration = %s, source_url = %s, starts_at = %s,
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
                    activity.source_url,
                    activity.starts_at,
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
                SELECT a.id, a.title, a.status,
                       COUNT(r.id) AS registration_count,
                       COUNT(r.checked_in_at) AS check_in_count
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
            "registration_count": row[3],
            "check_in_count": row[4],
        }
        for row in rows
    ]


@router.get("/admin/settings/mail-extraction")
def read_mail_extraction_settings(
    admin: User = Depends(require_admin),
) -> dict:
    del admin
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT enabled, host, port, username, mailbox, updated_at
                FROM mail_extraction_settings
                WHERE id = 1
                """
            )
            row = cur.fetchone()
    if row is None:
        return MailExtractionSettings().model_dump()
    return {
        "enabled": row[0],
        "host": row[1],
        "port": row[2],
        "username": row[3],
        "mailbox": row[4],
        "updated_at": row[5],
    }


@router.put("/admin/settings/mail-extraction")
def update_mail_extraction_settings(
    settings: MailExtractionSettings,
    admin: User = Depends(require_admin),
) -> dict:
    del admin
    if settings.enabled and (not settings.host or not settings.username or not settings.port):
        raise HTTPException(
            status_code=422,
            detail="Host, port, and username are required when extraction is enabled.",
        )
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mail_extraction_settings
                    (id, enabled, host, port, username, mailbox, updated_at)
                VALUES (1, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    host = EXCLUDED.host,
                    port = EXCLUDED.port,
                    username = EXCLUDED.username,
                    mailbox = EXCLUDED.mailbox,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING enabled, host, port, username, mailbox, updated_at
                """,
                (
                    settings.enabled,
                    settings.host,
                    settings.port,
                    settings.username,
                    settings.mailbox,
                ),
            )
            row = cur.fetchone()
            conn.commit()
    return {
        "enabled": row[0],
        "host": row[1],
        "port": row[2],
        "username": row[3],
        "mailbox": row[4],
        "updated_at": row[5],
    }


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
                  AND (%s IS NULL OR u.display_name ILIKE %s OR u.email ILIKE %s)
                ORDER BY u.display_name
                """,
                (
                    activity_id,
                    search,
                    f"%{search}%" if search is not None else None,
                    f"%{search}%" if search is not None else None,
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
