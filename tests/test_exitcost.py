"""The estimator, checked against arithmetic done by hand.

A test that only compares the code to itself proves the code is consistent, not
that it is right. The first case below is worked out longhand in the docstring.
"""
from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import exitcost

UTC = dt.timezone.utc
AT = dt.datetime(2026, 9, 14, 12, 0, tzinfo=UTC)

# bid side, best first
BIDS = [(100.0, 10.0), (99.0, 10.0), (98.0, 10.0)]
ASKS = [(100.2, 10.0), (101.0, 10.0)]
MID = 100.1


class HandComputed(unittest.TestCase):
    """Sell 1,500 USDT of a position whose mid is 100.1.

        quantity wanted = 1500 / 100.1            = 14.98501 units
        level 1: 10 units at 100.0                = 1,000.00
        level 2:  4.98501 units at 99.0           =   493.52
        proceeds                                  = 1,493.52
        vwap    = 1493.52 / 14.98501              =    99.668
        slippage = (100.1 - 99.668) / 100.1 * 1e4 =    43.2 bp
    """

    def setUp(self):
        self.q = exitcost.quote("XUSDT", 1500.0, BIDS, ASKS, fee_bp=10.0, at=AT)

    def test_reference_is_the_mid(self):
        self.assertAlmostEqual(self.q.reference, MID, places=6)

    def test_quantity(self):
        self.assertAlmostEqual(self.q.quantity, 1500 / MID, places=6)

    def test_vwap(self):
        self.assertAlmostEqual(self.q.vwap, 99.668, places=2)

    def test_slippage(self):
        self.assertAlmostEqual(self.q.slippage_bp, 43.2, places=1)

    def test_total_adds_the_fee(self):
        self.assertAlmostEqual(self.q.total_bp, 53.2, places=1)

    def test_two_levels_were_used(self):
        self.assertEqual(self.q.levels_used, 2)

    def test_not_exhausted(self):
        self.assertFalse(self.q.exhausted)


class TheSpreadIsACost(unittest.TestCase):
    def test_a_tiny_order_still_pays_half_the_spread(self):
        """Quoting against the best bid would hide this. It is real money."""
        q = exitcost.quote("XUSDT", 1.0, BIDS, ASKS, fee_bp=0.0, at=AT)
        half_spread_bp = (MID - 100.0) / MID * 1e4
        self.assertAlmostEqual(q.slippage_bp, half_spread_bp, places=2)
        self.assertGreater(q.slippage_bp, 0)

    def test_cost_rises_with_size(self):
        costs = [exitcost.quote("X", n, BIDS, ASKS, at=AT).total_bp
                 for n in (100, 1000, 2000, 2900)]
        self.assertEqual(costs, sorted(costs))


class RunningOutOfBookIsAResult(unittest.TestCase):
    def test_exhausted_is_flagged_not_raised(self):
        q = exitcost.quote("XUSDT", 1_000_000.0, BIDS, ASKS, at=AT)
        self.assertTrue(q.exhausted)
        self.assertLess(q.filled_usdt, 3000)

    def test_nothing_is_extrapolated_past_the_last_level(self):
        q = exitcost.quote("XUSDT", 1_000_000.0, BIDS, ASKS, at=AT)
        self.assertAlmostEqual(q.filled_usdt, 100 * 10 + 99 * 10 + 98 * 10, places=4)

    def test_the_shortfall_is_named_in_the_uncertainty_list(self):
        q = exitcost.quote("XUSDT", 1_000_000.0, BIDS, ASKS, at=AT)
        self.assertTrue(any("absorbed only" in u for u in q.unverified))

    def test_an_empty_bid_side_is_unquotable_not_free(self):
        q = exitcost.quote("XUSDT", 500.0, [], ASKS, at=AT)
        self.assertTrue(q.exhausted)
        self.assertEqual(q.filled_usdt, 0.0)
        self.assertTrue(any("unquotable" in u for u in q.unverified))

    def test_a_crossed_book_is_refused(self):
        q = exitcost.quote("XUSDT", 500.0, [(101.0, 5)], [(100.0, 5)], at=AT)
        self.assertTrue(any("unquotable" in u for u in q.unverified))

    def test_zero_size_levels_do_not_count_as_liquidity(self):
        q = exitcost.quote("XUSDT", 100.0, [(100.0, 0.0), (99.0, 10.0)], ASKS, at=AT)
        self.assertEqual(q.levels_used, 1)


