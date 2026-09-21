"""The reference market, via Bitget's `equity_price_quote` Skill.

The order book says what leaving costs on this venue. It cannot say what the
position is worth, because the market that prices it is shut for most of the
week - the premise of this whole project. The Skill supplies the other half,
and the rule it has to obey is the rule everything else here obeys: never
invent a number, and state the reason when there isn't one.

Network-free. The transport is exercised against supplied payloads.
"""
from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test_desk import BOOK, LISTED, SPEC

from egress import desk, llm, market, mcp

QUOTE = {"data": {"results": [{
    "symbol": "TSLA", "bid": 364.18, "ask": 364.19, "last_price": 364.18,
    "last_timestamp": "2026-09-18T23:59:58.183801Z"}]}}


class TheReferenceIsNeverInvented(unittest.TestCase):
    def test_a_good_answer_is_priced(self):
        with mock.patch.object(mcp, "query", return_value=QUOTE):
            out = mcp.underlying("TSLA")
        self.assertTrue(out["available"])
        self.assertEqual(out["last_price"], 364.18)
        self.assertEqual(out["source"], "bitget-mcp-server")

    def test_an_unreachable_skill_states_the_reason(self):
        with mock.patch.object(mcp, "query",
                               side_effect=mcp.McpUnavailable("HTTP 503")):
            out = mcp.underlying("TSLA")
        self.assertFalse(out["available"])
        self.assertIn("503", out["reason"])
        self.assertNotIn("last_price", out)

    def test_an_unexpected_exception_is_still_an_answer(self):
        """The desk promises every failure is stated, not raised."""
        with mock.patch.object(mcp, "query", side_effect=ValueError("boom")):
            out = mcp.underlying("TSLA")
        self.assertFalse(out["available"])
        self.assertIn("ValueError", out["reason"])

    def test_an_empty_result_set_is_not_a_price(self):
        with mock.patch.object(mcp, "query", return_value={"data": {"results": []}}):
            out = mcp.underlying("ZZZZ")
        self.assertFalse(out["available"])
        self.assertNotIn("last_price", out)

    def test_a_nonsense_price_is_refused(self):
        for bad in (0, -1, None, "364.18"):
            with self.subTest(bad=bad), \
                 mock.patch.object(mcp, "query", return_value={
                     "data": {"results": [{"last_price": bad}]}}):
                out = mcp.underlying("TSLA")
                self.assertFalse(out["available"], f"{bad!r} was priced")

    def test_the_basis_is_signed_the_way_the_page_reads_it(self):
        """Positive means the token is marked ABOVE the share."""
        self.assertGreater(mcp.basis_bp(369.5, 364.18), 0)
        self.assertLess(mcp.basis_bp(360.0, 364.18), 0)
        self.assertAlmostEqual(mcp.basis_bp(364.18 * 1.01, 364.18), 100.0, places=6)


class TheDeskCarriesTheReference(unittest.TestCase):
    def setUp(self):
        desk._UNIVERSE_CACHE[0] = None

    def answer(self, reference):
        with mock.patch.object(llm, "compile_question", return_value=SPEC), \
             mock.patch.object(mcp, "underlying", return_value=dict(reference)), \
             mock.patch.object(market, "depth_or_touch",
                               return_value=(*BOOK, "orderbook")):
            return desk.answer("cost to leave 40k TSLA", LISTED)

    def priced(self):
        now = dt.datetime.now(dt.timezone.utc)
        printed = (now - dt.timedelta(hours=57)).isoformat().replace("+00:00", "Z")
        return {"available": True, "source": "bitget-mcp-server",
                "entry": "equity_price_quote", "ticker": "TSLA",
                "last_price": 100.0, "printed_at": printed}

    def test_the_basis_and_the_age_reach_the_answer(self):
        out = self.answer(self.priced())
        ref = out["reference"]
        self.assertTrue(ref["available"])
        self.assertIn("basis_bp", ref)
        self.assertAlmostEqual(ref["hours_since_print"], 57.0, delta=0.2)

    def test_the_usdt_assumption_is_declared_when_a_basis_is_shown(self):
        """1 USDT is not 1 USD. Quoting a basis without saying so states a
        measurement where there is an assumption."""
        out = self.answer(self.priced())
        self.assertTrue(any("1 USDT as 1 USD" in u for u in out["unverified"]))

    def test_no_basis_and_no_caveat_when_the_skill_is_down(self):
        out = self.answer({"available": False, "reason": "HTTP 503"})
        self.assertFalse(out["reference"]["available"])
        self.assertNotIn("basis_bp", out["reference"])
        self.assertFalse(any("1 USDT as 1 USD" in u for u in out["unverified"]))

    def test_a_dead_skill_does_not_cost_the_answer(self):
        """The reference is additive. Everything the desk said before it
        existed must still be there when the Skill is down."""
        out = self.answer({"available": False, "reason": "HTTP 503"})
        for key in ("headline", "quote", "plan", "verdict", "reading", "advice"):
            self.assertIn(key, out, f"{key} was lost when the Skill failed")
        self.assertNotIn("error", out)

    def test_a_bad_timestamp_drops_the_age_not_the_basis(self):
        ref = self.priced() | {"printed_at": "not a timestamp"}
        out = self.answer(ref)
        self.assertIn("basis_bp", out["reference"])
        self.assertNotIn("hours_since_print", out["reference"])


class TheBudgetFitsAPersonWaiting(unittest.TestCase):
    """Ballast could afford 30s and three retries for a nightly job. Here the
    same budget is 90 seconds of someone watching a spinner."""

    def test_the_fuse_is_short(self):
        self.assertLessEqual(mcp.TIMEOUT, 8)
        self.assertLessEqual(mcp.RETRIES, 1)


if __name__ == "__main__":
    unittest.main()
