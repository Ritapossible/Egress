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
from typing import ClassVar
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

    def setUp(self):
        desk._UNIVERSE_CACHE[0] = None

    def test_an_empty_universe_file_is_refetched_not_believed(self):
        """{} means the file is missing, never that the market is empty."""
        with mock.patch.object(universe, "load", return_value={}), \
             mock.patch.object(market, "instruments",
                               return_value=[{"symbol": "RTSLAUSDT",
                                              "symbolType": "stock",
                                              "status": "online"}]) as fetch:
            self.assertEqual(desk.resolve("TSLA"), "RTSLAUSDT")
        fetch.assert_called_once()

    def test_the_fallback_is_cached_so_it_is_not_a_download_per_question(self):
        with mock.patch.object(universe, "load", return_value={}), \
             mock.patch.object(market, "instruments",
                               return_value=[{"symbol": "RTSLAUSDT",
                                              "symbolType": "stock",
                                              "status": "online"}]) as fetch:
            for _ in range(5):
                desk.resolve("TSLA")
        self.assertEqual(fetch.call_count, 1)


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


class ClientFixturesStayInSync(unittest.TestCase):
    """tools/fixtures/answers.json drives the browser test of desk.js.

    A fixture that drifts from what `answer()` actually returns makes the
    client gate green while the real panel is broken, so the shapes are
    checked against live output here.
    """

    FIXTURES = (Path(__file__).resolve().parent.parent
                / "tools" / "fixtures" / "answers.json")

    def setUp(self):
        self.saved = json.loads(self.FIXTURES.read_text())
        desk._UNIVERSE_CACHE[0] = None

    def produce(self, book):
        with mock.patch.object(llm, "compile_question", return_value=SPEC), \
             mock.patch.object(market, "depth_or_touch", **book):
            return desk.answer("cost to exit 40000 USDT of TSLA", LISTED)

    def test_every_fixture_is_a_shape_the_desk_still_produces(self):
        live = {
            "priced": self.produce({"return_value": (*BOOK, "orderbook")}),
            "floor": self.produce({"return_value": (
                [[358.0, 1.0]], [[358.5, 1.0]], "touch")}),
            "unquotable": self.produce({"return_value": ([], [], "none")}),
            "error": self.produce({
                "side_effect": market.MarketUnavailable("http 503")}),
        }
        self.assertEqual(set(live), set(self.saved),
                         "a fixture case no longer matches the desk's cases")
        for name, answer in live.items():
            with self.subTest(case=name):
                self.assertEqual(set(answer), set(self.saved[name]),
                                 f"the {name} answer's keys have changed - "
                                 f"regenerate tools/fixtures/answers.json")

    def test_a_priced_answer_carries_what_the_panel_renders(self):
        answer = self.produce({"return_value": (*BOOK, "orderbook")})
        for key in ("headline", "context", "advice", "verdict", "quote",
                    "plan", "unverified", "reading"):
            with self.subTest(key=key):
                self.assertIn(key, answer)

    def test_a_floor_answer_carries_the_warning_the_panel_shows(self):
        answer = self.produce({"return_value": (
            [[358.0, 1.0]], [[358.5, 1.0]], "touch")})
        self.assertTrue(answer["depth_note"])
        self.assertIn("floor", answer["depth_note"])


class TheVerdict(unittest.TestCase):
    """The answer leads with a judgement, and the judgement comes from the
    record - not from a threshold somebody typed into a template."""

    MARKS: ClassVar[dict] = {
        "overnight": {"stock_median_bp": 160.0, "snapshots": 141},
        "open": {"stock_median_bp": 8.0, "snapshots": 62}}

    def test_the_bands_read_the_way_a_desk_would_say_them(self):
        for total_bp, expected in ((16.0, "cheap"), (80.0, "cheap"),
                                   (160.0, "about typical"),
                                   (400.0, "expensive"),
                                   (2000.0, "very expensive")):
            with self.subTest(bp=total_bp):
                self.assertEqual(
                    desk._verdict(total_bp, "overnight", self.MARKS)["label"],
                    expected)

    def test_the_same_cost_is_judged_against_its_own_phase(self):
        """16 bp is cheap at night and expensive while New York is open.

        This is the whole point of comparing per phase: an exit cost is only
        good or bad relative to what the same market charges at the same hour.
        """
        self.assertEqual(desk._verdict(16.0, "overnight", self.MARKS)["label"],
                         "cheap")
        self.assertEqual(desk._verdict(16.0, "open", self.MARKS)["label"],
                         "expensive")

    def test_no_benchmark_means_no_verdict_rather_than_a_guess(self):
        verdict = desk._verdict(16.0, "overnight", {})
        self.assertEqual(verdict["label"], "")
        self.assertIsNone(verdict["median_bp"])

    def test_an_unknown_phase_does_not_invent_a_comparison(self):
        self.assertEqual(desk._verdict(16.0, "holiday", self.MARKS)["label"], "")

    def test_the_context_sentence_states_the_figure_behind_it(self):
        verdict = desk._verdict(16.0, "overnight", self.MARKS)
        sentence = desk._context({}, verdict, "overnight")
        self.assertIn("10x cheaper", sentence)
        self.assertIn("160 bp", sentence)
        self.assertIn("141", sentence)

    def test_no_context_without_a_benchmark(self):
        self.assertEqual(
            desk._context({}, desk._verdict(16.0, "x", {}), "x"), "")

    def test_a_missing_benchmark_file_is_not_an_error(self):
        with mock.patch.object(desk.config, "STATE", Path("/nonexistent")):
            self.assertEqual(desk.benchmark(), {})

    def test_the_benchmark_is_read_from_the_record_not_typed(self):
        """Perturb the file, and the verdict must follow."""
        import json as _json
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "benchmark.json").write_text(_json.dumps(
                {"phases": {"overnight": {"stock_median_bp": 4.0,
                                          "snapshots": 9}}}))
            with mock.patch.object(desk.config, "STATE", root):
                marks = desk.benchmark()
        # 16 bp against a 4 bp median is 4x - expensive, not cheap. The same
        # 16 bp against the real 163 bp median reads "cheap".
        self.assertEqual(desk._verdict(16.0, "overnight", marks)["label"],
                         "expensive")