class MaxExit(unittest.TestCase):
    def test_the_inverse_is_consistent_with_the_forward_quote(self):
        for budget in (30.0, 60.0, 120.0):
            with self.subTest(budget=budget):
                size = exitcost.max_exit(BIDS, ASKS, budget)
                self.assertGreater(size, 0)
                self.assertLessEqual(
                    exitcost.quote("X", size, BIDS, ASKS).total_bp, budget + 0.5)

    def test_a_budget_below_the_fee_buys_nothing(self):
        self.assertEqual(exitcost.max_exit(BIDS, ASKS, budget_bp=5.0, fee_bp=10.0), 0.0)

    def test_a_generous_budget_is_capped_by_the_book_not_the_budget(self):
        ceiling = sum(p * q for p, q in BIDS)
        self.assertAlmostEqual(exitcost.max_exit(BIDS, ASKS, 100_000.0),
                               round(ceiling, 2), places=2)

    def test_no_market_means_no_exit(self):
        self.assertEqual(exitcost.max_exit([], ASKS, 100.0), 0.0)


class SlicingReturnsBounds(unittest.TestCase):
    def test_the_interval_brackets_the_one_clip_cost(self):
        one = exitcost.quote("X", 2500.0, BIDS, ASKS).total_bp
        out = exitcost.sliced("X", 2500.0, 5, BIDS, ASKS)
        self.assertLessEqual(out["best_case_bp"], one)
        self.assertAlmostEqual(out["worst_case_bp"], one, places=2)

    def test_both_assumptions_are_stated(self):
        out = exitcost.sliced("X", 2500.0, 5, BIDS, ASKS)
        self.assertIn("refills", out["assumption_best"])
        self.assertIn("never refills", out["assumption_worst"])
        self.assertTrue(out["unverified"])

    def test_one_slice_is_not_cheaper_than_one_clip(self):
        out = exitcost.sliced("X", 2500.0, 1, BIDS, ASKS)
        self.assertAlmostEqual(out["best_case_bp"], out["worst_case_bp"], places=6)

    def test_slices_must_be_positive(self):
        with self.assertRaises(ValueError):
            exitcost.sliced("X", 100.0, 0, BIDS, ASKS)


class Contract(unittest.TestCase):
    def test_every_quote_says_it_is_an_estimate(self):
        q = exitcost.quote("XUSDT", 1000.0, BIDS, ASKS, at=AT)
        self.assertEqual(q.to_record()["basis"], "estimated")

    def test_every_quote_names_what_it_could_not_verify(self):
        q = exitcost.quote("XUSDT", 1000.0, BIDS, ASKS, at=AT)
        self.assertTrue(any("not guaranteed" in u for u in q.unverified))
        self.assertTrue(any("fee assumed" in u for u in q.unverified))

    def test_a_nonpositive_position_is_refused(self):
        for bad in (0.0, -1.0):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                exitcost.quote("XUSDT", bad, BIDS, ASKS)


if __name__ == "__main__":
    unittest.main()


class SilenceIsNotZero(unittest.TestCase):
    """The venue's depth endpoint and its ticker feed disagree, and it matters.

    RPBRUSDT and RSYKUSDT return `{"a": [], "b": []}` from `orderbook` while the
    ticker quotes them two-sided with over 2M USDT of 24h turnover. An earlier
    version of this estimator called that "NO EXIT" and would have shipped a
    venue quirk as the project's headline finding.
    """

    BOOKLESS = {"symbol": "RPBRUSDT", "bid1Price": "21.45", "ask1Price": "21.58",
                "bid1Size": "1", "ask1Size": "23", "turnover24h": "2390064.8"}

    def _patch(self, depth, ticker_row):
        from unittest import mock
        return mock.patch.multiple(
            "egress.market",
            orderbook=mock.Mock(return_value=depth),
            tickers=mock.Mock(return_value=[ticker_row]))

    def test_an_empty_depth_book_falls_back_to_the_touch(self):
        with self._patch(([], []), self.BOOKLESS):
            q = exitcost.for_symbol("RPBRUSDT", 25_000.0)
        self.assertEqual(q.source, "touch")
        self.assertGreater(q.book_usdt, 0, "the touch is real liquidity")

    def test_it_says_the_depth_is_unknown_rather_than_absent(self):
        with self._patch(([], []), self.BOOKLESS):
            q = exitcost.for_symbol("RPBRUSDT", 25_000.0)
        self.assertTrue(any("UNKNOWN, not absent" in u for u in q.unverified))
        self.assertTrue(any("floor on the cost" in u for u in q.unverified))

    def test_a_real_depth_book_is_still_labelled_as_such(self):
        with self._patch((BIDS, ASKS), self.BOOKLESS):
            q = exitcost.for_symbol("XUSDT", 1500.0)
        self.assertEqual(q.source, "orderbook")
        self.assertFalse(any("UNKNOWN" in u for u in q.unverified))

    def test_genuine_silence_on_both_feeds_is_reported_as_such(self):
        dead = {"symbol": "ZUSDT", "bid1Price": "0", "ask1Price": "0",
                "bid1Size": "0", "ask1Size": "0"}
        with self._patch(([], []), dead):
            q = exitcost.for_symbol("ZUSDT", 100.0)
        self.assertEqual(q.source, "none")
        self.assertTrue(any("neither depth nor a quote" in u for u in q.unverified))
