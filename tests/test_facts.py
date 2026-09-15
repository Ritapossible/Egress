"""The record the site reads from is the whole record, not today's slice.

The bug this guards: `by_snapshot` defaulted to `date.today()`. At 00:00 UTC
every table on the site emptied and stayed empty until the first snapshot of
the new day landed, while the footer kept reporting the full snapshot count
from the manifest. A judge opening the site after midnight saw a page that
claimed fifty snapshots and showed nothing.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import facts, store

UTC = dt.timezone.utc


def at(day: int, hour: int) -> int:
    return int(dt.datetime(2026, 9, day, hour, tzinfo=UTC).timestamp() * 1000)


def tickers(prefix: str, n: int, ts: int) -> list[dict]:
    return [{"symbol": f"{prefix}{i}USDT", "bid1Price": "10", "ask1Price": "10.1",
             "bid1Size": "5", "ask1Size": "6", "lastPrice": "10.05",
             "turnover24h": "1000", "ts": str(ts)} for i in range(n)]


class TheWholeRecord(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # Three snapshots spread over three separate UTC days.
        self.stamps = [at(13, 15), at(14, 15), at(15, 15)]
        for ts in self.stamps:
            store.append(store.rows_from(tickers("R", 2, ts), ts), ts, self.root)
        (self.root / "universe.json").write_text(json.dumps(
            {f"R{i}USDT": {"type": "stock"} for i in range(2)}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_days_lists_every_day_the_manifest_vouches_for(self):
        self.assertEqual(store.days(self.root),
                         [dt.date(2026, 9, 13), dt.date(2026, 9, 14),
                          dt.date(2026, 9, 15)])

    def test_days_ignores_a_snapshot_the_manifest_never_recorded(self):
        """Same rule as read_day: unfinished work is invisible to readers."""
        ts = at(16, 15)
        store.append(store.rows_from(tickers("R", 2, ts), ts), ts, self.root)
        manifest = self.root / store.MANIFEST
        kept = [ln for ln in manifest.read_text().splitlines()
                if ln.strip() and json.loads(ln)["snap_ts"] != ts]
        manifest.write_text("\n".join(kept) + "\n")
        self.assertNotIn(dt.date(2026, 9, 16), store.days(self.root))

    def test_by_snapshot_with_no_day_reads_every_day(self):
        summaries = facts.by_snapshot(root=self.root)
        self.assertEqual([s["snap_ts"] for s in summaries], self.stamps)

    def test_by_snapshot_still_narrows_when_a_day_is_named(self):
        only = facts.by_snapshot(dt.date(2026, 9, 14), self.root)
        self.assertEqual([s["snap_ts"] for s in only], [at(14, 15)])

    def test_the_record_does_not_empty_when_the_date_rolls_over(self):
        """The regression itself: no snapshot exists for 'today' at all."""
        tomorrow = dt.date(2026, 9, 16)
        self.assertEqual(facts.by_snapshot(tomorrow, self.root), [],
                         "sanity: that day really is empty")
        self.assertEqual(len(facts.by_snapshot(root=self.root)), 3,
                         "the site must still have the other three days")

    def test_the_snapshot_count_agrees_with_the_manifest(self):
        """The footer counts the manifest; the tables count summaries. If these
        two ever disagree the site is claiming evidence it is not showing."""
        self.assertEqual(len(facts.by_snapshot(root=self.root)),
                         store.coverage(self.root)["snapshots"])


class ReadingIsBounded(unittest.TestCase):
    """Reading the whole record must not mean holding the whole record.

    The first version materialised every row of every day at once: 311 MB at
    two days, on course for a gigabyte by the end of a week's crawl. Only the
    per-snapshot summaries need to outlive the day they came from.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.stamps = [at(d, 15) for d in (13, 14, 15)]
        for ts in self.stamps:
            store.append(store.rows_from(tickers("R", 3, ts), ts), ts, self.root)
        (self.root / "universe.json").write_text(json.dumps(
            {f"R{i}USDT": {"type": "stock"} for i in range(3)}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_one_day_is_held_at_a_time(self):
        seen = []
        real = store.read_day

        def watched(day, root=None):
            rows = real(day, root)
            seen.append(len(rows))
            return rows

        with mock.patch.object(store, "read_day", watched):
            facts.by_snapshot(root=self.root)
        self.assertEqual(len(seen), 3, "one read per day in the record")
        self.assertTrue(all(n == 3 for n in seen),
                        "each read must return one day, not the whole record")

    def test_the_answer_is_the_same_as_reading_the_days_one_by_one(self):
        whole = facts.by_snapshot(root=self.root)
        piecewise = [s for d in store.days(self.root)
                     for s in facts.by_snapshot(d, self.root)]
        self.assertEqual(whole, piecewise)


if __name__ == "__main__":
    unittest.main()


class TheBenchmarkNeverBlanksItself(unittest.TestCase):
    """The desk reads this file to judge an answer, and an empty one produces
    no error anywhere - it just silently removes the verdict and the comparison
    from every answer on the live site."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def snaps(n=3):
        return [{"snap_ts": i, "at": "", "phase": "overnight",
                 "stock": {"median_spread_bp": 160.0 + i},
                 "crypto": {"median_spread_bp": 11.0}} for i in range(n)]

    def test_a_populated_benchmark_is_written(self):
        facts.save_benchmark(self.root, self.snaps())
        written = json.loads((self.root / "benchmark.json").read_text())
        self.assertEqual(written["phases"]["overnight"]["stock_median_bp"], 161.0)

    def test_an_empty_one_is_fine_when_there_is_nothing_to_lose(self):
        path = facts.save_benchmark(self.root, [])
        self.assertEqual(json.loads(path.read_text())["phases"], {})

    def test_it_refuses_to_replace_a_populated_benchmark_with_nothing(self):
        facts.save_benchmark(self.root, self.snaps())
        with self.assertRaises(facts.BenchmarkEmpty):
            facts.save_benchmark(self.root, [])
        kept = json.loads((self.root / "benchmark.json").read_text())
        self.assertIn("overnight", kept["phases"],
                      "the standing comparison must survive an empty compute")

    def test_a_corrupt_existing_file_does_not_block_a_rewrite(self):
        (self.root / "benchmark.json").write_text("{ not json")
        facts.save_benchmark(self.root, [])
        self.assertEqual(
            json.loads((self.root / "benchmark.json").read_text())["phases"], {})

    def test_the_page_build_warns_rather_than_dying(self):
        from egress import page
        with mock.patch.object(page.facts, "save_benchmark",
                               side_effect=facts.BenchmarkEmpty("no phases")), \
             mock.patch.object(page.facts, "build", return_value=FACTS_MIN), \
             tempfile.TemporaryDirectory() as out:
            page.write(Path(out))          # must not raise
            self.assertTrue((Path(out) / "index.html").exists())


FACTS_MIN = {
    "generated": "2026-09-15T10:00:00+00:00",
    "universe": {"stock": 1, "crypto": 1}, "listed_total": 2,
    "coverage": {"snapshots": 1, "rows": 1, "gaps": []},
    "latest": {}, "phases": [], "snapshots": [], "notional_usdt": 25_000.0,
    "examples": [], "validation": {},
}
