import unittest
from unittest.mock import patch

from app.core.registration_qr import (
    create_registration_qr_token,
    hash_registration_qr_token,
    render_registration_qr,
)


class RegistrationQrTests(unittest.TestCase):
    def test_token_is_stable_per_registration_and_user(self):
        with patch.dict("os.environ", {"SECRET_KEY": "a" * 48}, clear=False):
            token = create_registration_qr_token(12, 34)
            self.assertEqual(token, create_registration_qr_token(12, 34))
            self.assertNotEqual(token, create_registration_qr_token(13, 34))
            self.assertNotEqual(token, create_registration_qr_token(12, 35))

    def test_token_hash_does_not_contain_token(self):
        with patch.dict("os.environ", {"SECRET_KEY": "b" * 48}, clear=False):
            token = create_registration_qr_token(1, 2)
        digest = hash_registration_qr_token(token)
        self.assertEqual(len(digest), 64)
        self.assertNotIn(token, digest)

    def test_svg_qr_contains_a_vector_image(self):
        image = render_registration_qr("opaque-registration-token")
        self.assertIn(b"<svg", image)
        self.assertIn(b"</svg>", image)


if __name__ == "__main__":
    unittest.main()