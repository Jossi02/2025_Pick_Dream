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
    parse_natural_korean_datetime,
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

    def test_parse_natural_korean_datetime_relative_day(self):
        now = datetime(2026, 6, 28, 1, 5, 0, tzinfo=KST)
        parsed = parse_natural_korean_datetime("\uBAA8\uB808 \uC624\uC804 11\uC2DC\uC5D0 \uC0AC\uC6A9\uD560 \uAC15\uC758\uC2E4", now)
        self.assertEqual(datetime(2026, 6, 30, 11, 0, 0, tzinfo=KST), parsed)

    def test_parse_natural_korean_datetime_explicit_date(self):
        now = datetime(2026, 6, 28, 1, 5, 0, tzinfo=KST)
        parsed = parse_natural_korean_datetime("6\uC6D4 30\uC77C \uC624\uD6C4 2\uC2DC 30\uBD84", now)
        self.assertEqual(datetime(2026, 6, 30, 14, 30, 0, tzinfo=KST), parsed)

    def test_parse_natural_korean_datetime_half_hour(self):
        now = datetime(2026, 6, 28, 1, 5, 0, tzinfo=KST)
        parsed = parse_natural_korean_datetime("\uB0B4\uC77C \uC624\uD6C4 2\uC2DC \uBC18", now)
        self.assertEqual(datetime(2026, 6, 29, 14, 30, 0, tzinfo=KST), parsed)

    def test_parse_natural_korean_datetime_rolls_forward_without_date(self):
        now = datetime(2026, 6, 28, 14, 5, 0, tzinfo=KST)
        parsed = parse_natural_korean_datetime("\uC624\uD6C4 2\uC2DC", now)
        self.assertEqual(datetime(2026, 6, 29, 14, 0, 0, tzinfo=KST), parsed)

    def test_parse_natural_korean_datetime_uses_default_date_for_time_only_followup(self):
        now = datetime(2026, 6, 28, 19, 47, 0, tzinfo=KST)
        pending_start = datetime(2026, 6, 30, 11, 0, 0, tzinfo=KST)
        parsed = parse_natural_korean_datetime(
            "\uADF8\uB7EC\uBA74 12\uC2DC\uBD80\uD130\uB85C \uD574\uC918",
            now,
            default_date=pending_start,
        )
        self.assertEqual(datetime(2026, 6, 30, 12, 0, 0, tzinfo=KST), parsed)

    def test_parse_natural_korean_datetime_explicit_date_overrides_default_date(self):
        now = datetime(2026, 6, 28, 19, 47, 0, tzinfo=KST)
        pending_start = datetime(2026, 6, 30, 11, 0, 0, tzinfo=KST)
        parsed = parse_natural_korean_datetime(
            "\uB0B4\uC77C 12\uC2DC\uBD80\uD130\uB85C \uD574\uC918",
            now,
            default_date=pending_start,
        )
        self.assertEqual(datetime(2026, 6, 29, 12, 0, 0, tzinfo=KST), parsed)

    def test_parse_natural_korean_datetime_next_weekday(self):
        now = datetime(2026, 6, 28, 14, 5, 0, tzinfo=KST)  # Sunday
        parsed = parse_natural_korean_datetime("\uB2E4\uC74C\uC8FC \uC6D4\uC694\uC77C \uC624\uC804 10\uC2DC", now)
        self.assertEqual(datetime(2026, 6, 29, 10, 0, 0, tzinfo=KST), parsed)


if __name__ == "__main__":
    unittest.main()