class TheAdvice(unittest.TestCase):
    def plan(self, rows):
        return {"plan": [{"slices": n, "best_case_bp": b, "worst_case_bp": w,
                          "quotable": True} for n, b, w in rows]}

    def test_it_says_when_splitting_is_not_worth_it(self):
        out = self.plan([(1, 16.1, 16.1), (4, 15.6, 16.1), (12, 15.5, 16.1)])
        self.assertIn("not worth the effort", desk._advice(out, {}))

    def test_it_quantifies_a_saving_worth_having(self):
        out = self.plan([(1, 300.0, 300.0), (4, 120.0, 300.0),
                         (12, 80.0, 300.0)])
        advice = desk._advice(out, {})
        self.assertIn("Split into 12 orders", advice)
        self.assertIn("220 bp", advice)
        self.assertIn("only if the book refills", advice)

    def test_a_saving_that_rounds_to_one_bp_is_not_advice(self):
        """"Save up to 1 bp" contradicts its own caveat. Do not say it."""
        out = self.plan([(1, 16.1, 16.1), (4, 15.0, 16.1), (12, 14.9, 16.1)])
        self.assertIn("not worth the effort", desk._advice(out, {}))

    def test_no_plan_means_no_advice_rather_than_filler(self):
        self.assertEqual(desk._advice({"plan": []}, {}), "")
        self.assertEqual(desk._advice({}, {}), "")

    def test_an_unquotable_plan_is_ignored(self):
        out = {"plan": [{"slices": 4, "quotable": False}]}
        self.assertEqual(desk._advice(out, {}), "")


class PreIpoListings(unittest.TestCase):
    """Bitget lists tokenized exposure to companies with no US listing.

    Those carry no `r` prefix: OpenAI exists only as PREOPAIUSDT, so resolving
    on R*/bare alone told a holder of a live instrument it was not listed. SPCX
    carries BOTH lines at once, and they are different books at different costs.
    """

    LISTED: ClassVar[dict] = {
        "RTSLAUSDT": {"type": "stock", "status": "online"},
        "RSPCXUSDT": {"type": "stock", "status": "online"},
        "PRESPCXUSDT": {"type": "stock", "status": "online"},
        "PREOPAIUSDT": {"type": "stock", "status": "online"},
        "RGONEUSDT": {"type": "stock", "status": "offline"},
        "SUIUSDT": {"type": "crypto", "status": "online"},
    }

    def test_a_pre_ipo_only_name_resolves(self):
        self.assertEqual(desk.resolve("OPAI", self.LISTED), "PREOPAIUSDT")

    def test_the_rtoken_line_wins_when_a_name_has_both(self):
        self.assertEqual(desk.resolve("SPCX", self.LISTED), "RSPCXUSDT")

    def test_both_lines_are_reported_so_the_choice_is_not_silent(self):
        self.assertEqual(desk._listings("SPCX", self.LISTED),
                         ["RSPCXUSDT", "PRESPCXUSDT"])

    def test_a_single_line_name_has_no_alternatives(self):
        self.assertEqual(desk._listings("TSLA", self.LISTED), ["RTSLAUSDT"])

    def test_an_offline_listing_is_not_resolved(self):
        self.assertIsNone(desk.resolve("GONE", self.LISTED))

    def test_a_crypto_symbol_is_still_refused(self):
        """The desk prices tokenized stocks; the prefix search must not widen that."""
        self.assertIsNone(desk.resolve("SUI", self.LISTED))

    def test_an_unlisted_ticker_stays_unlisted(self):
        self.assertIsNone(desk.resolve("ZZQQ", self.LISTED))
