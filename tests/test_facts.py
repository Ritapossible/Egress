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


if __name__ == "__main__":
    unittest.main()
