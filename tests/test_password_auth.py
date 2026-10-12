import unittest
from unittest.mock import patch

from starlette.requests import Request

from app.core.password_auth import (
    create_session_token,
    get_auth_secret,
    hash_password,
    hash_token,
    is_student_email,
    normalize_email,
    session_cookie_options,
    verify_password,
)


class PasswordAuthTests(unittest.TestCase):
    def test_student_email_is_limited_to_ncnu_student_pattern(self):
        self.assertTrue(is_student_email("S113321021@NCNU.EDU.TW"))
        self.assertFalse(is_student_email("student@ncnu.edu.tw"))
        self.assertFalse(is_student_email("s123@example.edu.tw"))

    def test_email_normalization_trims_and_lowercases(self):
        self.assertEqual(normalize_email(" S123@NCNU.EDU.TW "), "s123@ncnu.edu.tw")

    def test_passwords_use_argon2id_and_reject_wrong_password(self):
        encoded = hash_password("StrongTestPass123!")
        self.assertTrue(encoded.startswith("$argon2id$"))
        self.assertTrue(verify_password(encoded, "StrongTestPass123!"))
        self.assertFalse(verify_password(encoded, "WrongPassword123!"))

    def test_unknown_account_uses_dummy_hash_and_fails(self):
        self.assertFalse(verify_password(None, "WrongPassword123!"))

    def test_session_tokens_are_random_and_stored_as_hashes(self):
        token, digest = create_session_token()
        self.assertNotEqual(token, digest)
        self.assertEqual(len(digest), 64)
        self.assertEqual(hash_token(token), digest)

    def test_example_secret_is_rejected(self):
        with patch.dict(
            "os.environ",
            {"SECRET_KEY": "change-me-to-a-strong-secret-key"},
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                get_auth_secret()

    def test_secure_cookie_is_enabled_for_https_or_forwarded_https(self):
        request = Request(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/",
                "raw_path": b"/",
                "query_string": b"",
                "headers": [(b"x-forwarded-proto", b"https")],
                "client": ("127.0.0.1", 1234),
                "server": ("localhost", 7777),
                "root_path": "",
            }
        )
        with patch.dict("os.environ", {"SESSION_COOKIE_SECURE": ""}, clear=False):
            options = session_cookie_options(request)
        self.assertTrue(options["secure"])
        self.assertTrue(options["httponly"])
        self.assertEqual(options["samesite"], "lax")


if __name__ == "__main__":
    unittest.main()