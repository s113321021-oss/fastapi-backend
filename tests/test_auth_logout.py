import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.auth import router


class LogoutRouteTests(unittest.TestCase):
    def test_logout_returns_no_content_and_expires_session_cookie(self):
        app = FastAPI()
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post("/api/auth/logout")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertIn("campus_session=", response.headers["set-cookie"])
        self.assertIn("max-age=0", response.headers["set-cookie"].lower())


if __name__ == "__main__":
    unittest.main()
