"""The validation must refuse data it has shown to be untrustworthy.

The venue's candle volume and its 24h turnover agree to within 2% on crypto and
diverge by 6x to 16x on tokenized stocks. A validation that averaged over both
would produce a number people trust and should not.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import validate


def bars(quote_vol: float, n: int = 24, step_ms: int = 3_600_000) -> list[dict]:
    return [{"ts": 1_789_000_000_000 + i * step_ms, "open": 1.0, "high": 1.0,
             "low": 1.0, "close": 1.0, "base_vol": quote_vol,
             "quote_vol": quote_vol} for i in range(n)]


def patched(candles, ticker):
    return mock.patch.multiple("egress.market",
                               candles=mock.Mock(return_value=candles),
                               ticker=mock.Mock(return_value=ticker))


class FeedAgreement(unittest.TestCase):
    def test_agreeing_feeds_pass(self):
        """Crypto: 24 bars sum to the 24h figure."""
        with patched(bars(100.0), {"turnover24h": "2400"}):
            out = validate.feed_agreement("BTCUSDT")
        self.assertTrue(out["agrees"])
        self.assertAlmostEqual(out["ratio"], 1.0, places=2)

    def test_a_sixfold_divergence_is_rejected(self):
        """The tokenized-stock case, at the mildest ratio actually measured."""
        with patched(bars(100.0), {"turnover24h": "400"}):
            out = validate.feed_agreement("RTSLAUSDT")
        self.assertFalse(out["agrees"])
        self.assertIn("6.0x", out["reason"])

    def test_a_missing_turnover_is_not_treated_as_agreement(self):
        with patched(bars(100.0), {"turnover24h": "0"}):
            self.assertFalse(validate.feed_agreement("XUSDT")["agrees"])

    def test_too_few_bars_is_not_treated_as_agreement(self):
        with patched(bars(100.0, n=5), {"turnover24h": "500"}):
            out = validate.feed_agreement("XUSDT")
        self.assertFalse(out["agrees"])
        self.assertIn("5 hourly bars", out["reason"])

    def test_an_unreachable_venue_is_not_treated_as_agreement(self):
        from egress.market import MarketUnavailable
        with mock.patch("egress.market.candles",
                        side_effect=MarketUnavailable("timeout")):
            self.assertFalse(validate.feed_agreement("XUSDT")["agrees"])


class ExclusionIsEnforced(unittest.TestCase):
    def test_a_disagreeing_symbol_is_never_scored(self):
        """The guard. Without it the headline would average over bad data."""
        with patched(bars(100.0), {"turnover24h": "400"}):
            out = validate.for_symbol("RTSLAUSDT")
        self.assertTrue(out["excluded"])
        self.assertEqual(out["bars"], 0)
        self.assertNotIn("median_ratio", out)

    def test_the_exclusion_reason_is_carried_not_swallowed(self):
        with patched(bars(100.0), {"turnover24h": "400"}):
            out = validate.for_symbol("RTSLAUSDT")
        self.assertIn("ticker", out["reason"])
        self.assertIsNotNone(out["feed_ratio"])


class Tolerance(unittest.TestCase):
    def test_the_band_admits_crypto_and_excludes_every_stock_ratio_seen(self):
        self.assertLess(validate.AGREE_LOW, 0.98)
        self.assertGreater(validate.AGREE_HIGH, 0.98)
        for measured in (4.2, 5.9, 6.1, 8.5, 9.0, 15.7):
            with self.subTest(ratio=measured):
                self.assertGreater(measured, validate.AGREE_HIGH)


if __name__ == "__main__":
    unittest.main()
