"""The four regimes the study compares."""
from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import sessions

UTC = dt.timezone.utc


def at(y, m, d, hh, mm=0):
    return dt.datetime(y, m, d, hh, mm, tzinfo=UTC)


class Phases(unittest.TestCase):
    def test_a_weekday_crosses_open_and_close(self):
        self.assertEqual(sessions.phase(at(2026, 9, 14, 13, 29)), "overnight")
        self.assertEqual(sessions.phase(at(2026, 9, 14, 13, 30)), "open")
        self.assertEqual(sessions.phase(at(2026, 9, 14, 19, 59)), "open")
        self.assertEqual(sessions.phase(at(2026, 9, 14, 20, 0)), "overnight")

    def test_weekends_are_never_open(self):
        for day, label in ((12, "weekend"), (13, "weekend")):
            self.assertEqual(sessions.phase(at(2026, 9, day, 15)), label)

    def test_a_holiday_is_not_a_trading_day(self):
        """Labour Day 2026 falls on a Monday inside market hours."""
        self.assertEqual(sessions.phase(at(2026, 9, 7, 15)), "holiday")
        self.assertFalse(sessions.is_open(at(2026, 9, 7, 15)))

    def test_open_is_a_strict_subset_of_weekday_hours(self):
        self.assertTrue(sessions.is_open(at(2026, 9, 14, 15)))
        self.assertFalse(sessions.is_open(at(2026, 9, 14, 3)))

    def test_naive_weekday_check_would_call_a_holiday_tradeable(self):
        """Recorded because the obvious weekday() <= 4 test gets this wrong."""
        labour_day = dt.date(2026, 9, 7)
        self.assertTrue(labour_day.weekday() <= 4)
        self.assertFalse(sessions.is_trading_day(labour_day))


if __name__ == "__main__":
    unittest.main()


class DaylightSaving(unittest.TestCase):
    """The offset is computed, not assumed.

    Hardcoding the summer conversion was wrong by an hour from November to
    March - it would have labelled 13:30-14:30 UTC as "open" on every winter
    trading day, when New York had not yet rung the bell.
    """

    def test_the_transitions_land_on_the_right_sundays(self):
        self.assertFalse(sessions.is_dst(dt.date(2026, 3, 7)))
        self.assertTrue(sessions.is_dst(dt.date(2026, 3, 8)))    # 2nd Sunday
        self.assertTrue(sessions.is_dst(dt.date(2026, 10, 31)))
        self.assertFalse(sessions.is_dst(dt.date(2026, 11, 1)))  # 1st Sunday

    def test_the_offset_is_four_in_summer_and_five_in_winter(self):
        self.assertEqual(sessions.utc_offset_hours(dt.date(2026, 7, 1)), 4)
        self.assertEqual(sessions.utc_offset_hours(dt.date(2026, 12, 1)), 5)

    def test_the_session_shifts_with_the_clocks(self):
        self.assertEqual(sessions.open_close_utc(dt.date(2026, 9, 15)),
                         (dt.time(13, 30), dt.time(20, 0)))
        self.assertEqual(sessions.open_close_utc(dt.date(2026, 12, 15)),
                         (dt.time(14, 30), dt.time(21, 0)))

    def test_a_winter_morning_is_not_called_open_an_hour_early(self):
        """The regression: 13:45 UTC in December is 08:45 in New York."""
        early = dt.datetime(2026, 12, 15, 13, 45, tzinfo=dt.timezone.utc)
        self.assertFalse(sessions.is_open(early))
        self.assertEqual(sessions.phase(early), "overnight")
        open_now = dt.datetime(2026, 12, 15, 14, 45, tzinfo=dt.timezone.utc)
        self.assertTrue(sessions.is_open(open_now))

    def test_a_summer_day_is_unchanged(self):
        """The study window must read exactly as it did before."""
        self.assertTrue(sessions.is_open(
            dt.datetime(2026, 9, 15, 13, 45, tzinfo=dt.timezone.utc)))
        self.assertFalse(sessions.is_open(
            dt.datetime(2026, 9, 15, 20, 1, tzinfo=dt.timezone.utc)))

    def test_the_calendar_does_not_expire_at_new_year(self):
        """2027-01-01 is a holiday, not a normal Friday session."""
        self.assertEqual(sessions.phase(
            dt.datetime(2027, 1, 1, 15, 0, tzinfo=dt.timezone.utc)), "holiday")
