import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from app.models.main import ActivityCreate


class ActivityTimeRangeTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "title": "Test Activity",
            "description": "Activity description",
            "location": "Test Hall",
            "organizer": "Test Organizer",
            "capacity": 20,
            "starts_at": datetime(2026, 12, 1, 10, tzinfo=timezone.utc),
            "ends_at": datetime(2026, 12, 1, 11, tzinfo=timezone.utc),
            "registration_opens_at": datetime(2026, 11, 1, 10, tzinfo=timezone.utc),
            "registration_deadline": datetime(2026, 11, 30, 10, tzinfo=timezone.utc),
        }

    def test_accepts_valid_time_ranges(self):
        activity = ActivityCreate(**self.payload)

        self.assertEqual(activity.ends_at, self.payload["ends_at"])
        self.assertEqual(
            activity.registration_opens_at,
            self.payload["registration_opens_at"],
        )

    def test_rejects_activity_end_before_start(self):
        self.payload["ends_at"] = self.payload["starts_at"]

        with self.assertRaises(ValidationError):
            ActivityCreate(**self.payload)

    def test_rejects_registration_open_after_deadline(self):
        self.payload["registration_opens_at"] = datetime(
            2026, 12, 1, 10, tzinfo=timezone.utc
        )

        with self.assertRaises(ValidationError):
            ActivityCreate(**self.payload)

    def test_legacy_payload_without_range_endpoints_remains_supported(self):
        self.payload.pop("ends_at")
        self.payload.pop("registration_opens_at")

        activity = ActivityCreate(**self.payload)

        self.assertIsNone(activity.ends_at)
        self.assertIsNone(activity.registration_opens_at)


if __name__ == "__main__":
    unittest.main()
