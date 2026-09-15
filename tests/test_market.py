"""The only module that speaks HTTP. Every failure it has must be typed.

A crawler that cannot tell "the venue said nothing" from "we failed to ask"
writes gaps into the record that look like data, so `MarketUnavailable` is the
contract and a bare ValueError escaping is a defect.
"""
from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import config, market


def body(payload: dict):
    """A fresh response per call - a retry must not read an exhausted stream."""
    def make(*_args, **_kw):
        return mock.MagicMock(
            __enter__=mock.MagicMock(
                return_value=io.BytesIO(json.dumps(payload).encode())),
            __exit__=mock.MagicMock(return_value=False))
    return make


def ok(data):
    """One response. Use `body(...)` where a retry may read it again."""
    return mock.MagicMock(
        __enter__=mock.MagicMock(return_value=io.BytesIO(
            json.dumps({"code": "00000", "msg": "success", "data": data}).encode())),
        __exit__=mock.MagicMock(return_value=False))


class EveryFailureIsTyped(unittest.TestCase):
    def assert_typed(self, **kw):
        with mock.patch("urllib.request.urlopen", **kw), \
             mock.patch("time.sleep"), \
             self.assertRaises(market.MarketUnavailable) as caught:
            market.tickers()
        return caught.exception.reason

    def test_an_http_error(self):
        self.assertIn("503", self.assert_typed(
            side_effect=urllib.error.HTTPError("u", 503, "x", {}, None)))

    def test_an_unreachable_host(self):
        self.assertIn("unreachable", self.assert_typed(
            side_effect=urllib.error.URLError("no route")))

    def test_a_timeout(self):
        self.assertIn("timeout", self.assert_typed(side_effect=TimeoutError()))

    def test_malformed_json(self):
        def broken(*_a, **_k):
            return mock.MagicMock(
                __enter__=mock.MagicMock(return_value=io.BytesIO(b"<html>502</html>")),
                __exit__=mock.MagicMock(return_value=False))
        self.assertIn("malformed json", self.assert_typed(side_effect=broken))

    def test_an_api_level_error_code(self):
        self.assertIn("40020", self.assert_typed(
            side_effect=body({"code": "40020", "msg": "bad interval"})))

    def test_data_that_is_neither_a_list_nor_an_object(self):
        self.assertIn("expected", self.assert_typed(
            side_effect=body({"code": "00000", "data": "nope"})))

    def test_a_malformed_orderbook_level_does_not_raise_untyped(self):
        """It used to escape as a bare ValueError, breaking the contract."""
        with mock.patch("urllib.request.urlopen", return_value=ok(
                {"b": [["100", "5"], ["bad", "level"], [], ["99", "3"]],
                 "a": [["101", "5"]]})):
            bids, asks = market.orderbook("RTSLAUSDT")
        self.assertEqual(bids, [[100.0, 5.0], [99.0, 3.0]])
        self.assertEqual(asks, [[101.0, 5.0]])


class Retries(unittest.TestCase):
    def test_it_retries_then_gives_up_with_the_last_reason(self):
        calls = []
        def fail(req, timeout=None):
            calls.append(timeout)
            raise urllib.error.URLError("down")
        with mock.patch("urllib.request.urlopen", fail), mock.patch("time.sleep"), \
             self.assertRaises(market.MarketUnavailable):
            market.tickers()
        self.assertEqual(len(calls), config.HTTP_RETRIES)

    def test_the_quick_budget_is_shorter_and_tries_fewer_times(self):
        calls = []
        def fail(req, timeout=None):
            calls.append(timeout)
            raise urllib.error.URLError("down")
        with mock.patch("urllib.request.urlopen", fail), mock.patch("time.sleep"), \
             self.assertRaises(market.MarketUnavailable):
            market.tickers(quick=True)
        self.assertEqual(len(calls), config.REQUEST_RETRIES)
        self.assertEqual(set(calls), {config.REQUEST_TIMEOUT_S})

    def test_a_later_attempt_can_succeed(self):
        attempts = iter([urllib.error.URLError("blip"), ok([{"symbol": "BTCUSDT"}])])
        def flaky(req, timeout=None):
            nxt = next(attempts)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        with mock.patch("urllib.request.urlopen", flaky), mock.patch("time.sleep"):
            self.assertEqual(market.tickers(), [{"symbol": "BTCUSDT"}])


class QueryStrings(unittest.TestCase):
    def test_parameters_are_url_encoded_not_interpolated(self):
        captured = {}
        def capture(req, timeout=None):
            captured["url"] = req.full_url
            return ok({"b": [], "a": []})
        with mock.patch("urllib.request.urlopen", capture):
            market.orderbook("R&limit=9999#USDT")
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(captured["url"]).query)
        self.assertEqual(parsed["symbol"], ["R&limit=9999#USDT"])
        self.assertEqual(parsed["limit"], ["150"], "an injected param must not win")


class SilenceIsNotZero(unittest.TestCase):
    """An empty depth response is not proof of an empty market."""

    def test_real_depth_is_reported_as_orderbook(self):
        with mock.patch.object(market, "orderbook",
                               return_value=([[100.0, 5.0]], [[101.0, 5.0]])):
            self.assertEqual(market.depth_or_touch("X")[2], "orderbook")

    def test_empty_depth_with_a_live_quote_falls_back_to_the_touch(self):
        with mock.patch.object(market, "orderbook", return_value=([], [])), \
             mock.patch.object(market, "ticker", return_value={
                 "bid1Price": "100", "bid1Size": "2",
                 "ask1Price": "101", "ask1Size": "3"}):
            bids, asks, source = market.depth_or_touch("X")
        self.assertEqual(source, "touch")
        self.assertEqual((bids, asks), ([[100.0, 2.0]], [[101.0, 3.0]]))

    def test_empty_depth_and_no_quote_is_none_not_an_empty_orderbook(self):
        with mock.patch.object(market, "orderbook", return_value=([], [])), \
             mock.patch.object(market, "ticker",
                               side_effect=market.MarketUnavailable("absent")):
            self.assertEqual(market.depth_or_touch("X"), ([], [], "none"))

    def test_a_zero_sized_touch_is_not_a_level(self):
        with mock.patch.object(market, "orderbook", return_value=([], [])), \
             mock.patch.object(market, "ticker", return_value={
                 "bid1Price": "100", "bid1Size": "0",
                 "ask1Price": "0", "ask1Size": "0"}):
            self.assertEqual(market.depth_or_touch("X")[2], "none")


class Candles(unittest.TestCase):
    def test_positional_rows_are_named(self):
        with mock.patch("urllib.request.urlopen", return_value=ok(
                [["1700000000000", "1", "2", "0.5", "1.5", "10", "15"]])):
            rows = market.candles("X")
        self.assertEqual(rows[0]["quote_vol"], 15.0)
        self.assertEqual(rows[0]["close"], 1.5)

    def test_short_or_unparseable_rows_are_skipped_not_fatal(self):
        with mock.patch("urllib.request.urlopen", return_value=ok(
                [["1", "2"], ["1700000000000", "1", "2", "0.5", "1.5", "10", "15"],
                 ["x", "y", "z", "a", "b", "c", "d"]])):
            self.assertEqual(len(market.candles("X")), 1)

    def test_rows_come_back_oldest_first(self):
        with mock.patch("urllib.request.urlopen", return_value=ok(
                [["300", "1", "1", "1", "1", "1", "1"],
                 ["100", "1", "1", "1", "1", "1", "1"]])):
            self.assertEqual([r["ts"] for r in market.candles("X")], [100, 300])


if __name__ == "__main__":
    unittest.main()
