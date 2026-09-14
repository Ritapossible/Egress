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
