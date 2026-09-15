"""The desk is the product, and until now it had no tests at all.

Two promises are enforced here, because both were broken in ways the rest of
the suite could not see:

1. `answer()` returns a stated result for every failure. It used to raise
   MarketUnavailable straight through to the serverless handler, which turns
   into an HTML 500 page the client cannot read an error out of.
2. Everything it returns survives `json.dumps(..., allow_nan=False)`. A cost
   the book cannot price used to serialise as a bare `NaN` - valid Python,
   invalid JSON - so the browser threw a parse error instead of showing the
   honest answer the desk had already computed.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import desk, exitcost, llm, market, universe

SPEC = {"ticker": "TSLA", "notional_usdt": 40_000.0, "confident": True,
        "model": "stub"}
LISTED = {
    "RTSLAUSDT": {"type": "stock", "status": "online"},
    "RHALTUSDT": {"type": "stock", "status": "offline"},
    "BTCUSDT": {"type": "crypto", "status": "online"},
}
BOOK = ([[100.0, 500.0], [99.0, 500.0]], [[101.0, 500.0]])


def strict_json(payload: dict) -> str:
    """The exact call api/ask.py makes. Raises on any non-finite number."""
    return json.dumps(payload, allow_nan=False)


class Resolution(unittest.TestCase):
    """Selection from the live universe, never generation."""

    def test_a_listed_ticker_resolves(self):
        self.assertEqual(desk.resolve("TSLA", LISTED), "RTSLAUSDT")

    def test_case_and_padding_do_not_matter(self):
        self.assertEqual(desk.resolve("  tsla ", LISTED), "RTSLAUSDT")

    def test_an_unlisted_ticker_resolves_to_nothing(self):
        self.assertIsNone(desk.resolve("FAKECO", LISTED))

    def test_an_offline_listing_is_not_tradable_so_not_resolved(self):
        self.assertIsNone(desk.resolve("HALT", LISTED))

    def test_a_crypto_pair_is_not_a_tokenized_stock(self):
        self.assertIsNone(desk.resolve("BTC", LISTED))

    def test_an_empty_universe_file_is_refetched_not_believed(self):
        """{} means the file is missing, never that the market is empty."""
        with mock.patch.object(universe, "load", return_value={}), \
             mock.patch.object(market, "instruments",
                               return_value=[{"symbol": "RTSLAUSDT",
                                              "symbolType": "stock",
                                              "status": "online"}]) as fetch:
            self.assertEqual(desk.resolve("TSLA"), "RTSLAUSDT")
        fetch.assert_called_once()


class EveryFailureIsStated(unittest.TestCase):
    """The docstring's promise, enforced. Each case must also be valid JSON."""

    def answer(self, spec=SPEC, book=(*BOOK, "orderbook")):
        with mock.patch.object(llm, "compile_question", return_value=spec), \
             mock.patch.object(market, "depth_or_touch", return_value=book):
            return desk.answer("what does leaving 40k of TSLA cost?", LISTED)

    def assert_stated(self, out, fragment):
        self.assertIn("error", out, "a failure must be stated, not raised")
        self.assertIn(fragment, out["error"])
        strict_json(out)

    def test_an_unreadable_question(self):
        with mock.patch.object(llm, "compile_question",
                               side_effect=llm.ReaderUnavailable("no key")):
            out = desk.answer("q", LISTED)
        self.assert_stated(out, "could not read the question")

    def test_a_question_with_no_ticker_in_it(self):
        out = self.answer(spec={**SPEC, "ticker": None})
        self.assert_stated(out, "no US stock ticker found")

    def test_a_ticker_the_venue_does_not_list(self):
        out = self.answer(spec={**SPEC, "ticker": "FAKECO"})
        self.assert_stated(out, "not listed as a tokenized stock")

    def test_a_venue_that_will_not_return_a_book(self):
        """The regression: this used to raise straight through the handler."""
        with mock.patch.object(llm, "compile_question", return_value=SPEC), \
             mock.patch.object(market, "depth_or_touch",
                               side_effect=market.MarketUnavailable("http 503")):
            out = desk.answer("q", LISTED)
        self.assert_stated(out, "would not return a book")

    def test_a_universe_that_cannot_be_read_at_all(self):
        with mock.patch.object(llm, "compile_question", return_value=SPEC), \
             mock.patch.object(universe, "load", return_value={}), \
             mock.patch.object(market, "instruments",
                               side_effect=market.MarketUnavailable("http 500")):
            out = desk.answer("q")
        self.assert_stated(out, "listed universe could not be read")


