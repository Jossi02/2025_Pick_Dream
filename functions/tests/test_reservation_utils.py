import sys
import unittest
from datetime import datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reservation_utils import (  # noqa: E402
    KST,
    coerce_capacity,
    extract_room_id,
    format_korean_time,
    intervals_overlap,
    parse_korean_time,
    reservation_room_id,
)


class ReservationUtilsTest(unittest.TestCase):
    def test_extract_room_id_supports_building_names(self):
        self.assertEqual("7202", extract_room_id("집현관 202호"))
        self.assertEqual("5101", extract_room_id("5강의동 101호"))

    def test_extract_room_id_rejects_embedded_long_numbers(self):
        self.assertIsNone(extract_room_id("학번 20201234"))

    def test_reservation_room_id_prefers_explicit_schema_field(self):
        self.assertEqual("4103", reservation_room_id("hash", {"roomID": 4103, "name": "예지관 101호"}))
        self.assertEqual("4101", reservation_room_id("hash", {"name": "예지관 101호"}))

    def test_capacity_is_normalized(self):
        self.assertEqual(12, coerce_capacity("12명"))
        self.assertEqual(0, coerce_capacity(None))

    def test_korean_time_round_trip(self):
        value = datetime(2026, 6, 27, 14, 5, 0, tzinfo=KST)
        self.assertEqual(value, parse_korean_time(format_korean_time(value)))

    def test_interval_boundaries_do_not_overlap(self):
        first_start = datetime(2026, 6, 27, 10, tzinfo=KST)
        first_end = datetime(2026, 6, 27, 11, tzinfo=KST)
        second_end = datetime(2026, 6, 27, 12, tzinfo=KST)
        self.assertFalse(intervals_overlap(first_start, first_end, first_end, second_end))
        self.assertTrue(intervals_overlap(first_start, second_end, first_end, second_end))


if __name__ == "__main__":
    unittest.main()
