import os

import psycopg


def get_db_connection() -> psycopg.Connection:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set.")
    return psycopg.connect(database_url)


def initialize_tables(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
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
                starts_at TIMESTAMPTZ NOT NULL,
                ends_at TIMESTAMPTZ,
                registration_opens_at TIMESTAMPTZ,
                registration_deadline TIMESTAMPTZ NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'approved', 'rejected', 'published', 'archived')),
                review_note TEXT,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                published_at TIMESTAMPTZ
            )
            """
        )
        cur.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = 'activities'::regclass
                      AND conname = 'activities_status_check'
                      AND position('archived' in pg_get_constraintdef(oid)) > 0
                ) THEN
                    ALTER TABLE activities
                        DROP CONSTRAINT IF EXISTS activities_status_check;
                    ALTER TABLE activities
                        ADD CONSTRAINT activities_status_check
                        CHECK (status IN (
                            'draft', 'approved', 'rejected', 'published', 'archived'
                        ));
                END IF;
            END
            $$
            """
        )
        cur.execute(
            """
            ALTER TABLE activities
                ADD COLUMN IF NOT EXISTS organizer VARCHAR(255) NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS category VARCHAR(30) NOT NULL DEFAULT 'other',
                ADD COLUMN IF NOT EXISTS capacity INTEGER NOT NULL DEFAULT 0,
                ADD COLUMN IF NOT EXISTS duration VARCHAR(100) NOT NULL DEFAULT '',
                ADD COLUMN IF NOT EXISTS ends_at TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS registration_opens_at TIMESTAMPTZ
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
            "ALTER TABLE registrations ADD COLUMN IF NOT EXISTS qr_token_hash CHAR(64)"
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS registrations_qr_token_hash_uq "
            "ON registrations (qr_token_hash) WHERE qr_token_hash IS NOT NULL"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_staff (
                activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                assigned_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                PRIMARY KEY (activity_id, user_id)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS activity_staff_user_idx "
            "ON activity_staff (user_id, activity_id)"
        )
    conn.commit()