class TheAnswerIsAlwaysValidJson(unittest.TestCase):
    """api/ask.py serialises with allow_nan=False. Nothing may trip it."""

    def answer_with(self, book):
        with mock.patch.object(llm, "compile_question", return_value=SPEC), \
             mock.patch.object(market, "depth_or_touch", return_value=book):
            return desk.answer("q", LISTED)

    def test_a_priced_exit(self):
        out = self.answer_with((*BOOK, "orderbook"))
        strict_json(out)
        self.assertTrue(out["quote"]["quotable"])
        self.assertIn("costs about", out["reading"])

    def test_a_book_with_no_two_sided_market(self):
        """The bug: this serialised as a bare NaN and broke JSON.parse."""
        out = self.answer_with(([], [], "none"))
        strict_json(out)
        self.assertFalse(out["quote"]["quotable"])
        self.assertIsNone(out["quote"]["total_bp"])
        self.assertIn("no exit can be priced", out["reading"])

    def test_a_one_sided_book(self):
        """4 of 1,175 listed stocks were in this state when it was found."""
        out = self.answer_with(([[100.0, 5.0]], [], "orderbook"))
        strict_json(out)
        self.assertFalse(out["quote"]["quotable"])

    def test_a_touch_only_book_is_marked_a_floor(self):
        out = self.answer_with(([[100.0, 1.0]], [[101.0, 1.0]], "touch"))
        strict_json(out)
        self.assertEqual(out["quote"]["source"], "touch")
        self.assertIn("floor", out["reading"])


class OneQuestionIsOneRoundTrip(unittest.TestCase):
    """The quote, the plan and the max-exit search must see one same book."""

    def test_the_book_is_fetched_exactly_once(self):
        with mock.patch.object(llm, "compile_question", return_value=SPEC), \
             mock.patch.object(market, "depth_or_touch",
                               return_value=(*BOOK, "orderbook")) as fetch:
            desk.answer("q", LISTED)
        self.assertEqual(fetch.call_count, 1,
                         "two fetches let the quote and the plan describe "
                         "two different moments of the market")

    def test_the_book_is_fetched_on_the_impatient_budget(self):
        with mock.patch.object(llm, "compile_question", return_value=SPEC), \
             mock.patch.object(market, "depth_or_touch",
                               return_value=(*BOOK, "orderbook")) as fetch:
            desk.answer("q", LISTED)
        self.assertTrue(fetch.call_args.kwargs.get("quick"),
                        "a user is waiting; the crawler's budget is too patient")


class NumbersComeFromCodeNotTheReader(unittest.TestCase):
    def test_a_reader_that_invents_a_cost_is_ignored(self):
        """The model supplies a ticker and a size. Nothing else is read."""
        lying = {**SPEC, "total_bp": 1.0, "cost": "free", "reading": "it's free"}
        with mock.patch.object(llm, "compile_question", return_value=lying), \
             mock.patch.object(market, "depth_or_touch",
                               return_value=(*BOOK, "orderbook")):
            out = desk.answer("q", LISTED)
        self.assertNotIn("free", out["reading"])
        expected = exitcost.from_book("RTSLAUSDT", 40_000.0, *BOOK, "orderbook")
        self.assertEqual(out["quote"]["total_bp"], expected.total_bp)


if __name__ == "__main__":
    unittest.main()
