import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("GEMINI_API_KEY", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402


class AiIntentTest(unittest.TestCase):
    def test_cancel_reservation_patterns(self):
        self.assertTrue(main.is_cancel_reservation_request("\uc608\uc57d \ucde8\uc18c\ud574\uc918"))
        self.assertTrue(main.is_cancel_reservation_request("\uc608\uc57d\uc744 \ucde8\uc18c\ud558\uace0 \uc2f6\uc5b4"))
        self.assertTrue(main.is_cancel_reservation_request("7202 \uac15\uc758\uc2e4 \ucde8\uc18c\ud560\uac8c"))
        self.assertFalse(main.is_cancel_reservation_request("\uc608\uc57d\ud655\uc815"))

    def test_change_reservation_patterns(self):
        self.assertTrue(main.is_change_reservation_request("12\uc2dc\ub85c \ubcc0\uacbd\ud574\uc918"))
        self.assertTrue(main.is_change_reservation_request("5101 \uac15\uc758\uc2e4\ub85c \ubc14\uafd4\uc918"))
        self.assertTrue(main.is_change_reservation_request("\uc778\uc6d0 6\uba85\uc73c\ub85c \ubc14\uafd4\uc918"))
        self.assertFalse(main.is_change_reservation_request("\uc608\uc57d \ucde8\uc18c\ud574\uc918"))

    def test_explicit_change_reservation_patterns(self):
        self.assertTrue(main.is_explicit_change_reservation_request("\uae30\uc874 \uc608\uc57d\uc744 \ub2e4\ub978 \uac15\uc758\uc2e4\ub85c \ubcc0\uacbd\ud574\uc918"))
        self.assertTrue(main.is_explicit_change_reservation_request("5101 \uac15\uc758\uc2e4\ub85c \ubc14\uafd4\uc918"))
        self.assertFalse(main.is_explicit_change_reservation_request("\ub2e4\ub978 \uac15\uc758\uc2e4\ub85c \ud574\uc918"))

    def test_my_reservations_patterns(self):
        self.assertTrue(main.is_my_reservations_request("\ub0b4 \uc608\uc57d \ubcf4\uc5ec\uc918"))
        self.assertTrue(main.is_my_reservations_request("\uc608\uc57d \ub0b4\uc5ed \uc870\ud68c"))
        self.assertFalse(main.is_my_reservations_request("\uc608\uc57d\ud655\uc815"))

    def test_room_and_duration_parsing(self):
        self.assertEqual(["7202", "5101"], main.extract_room_ids("7202\ub97c 5101\ub85c \ubcc0\uacbd\ud574\uc918"))
        self.assertEqual(2, main.parse_duration_hours("2\uc2dc\uac04\uc73c\ub85c \ubcc0\uacbd\ud574\uc918"))
        self.assertEqual(6, main.parse_participant_count("6\uba85\uc73c\ub85c \ubc14\uafd4\uc918"))


if __name__ == "__main__":
    unittest.main()
