import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from app.core.password_auth import hash_password


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "Set TEST_DATABASE_URL to a disposable PostgreSQL database to run API integration tests.",
)
class ApiDatabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = TEST_DATABASE_URL
        cls.schema = f"api_test_{uuid.uuid4().hex}"
        cls.environment = patch.dict(
            os.environ,
            {
                "DATABASE_URL": cls.database_url,
                "ROOT_PATH": "",
                "SECRET_KEY": "integration-test-secret-key-that-is-at-least-32-bytes",
                "SESSION_COOKIE_SECURE": "false",
            },
        )
        cls.environment.start()

        cls._original_testclient_request = TestClient.request

        def _csrf_request(self, method, url, **kwargs):
            if method.upper() in {"POST", "PUT", "DELETE", "PATCH"}:
                headers = dict(kwargs.get("headers") or {})
                if "x-csrf-token" not in {k.lower() for k in headers}:
                    if not self.cookies.get("csrf_token"):
                        cls._original_testclient_request(self, "GET", "/api/health")
                    headers["X-CSRF-Token"] = self.cookies.get("csrf_token", "")
                kwargs["headers"] = headers
            return cls._original_testclient_request(self, method, url, **kwargs)

        TestClient.request = _csrf_request

        with psycopg.connect(cls.database_url) as conn:
            conn.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema))
            )
            conn.commit()

        from app.main import app
        import app.core.db as core_db
        import app.main as main
        import app.routers.auth as auth_router
        import app.routers.user_access as access_router

        cls.app = app

        def connect_to_test_schema():
            conn = psycopg.connect(cls.database_url)
            conn.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(cls.schema))
            )
            conn.commit()
            return conn

        cls.connection_factory = connect_to_test_schema
        cls.patches = [
            patch.object(core_db, "get_db_connection", connect_to_test_schema),
            patch.object(main, "get_db_connection", connect_to_test_schema),
            patch.object(auth_router, "get_db_connection", connect_to_test_schema),
            patch.object(access_router, "get_db_connection", connect_to_test_schema),
        ]
        for active_patch in cls.patches:
            active_patch.start()

    @classmethod
    def tearDownClass(cls):
        for active_patch in reversed(cls.patches):
            active_patch.stop()
        try:
            with psycopg.connect(cls.database_url) as conn:
                conn.execute(
                    sql.SQL("DROP SCHEMA {} CASCADE").format(
                        sql.Identifier(cls.schema)
                    )
                )
                conn.commit()
        finally:
            if hasattr(cls, "_original_testclient_request"):
                TestClient.request = cls._original_testclient_request
            cls.environment.stop()

    def setUp(self):
        self.client = TestClient(self.app)
        self.client.__enter__()
        with self.connection_factory() as conn:
            conn.execute(
                """
                TRUNCATE registrations, activities, auth_login_attempts,
                         user_sessions, users, notes
                RESTART IDENTITY CASCADE
                """
            )
            conn.execute(
                """
                INSERT INTO users (email, display_name, role, password_hash)
                VALUES (%s, %s, %s, %s), (%s, %s, %s, %s)
                """,
                (
                    "admin@example.edu",
                    "Test Admin",
                    "admin",
                    hash_password("AdminIntegrationPass123!"),
                    "checkin@example.edu",
                    "Test Check-in",
                    "checkin",
                    hash_password("CheckinIntegrationPass123!"),
                ),
            )
            conn.commit()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    @staticmethod
    def login(client, email, password):
        return client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )

    def login_as_admin(self):
        response = self.login(
            self.client,
            "admin@example.edu",
            "AdminIntegrationPass123!",
        )
        self.assertEqual(response.status_code, 200, response.text)

    def make_student(self, email="s123456789@ncnu.edu.tw"):
        response = self.client.post(
            "/api/auth/register",
            json={
                "email": email,
                "display_name": "Test Student",
                "password": "StudentIntegrationPass123!",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def create_published_activity(self, client, capacity=10):
        now = datetime.now(timezone.utc)
        payload = {
            "title": "Integration Test Activity",
            "description": "Activity used by PostgreSQL API integration tests.",
            "location": "Test Hall",
            "organizer": "Integration Tests",
            "category": "talk",
            "capacity": capacity,
            "duration": "60 minutes",
            "starts_at": (now + timedelta(days=2)).isoformat(),
            "registration_deadline": (now + timedelta(days=1)).isoformat(),
        }
        created = client.post("/api/admin/activities", json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        activity_id = created.json()["id"]
        reviewed = client.post(
            f"/api/admin/activities/{activity_id}/review",
            json={"approved": True},
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        published = client.post(f"/api/admin/activities/{activity_id}/publish")
        self.assertEqual(published.status_code, 200, published.text)
        return activity_id, payload

    def test_registration_login_logout_and_revoked_session(self):
        response = self.client.post(
            "/api/auth/register",
            json={
                "email": "s123456789@ncnu.edu.tw",
                "display_name": "Integration Student",
                "password": "StudentIntegrationPass123!",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["role"], "student")
        self.assertIn("httponly", response.headers["set-cookie"].lower())
        self.assertEqual(
            self.client.get("/api/auth/me").json()["email"],
            "s123456789@ncnu.edu.tw",
        )

        invalid_registration = self.client.post(
            "/api/auth/register",
            json={
                "email": "not-a-student@example.edu",
                "display_name": "Invalid Student",
                "password": "StudentIntegrationPass123!",
            },
        )
        self.assertEqual(invalid_registration.status_code, 422)

        logout = self.client.post("/api/auth/logout")
        self.assertEqual(logout.status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

        with self.connection_factory() as conn:
            revoked_at = conn.execute(
                "SELECT revoked_at FROM user_sessions"
            ).fetchone()[0]
        self.assertIsNotNone(revoked_at)

        login = self.login(
            self.client,
            "S123456789@NCNU.EDU.TW",
            "StudentIntegrationPass123!",
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

    def test_role_permissions_and_activity_review_publish_flow(self):
        self.assertEqual(self.client.get("/api/admin/activities").status_code, 401)
        student = self.make_student()
        student_client = TestClient(self.app)
        self.assertEqual(
            self.login(
                student_client,
                student["email"],
                "StudentIntegrationPass123!",
            ).status_code,
            200,
        )
        self.assertEqual(
            student_client.get("/api/admin/activities/statistics").status_code,
            403,
        )
        self.assertEqual(student_client.get("/api/admin/activities").status_code, 403)

        self.login_as_admin()
        now = datetime.now(timezone.utc)
        payload = {
            "title": "Review Workflow Activity",
            "description": "Draft, rejection, correction, approval, and publication.",
            "location": "Test Hall",
            "organizer": "Integration Tests",
            "category": "workshop",
            "capacity": 5,
            "starts_at": (now + timedelta(days=2)).isoformat(),
            "registration_deadline": (now + timedelta(days=1)).isoformat(),
        }
        created = self.client.post("/api/admin/activities", json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        activity_id = created.json()["id"]
        self.assertEqual(created.json()["status"], "draft")
        self.assertEqual(self.client.get("/api/activities").json(), [])
        self.assertEqual(
            self.client.get(f"/api/activities/{activity_id}").status_code,
            404,
        )
        self.assertEqual(
            student_client.post(
                f"/api/activities/{activity_id}/registrations"
            ).status_code,
            404,
        )

        missing_rejection_note = self.client.post(
            f"/api/admin/activities/{activity_id}/review",
            json={"approved": False},
        )
        self.assertEqual(missing_rejection_note.status_code, 422)
        rejected = self.client.post(
            f"/api/admin/activities/{activity_id}/review",
            json={"approved": False, "note": "Please revise the event details."},
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["status"], "rejected")
        self.assertEqual(
            self.client.post(
                f"/api/admin/activities/{activity_id}/publish"
            ).status_code,
            409,
        )

        payload["title"] = "Corrected Review Workflow Activity"
        updated = self.client.put(
            f"/api/admin/activities/{activity_id}",
            json=payload,
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["status"], "draft")
        self.assertIsNone(updated.json()["review_note"])

        approved = self.client.post(
            f"/api/admin/activities/{activity_id}/review",
            json={"approved": True},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "approved")
        published = self.client.post(
            f"/api/admin/activities/{activity_id}/publish"
        )
        self.assertEqual(published.status_code, 200, published.text)
        self.assertEqual(published.json()["status"], "published")
        self.assertEqual(
            self.client.get(f"/api/activities/{activity_id}").status_code,
            200,
        )
        self.assertEqual(
            student_client.get(
                "/api/check-in/registrations",
                params={"activity_id": activity_id},
            ).status_code,
            403,
        )

    def test_registration_capacity_qr_checkin_and_statistics(self):
        self.login_as_admin()
        activity_id, _ = self.create_published_activity(self.client, capacity=1)
        admin_client = TestClient(self.app)
        self.assertEqual(
            self.login(
                admin_client,
                "admin@example.edu",
                "AdminIntegrationPass123!",
            ).status_code,
            200,
        )

        student = self.make_student()
        self.assertEqual(
            self.client.post(
                f"/api/activities/{activity_id}/registrations"
            ).status_code,
            201,
        )
        duplicate = self.client.post(
            f"/api/activities/{activity_id}/registrations"
        )
        self.assertEqual(duplicate.status_code, 409)

        registration = self.client.get("/api/registrations/me").json()[0]
        self.assertEqual(registration["activity_id"], activity_id)
        qr_response = self.client.get(
            f"/api/registrations/me/{registration['id']}/qr"
        )
        self.assertEqual(qr_response.status_code, 200, qr_response.text)
        self.assertEqual(qr_response.headers["content-type"], "image/svg+xml")
        qr_token = qr_response.headers["x-qr-token"]
        self.assertRegex(qr_token, r"^[A-Za-z0-9_-]{43}$")
        self.assertIn(b"<svg", qr_response.content)

        second_user = admin_client.post(
            "/api/admin/users",
            json={
                "email": "s987654321@ncnu.edu.tw",
                "display_name": "Second Student",
                "role": "student",
                "password": "SecondIntegrationPass123!",
            },
        )
        self.assertEqual(second_user.status_code, 201, second_user.text)
        second_client = TestClient(self.app)
        self.assertEqual(
            self.login(
                second_client,
                second_user.json()["email"],
                "SecondIntegrationPass123!",
            ).status_code,
            200,
        )
        full = second_client.post(
            f"/api/activities/{activity_id}/registrations"
        )
        self.assertEqual(full.status_code, 409)
        self.assertEqual(
            second_client.get(
                f"/api/registrations/me/{registration['id']}/qr"
            ).status_code,
            404,
        )

        checkin_client = TestClient(self.app)
        checkin_login = self.login(
            checkin_client,
            "checkin@example.edu",
            "CheckinIntegrationPass123!",
        )
        self.assertEqual(checkin_login.status_code, 200, checkin_login.text)
        checkin_user = checkin_client.get("/api/auth/me").json()
        assigned = admin_client.post(
            f"/api/admin/activities/{activity_id}/staff",
            json={"user_id": checkin_user["id"]},
        )
        self.assertEqual(assigned.status_code, 201, assigned.text)
        self.assertEqual(
            checkin_client.get(
                "/api/admin/activities/statistics"
            ).status_code,
            403,
        )
        self.assertEqual(
            checkin_client.get(
                "/api/check-in/registrations",
                params={"activity_id": activity_id, "search": student["display_name"]},
            ).status_code,
            200,
        )

        lookup = checkin_client.post(
            "/api/check-in/qr/lookup",
            json={"token": qr_token, "activity_id": activity_id},
        )
        self.assertEqual(lookup.status_code, 200, lookup.text)
        self.assertEqual(lookup.json()["registration_id"], registration["id"])
        self.assertEqual(
            admin_client.post(
                "/api/check-in/qr/lookup",
                json={"token": qr_token, "activity_id": activity_id},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                "/api/check-in/qr/lookup",
                json={"token": qr_token, "activity_id": activity_id},
            ).status_code,
            403,
        )

        checked_in = checkin_client.post(
            f"/api/check-in/registrations/{registration['id']}/confirm"
        )
        self.assertEqual(checked_in.status_code, 200, checked_in.text)
        self.assertIsNotNone(checked_in.json()["checked_in_at"])
        self.assertEqual(
            checkin_client.post(
                f"/api/check-in/registrations/{registration['id']}/confirm"
            ).status_code,
            409,
        )
        my_registrations = self.client.get("/api/registrations/me").json()
        self.assertIsNotNone(my_registrations[0]["checked_in_at"])

        statistics = admin_client.get(
            "/api/admin/activities/statistics"
        )
        self.assertEqual(statistics.status_code, 200, statistics.text)
        activity_statistics = next(
            item for item in statistics.json() if item["activity_id"] == activity_id
        )
        self.assertEqual(activity_statistics["registration_count"], 1)
        self.assertEqual(activity_statistics["check_in_count"], 1)
        self.assertEqual(activity_statistics["not_checked_in_count"], 0)
        self.assertEqual(activity_statistics["check_in_rate"], 100.0)

    def test_archiving_activity_hides_it_and_preserves_registration_and_checkin(self):
        self.login_as_admin()
        activity_id, _ = self.create_published_activity(self.client)
        admin_client = TestClient(self.app)
        self.assertEqual(
            self.login(
                admin_client,
                "admin@example.edu",
                "AdminIntegrationPass123!",
            ).status_code,
            200,
        )
        student = self.make_student()
        student_client = TestClient(self.app)
        self.assertEqual(
            self.login(
                student_client,
                student["email"],
                "StudentIntegrationPass123!",
            ).status_code,
            200,
        )
        self.assertEqual(
            student_client.post(
                f"/api/activities/{activity_id}/registrations"
            ).status_code,
            201,
        )
        registration = student_client.get("/api/registrations/me").json()[0]
        self.assertEqual(
            admin_client.post(
                f"/api/check-in/registrations/{registration['id']}/confirm"
            ).status_code,
            200,
        )

        archived = admin_client.post(
            f"/api/admin/activities/{activity_id}/archive"
        )

        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertEqual(archived.json()["status"], "archived")
        self.assertNotIn(
            activity_id,
            [activity["id"] for activity in admin_client.get("/api/activities").json()],
        )
        self.assertEqual(
            admin_client.get(f"/api/activities/{activity_id}").status_code,
            404,
        )
        self.assertEqual(
            student_client.post(
                f"/api/activities/{activity_id}/registrations"
            ).status_code,
            404,
        )
        retained = student_client.get("/api/registrations/me").json()[0]
        self.assertEqual(retained["id"], registration["id"])
        self.assertIsNotNone(retained["checked_in_at"])
        statistics = admin_client.get("/api/admin/activities/statistics").json()
        archived_statistics = next(
            item for item in statistics if item["activity_id"] == activity_id
        )
        self.assertEqual(archived_statistics["status"], "archived")
        self.assertEqual(archived_statistics["registration_count"], 1)
        self.assertEqual(archived_statistics["check_in_count"], 1)


if __name__ == "__main__":
    unittest.main()
