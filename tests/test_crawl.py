"""The crawler is the only part that cannot be caught up later.

So its one job is to survive: a venue blip, a failed universe refresh or a
write error must cost one snapshot, never the shift. Gaps stay visible in the
manifest rather than being papered over.
"""
from __future__ import annotations

import datetime as dt
import itertools
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import crawl, market, store, universe

UTC = dt.timezone.utc
TICKERS = [{"symbol": f"S{i}USDT", "bid1Price": "10", "ask1Price": "10.1",
            "bid1Size": "5", "ask1Size": "6", "lastPrice": "10",
            "turnover24h": "1000", "ts": "1"} for i in range(4)]


class OneSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_good_snapshot_is_stored_and_recorded(self):
        with mock.patch.object(market, "tickers", return_value=TICKERS):
            result = crawl.snapshot(self.root, verbose=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["rows"], 4)
        self.assertEqual(len(store.manifest(self.root)), 1)

    def test_a_venue_failure_records_nothing_and_says_why(self):
        with mock.patch.object(market, "tickers",
                               side_effect=market.MarketUnavailable("http 503")):
            result = crawl.snapshot(self.root, verbose=False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "http 503")
        self.assertEqual(store.manifest(self.root), [],
                         "an unfetched snapshot must leave a visible gap")

    def test_a_write_failure_ends_the_snapshot_not_the_shift(self):
        """A full disk used to raise straight out of the loop."""
        with mock.patch.object(market, "tickers", return_value=TICKERS), \
             mock.patch.object(store, "append",
                               side_effect=OSError("No space left on device")):
            result = crawl.snapshot(self.root, verbose=False)
        self.assertFalse(result["ok"])
        self.assertIn("No space left", result["reason"])
        self.assertEqual(store.manifest(self.root), [])


class FakeClock:
    """A clock the loop cannot outrun. Mocking sleep alone just spins."""

    def __init__(self, start: float = 1_000_800.0):
        # Grid-aligned: 1,000,800 is a whole number of 300s intervals, so the
        # first sleep is a full one and the arithmetic below is exact.
        self.now = start

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(seconds, 0.0)


class TheLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.clock = FakeClock()

    def tearDown(self):
        self.tmp.cleanup()

    def run_loop(self, outcomes, interval_s=300):
        seen = []
        def snap(*_a, **_k):
            ok = outcomes[len(seen)] if len(seen) < len(outcomes) else True
            seen.append(ok)
            self.clock.sleep(1.0)        # the fetch itself takes time
            return {"ok": ok, "snap_ts": 0}
        with mock.patch.object(crawl, "snapshot", snap), \
             mock.patch.object(crawl.time, "time", self.clock.time), \
             mock.patch.object(crawl.time, "sleep", self.clock.sleep):
            result = crawl.loop(hours=(interval_s * len(outcomes)) / 3600,
                                interval_s=interval_s, root=self.root,
                                verbose=False)
        return result, seen

    def test_it_counts_what_it_took_and_what_it_missed(self):
        result, seen = self.run_loop([True, False, True])
        self.assertEqual(len(seen), 3)
        self.assertEqual(result["taken"], 2)
        self.assertEqual(result["failed"], 1)

    def test_snapshots_land_on_the_interval_grid_despite_slow_work(self):
        """Sleeping a fixed amount after variable work walks the schedule."""
        stamps = []
        def snap(*_a, **_k):
            stamps.append(self.clock.now)
            self.clock.sleep(37.0)       # a slow fetch
            return {"ok": True, "snap_ts": 0}
        with mock.patch.object(crawl, "snapshot", snap), \
             mock.patch.object(crawl.time, "time", self.clock.time), \
             mock.patch.object(crawl.time, "sleep", self.clock.sleep):
            crawl.loop(hours=(300 * 4) / 3600, interval_s=300, root=self.root,
                       verbose=False)
        gaps = [round(b - a) for a, b in itertools.pairwise(stamps)]
        self.assertTrue(all(g == 300 for g in gaps),
                        f"drifted off the 300s grid: {gaps}")

    def test_it_stops_at_the_deadline(self):
        with mock.patch.object(crawl, "snapshot",
                               return_value={"ok": True, "snap_ts": 0}), \
             mock.patch.object(crawl.time, "time", self.clock.time), \
             mock.patch.object(crawl.time, "sleep", self.clock.sleep):
            result = crawl.loop(hours=0.0, interval_s=1, root=self.root,
                                verbose=False)
        self.assertEqual(result["taken"], 0)


class RunStartup(unittest.TestCase):
    def test_a_failed_universe_refresh_does_not_cost_the_shift(self):
        """The regression: a venue blip at 00:00 used to skip 5.8 hours."""
        with mock.patch.object(universe, "snapshot",
                               side_effect=market.MarketUnavailable("http 503")), \
             mock.patch.object(crawl, "loop",
                               return_value={"taken": 12, "failed": 0}) as ran:
            code = crawl.main(["--loop", "--hours", "0.01"])
        self.assertEqual(code, 0)
        ran.assert_called_once()

    def test_a_loop_that_took_nothing_exits_non_zero(self):
        with mock.patch.object(universe, "snapshot", return_value={}), \
             mock.patch.object(crawl, "loop",
                               return_value={"taken": 0, "failed": 9}):
            self.assertEqual(crawl.main(["--loop", "--hours", "0.01"]), 1)

    def test_coverage_reports_without_touching_the_venue(self):
        with mock.patch.object(market, "tickers",
                               side_effect=AssertionError("must not call out")):
            self.assertEqual(crawl.main(["--coverage"]), 0)


class CollectionIsSeparateFromInterpretation(unittest.TestCase):
    def test_the_crawler_does_not_import_the_calendar_or_the_estimator(self):
        """A wrong calendar must never be able to spoil a week of collection."""
        source = (Path(__file__).resolve().parent.parent
                  / "egress" / "crawl.py").read_text()
        for forbidden in ("sessions", "exitcost", "validate", "facts"):
            with self.subTest(module=forbidden):
                self.assertNotIn(f"import {forbidden}", source)
                self.assertNotIn(f", {forbidden}", source)


if __name__ == "__main__":
    unittest.main()
