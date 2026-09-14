"""The store's one guarantee: a snapshot nobody finished is never read back."""
from __future__ import annotations

import datetime as dt
import gzip
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import store

UTC = dt.timezone.utc
TS = int(dt.datetime(2026, 9, 14, 12, 0, tzinfo=UTC).timestamp() * 1000)


def tickers(n: int, prefix: str = "SYM") -> list[dict]:
    return [{"symbol": f"{prefix}{i}USDT", "bid1Price": "10", "ask1Price": "10.1",
             "bid1Size": "5", "ask1Size": "6", "lastPrice": "10.05",
             "turnover24h": "1000", "ts": str(TS)} for i in range(n)]


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_then_read(self):
        store.append(store.rows_from(tickers(3), TS), TS, self.root)
        rows = store.read_day(dt.date(2026, 9, 14), self.root)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["symbol"], "SYM0USDT")
        self.assertEqual(rows[0]["bid"], "10")

    def test_appends_accumulate_in_one_file(self):
        for ts in (TS, TS + 300_000, TS + 600_000):
            store.append(store.rows_from(tickers(2), ts), ts, self.root)
        self.assertEqual(len(store.read_day(dt.date(2026, 9, 14), self.root)), 6)
        files = list((self.root / store.SNAPSHOT_DIR).glob("*.csv.gz"))
        self.assertEqual(len(files), 1, "one day is one file")

    def test_a_snapshot_missing_from_the_manifest_is_not_read(self):
        """The guarantee. A killed writer leaves rows; the manifest disowns them."""
        store.append(store.rows_from(tickers(2), TS), TS, self.root)
        path = self.root / store.SNAPSHOT_DIR / "2026-09-14.csv.gz"
        orphan = TS + 300_000
        with gzip.open(path, "at", encoding="utf-8") as fh:
            fh.write(f"{orphan},GHOSTUSDT,1,1,1,1,1,1,{orphan}\n")
        symbols = {r["symbol"] for r in store.read_day(dt.date(2026, 9, 14), self.root)}
        self.assertNotIn("GHOSTUSDT", symbols)

    def test_the_header_never_returns_as_data(self):
        store.append(store.rows_from(tickers(2), TS), TS, self.root)
        rows = store.read_day(dt.date(2026, 9, 14), self.root)
        self.assertTrue(all(r["symbol"] != "symbol" for r in rows))

    def test_blank_venue_fields_stay_blank_rather_than_becoming_zero(self):
        """An absent quote and a zero quote are different facts."""
        rows = store.rows_from([{"symbol": "XUSDT", "bid1Price": None,
                                 "ask1Price": ""}], TS)
        self.assertEqual(rows[0][2], "")
        self.assertEqual(rows[0][3], "")

    def test_every_instrument_is_stored_including_the_control_group(self):
        mixed = tickers(2, "RTSLA") + tickers(3, "BTC")
        self.assertEqual(len(store.rows_from(mixed, TS)), 5)


class Coverage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_gaps_are_reported_not_smoothed(self):
        for ts in (TS, TS + 300_000, TS + 7_200_000):      # two hours missing
            store.append(store.rows_from(tickers(1), ts), ts, self.root)
        cover = store.coverage(self.root)
        self.assertEqual(cover["snapshots"], 3)
        self.assertEqual(len(cover["gaps"]), 1)
        self.assertAlmostEqual(cover["gaps"][0]["minutes"], 115.0, places=0)

    def test_an_empty_record_says_so(self):
        self.assertEqual(store.coverage(self.root)["snapshots"], 0)


if __name__ == "__main__":
    unittest.main()
