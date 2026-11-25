import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.core.registration_qr import (
    create_registration_qr_token,
    hash_registration_qr_token,
    registration_qr_expires_at,
    render_registration_qr,
)


class RegistrationQrTests(unittest.TestCase):
    def test_token_is_random_and_urlsafe(self):
        token = create_registration_qr_token()
        self.assertEqual(len(token), 43)
        self.assertRegex(token, r"^[A-Za-z0-9_-]{43}$")
        self.assertNotEqual(token, create_registration_qr_token())

    def test_token_hash_does_not_contain_token(self):
        token = create_registration_qr_token()
        digest = hash_registration_qr_token(token)
        self.assertEqual(len(digest), 64)
        self.assertNotIn(token, digest)
        self.assertEqual(digest, hash_registration_qr_token(token))

    def test_svg_qr_contains_a_vector_image(self):
        image = render_registration_qr("opaque-registration-token")
        self.assertIn(b"<svg", image)
        self.assertIn(b"</svg>", image)

    def test_expiry_uses_configured_ttl(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        with patch.dict("os.environ", {"REGISTRATION_QR_TTL_SECONDS": "120"}, clear=False):
            expires_at = registration_qr_expires_at(now)
        self.assertEqual(expires_at, now + timedelta(seconds=120))

    def test_invalid_ttl_is_rejected(self):
        with patch.dict("os.environ", {"REGISTRATION_QR_TTL_SECONDS": "5"}, clear=False):
            with self.assertRaises(RuntimeError):
                registration_qr_expires_at()


if __name__ == "__main__":
    unittest.main()
