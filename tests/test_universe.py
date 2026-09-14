"""The classification bug this module exists to prevent.

R*USDT looks like a clean way to find tokenized stocks and is wrong 28 times in
the live listing set. These fixtures are real rows from the venue.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import universe

REAL = [
    {"symbol": "RTSLAUSDT", "symbolType": "stock", "baseCoin": "rTSLA",
     "status": "online", "buyLimitPriceRatio": "0.1", "minOrderAmount": "10"},
    {"symbol": "RNVDAUSDT", "symbolType": "stock", "baseCoin": "rNVDA",
     "status": "online", "buyLimitPriceRatio": "0.1", "minOrderAmount": "10"},
    # iExec. Not Royal Caribbean.
    {"symbol": "RLCUSDT", "symbolType": "crypto", "baseCoin": "RLC",
     "status": "online", "buyLimitPriceRatio": "0.02", "minOrderAmount": "1"},
    {"symbol": "RENDERUSDT", "symbolType": "crypto", "baseCoin": "RENDER",
     "status": "online", "buyLimitPriceRatio": "0.02", "minOrderAmount": "1"},
    # A tokenized stock that carries no R prefix at all.
    {"symbol": "PRESPCXUSDT", "symbolType": "stock", "baseCoin": "PRESPCX",
     "status": "online", "buyLimitPriceRatio": "0.1", "minOrderAmount": "10"},
]


class Classification(unittest.TestCase):
    def setUp(self):
        self.u = universe.classify(REAL)

    def test_r_prefixed_crypto_is_not_a_stock(self):
        for symbol in ("RLCUSDT", "RENDERUSDT"):
            with self.subTest(symbol=symbol):
                self.assertEqual(self.u[symbol]["type"], universe.CRYPTO)
                self.assertNotIn(symbol, universe.of_type(self.u, universe.STOCK))

    def test_a_stock_without_the_prefix_is_still_a_stock(self):
        self.assertIn("PRESPCXUSDT", universe.of_type(self.u, universe.STOCK))

    def test_the_heuristic_this_replaces_would_have_been_wrong(self):
        """Stated as a test so nobody reintroduces it as a shortcut."""
        naive = {r["symbol"] for r in REAL
                 if r["symbol"].startswith("R") and r["symbol"].endswith("USDT")}
        truth = set(universe.of_type(self.u, universe.STOCK))
        self.assertNotEqual(naive, truth)
        self.assertIn("RLCUSDT", naive - truth)        # false positive
        self.assertIn("PRESPCXUSDT", truth - naive)    # false negative

    def test_counts_are_by_declared_type(self):
        self.assertEqual(universe.counts(self.u), {"crypto": 2, "stock": 3})

    def test_the_price_band_is_kept(self):
        """A 10% collar on stocks and 2% on crypto is the venue conceding these
        instruments behave differently. It belongs in the record."""
        self.assertEqual(self.u["RTSLAUSDT"]["band"], "0.1")
        self.assertEqual(self.u["RLCUSDT"]["band"], "0.02")


if __name__ == "__main__":
    unittest.main()
