import shutil
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import BASE_DIR, app


class StaticPathBypassTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.sibling_dir = BASE_DIR / "static_evil_test"
        self.sibling_dir.mkdir(exist_ok=True)
        self.secret_file = self.sibling_dir / "secret.txt"
        self.secret_file.write_text("top-secret", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.sibling_dir, ignore_errors=True)

    def test_static_prefix_sibling_path_is_rejected(self):
        response = self.client.get("/static/%2e%2e/static_evil_test/secret.txt")
        self.assertEqual(response.status_code, 403)

    def test_valid_static_file_still_served(self):
        response = self.client.get("/static/index.html")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("content-type", ""))


class NotesAuthTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.get("/api/health")
        csrf = self.client.cookies.get("csrf_token", "")
        self.csrf_headers = {"X-CSRF-Token": csrf}

    def test_list_notes_requires_authentication(self):
        response = self.client.get("/api/notes")
        self.assertEqual(response.status_code, 401)

    def test_get_note_requires_authentication(self):
        response = self.client.get("/api/note/1")
        self.assertEqual(response.status_code, 401)

    def test_create_note_requires_authentication(self):
        response = self.client.post("/api/note", json={"title": "t", "content": "c"}, headers=self.csrf_headers)
        self.assertEqual(response.status_code, 401)

    def test_update_note_requires_authentication(self):
        response = self.client.put("/api/note/1", json={"title": "t", "content": "c"}, headers=self.csrf_headers)
        self.assertEqual(response.status_code, 401)

    def test_delete_note_requires_authentication(self):
        response = self.client.delete("/api/note/1", headers=self.csrf_headers)
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
