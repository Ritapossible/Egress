"""The serverless endpoint, driven over a real socket.

`api/ask.py` had no tests at all, and it is the only thing a judge actually
touches. These run the handler through http.server so the request line, the
headers, the status code and the body are exercised exactly as Vercel will.

The contract it must keep:
  - every response is valid JSON (allow_nan=False), or it is an error
  - no exception ever reaches the platform as an HTML 500
  - one caller cannot spend the whole reader key
"""
from __future__ import annotations

import http.client
import importlib.util
import json
import sys
import threading
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("ask", ROOT / "api" / "ask.py")
ask = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ask)

from egress import desk, llm  # noqa: E402  - after the path insert


class Endpoint(unittest.TestCase):
    def setUp(self):
        ask._recent.clear()
        self.server = HTTPServer(("127.0.0.1", 0), ask.handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def call(self, method="POST", body=None, raw=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        payload = raw if raw is not None else (
            json.dumps(body).encode() if body is not None else b"")
        conn.request(method, "/api/ask", payload,
                     headers or {"Content-Type": "application/json"})
        resp = conn.getresponse()
        text = resp.read().decode()
        conn.close()
        # The client parses strictly. A bare NaN would raise here, as it does
        # in a browser.
        parsed = json.loads(text, parse_constant=_reject)
        return resp.status, parsed


def _reject(constant):
    raise AssertionError(f"response carried the invalid JSON token {constant!r}")


class Health(Endpoint):
    def test_get_reports_whether_the_reader_is_configured(self):
        status, out = self.call("GET")
        self.assertEqual(status, 200)
        self.assertIn("reader_configured", out)


class Validation(Endpoint):
    def test_a_non_json_body_is_a_400(self):
        status, out = self.call(raw=b"not json at all")
        self.assertEqual(status, 400)
        self.assertIn("send JSON", out["error"])

    def test_an_empty_question_is_a_400(self):
        status, out = self.call(body={"q": "   "})
        self.assertEqual(status, 400)
        self.assertIn("ask something", out["error"])

    def test_a_missing_q_is_a_400(self):
        self.assertEqual(self.call(body={"other": "x"})[0], 400)

    def test_a_non_string_q_is_a_400_not_a_crash(self):
        for value in ({"q": 5}, {"q": ["a"]}, {"q": None}, {"q": {"a": 1}}):
            with self.subTest(value=value):
                self.assertEqual(self.call(body=value)[0], 400)

    def test_an_oversized_body_is_refused_not_truncated(self):
        """Truncating produced a confusing 'send JSON' for a size problem."""
        status, out = self.call(body={"q": "T" * (ask.MAX_BODY + 500)})
        self.assertEqual(status, 413)
        self.assertIn("over", out["error"])

    def test_a_lying_content_length_does_not_hang_or_crash(self):
        status, _ignored = self.call(raw=b'{"q":"hi"}',
                              headers={"Content-Type": "application/json",
                                       "Content-Length": "8"})
        self.assertIn(status, (200, 400, 503))


class ReaderNotConfigured(Endpoint):
    def test_a_missing_key_is_a_503_that_names_the_variable(self):
        with mock.patch.object(llm, "configured", return_value=False):
            status, out = self.call(body={"q": "cost to exit TSLA"})
        self.assertEqual(status, 503)
        self.assertIn("QWEN_API_KEY", out["error"])


class Answering(Endpoint):
    def test_a_good_answer_comes_back_as_200_json(self):
        answer = {"symbol": "RTSLAUSDT", "reading": "costs about 14 bp",
                  "quote": {"quotable": True, "total_bp": 14.0}}
        with mock.patch.object(llm, "configured", return_value=True), \
             mock.patch.object(ask.desk, "answer", return_value=answer):
            status, out = self.call(body={"q": "cost to exit TSLA"})
        self.assertEqual(status, 200)
        self.assertEqual(out["symbol"], "RTSLAUSDT")

    def test_a_desk_that_raises_becomes_a_502_not_an_html_500(self):
        """The regression: a venue outage used to reach Vercel as a traceback."""
        with mock.patch.object(llm, "configured", return_value=True), \
             mock.patch.object(ask.desk, "answer",
                               side_effect=RuntimeError("boom")):
            status, out = self.call(body={"q": "cost to exit TSLA"})
        self.assertEqual(status, 502)
        self.assertIn("RuntimeError", out["error"])

    def test_a_non_finite_number_never_ships_as_invalid_json(self):
        """allow_nan=False is the backstop. NaN must become a stated error."""
        with mock.patch.object(llm, "configured", return_value=True), \
             mock.patch.object(ask.desk, "answer",
                               return_value={"total_bp": float("nan")}):
            status, out = self.call(body={"q": "cost to exit TSLA"})
        self.assertEqual(status, 500)
        self.assertIn("unrepresentable", out["error"])

    def test_the_question_is_truncated_before_it_reaches_the_desk(self):
        seen = {}
        def capture(question, *a, **k):
            seen["q"] = question
            return {"reading": "ok"}
        with mock.patch.object(llm, "configured", return_value=True), \
             mock.patch.object(ask.desk, "answer", capture):
            self.call(body={"q": "T" * 3000})
        self.assertEqual(len(seen["q"]), ask.MAX_QUESTION)


class RateLimit(Endpoint):
    def test_a_burst_is_refused_with_429_once_the_window_fills(self):
        with mock.patch.object(llm, "configured", return_value=True), \
             mock.patch.object(ask.desk, "answer", return_value={"reading": "ok"}):
            codes = [self.call(body={"q": "cost to exit TSLA"})[0]
                     for _ in range(ask.RATE_LIMIT + 3)]
        self.assertEqual(codes[:ask.RATE_LIMIT], [200] * ask.RATE_LIMIT)
        self.assertEqual(set(codes[ask.RATE_LIMIT:]), {429})

    def test_the_limit_is_checked_after_the_key_check(self):
        """An unconfigured deployment should say so, not rate-limit first."""
        with mock.patch.object(llm, "configured", return_value=False):
            codes = [self.call(body={"q": "x"})[0]
                     for _ in range(ask.RATE_LIMIT + 2)]
        self.assertEqual(set(codes), {503})

    def test_the_window_rolls_forward(self):
        with mock.patch.object(llm, "configured", return_value=True), \
             mock.patch.object(ask.desk, "answer", return_value={"reading": "ok"}):
            for _ in range(ask.RATE_LIMIT):
                self.call(body={"q": "x"})
            self.assertEqual(self.call(body={"q": "x"})[0], 429)
            ask._recent.clear()          # stands in for the window expiring
            self.assertEqual(self.call(body={"q": "x"})[0], 200)


class RealDeskIntegration(Endpoint):
    """The endpoint over the real desk, with only the venue and reader stubbed."""

    def test_an_unquotable_symbol_returns_200_and_parseable_json(self):
        from egress import market
        spec = {"ticker": "TSLA", "notional_usdt": 1000.0,
                "confident": True, "model": "stub"}
        listed = {"RTSLAUSDT": {"type": "stock", "status": "online"}}
        with mock.patch.object(llm, "configured", return_value=True), \
             mock.patch.object(llm, "compile_question", return_value=spec), \
             mock.patch.object(market, "depth_or_touch", return_value=([], [], "none")), \
             mock.patch.object(desk, "listed_symbols", return_value=listed):
            status, out = self.call(body={"q": "cost to exit TSLA"})
        self.assertEqual(status, 200)
        self.assertFalse(out["quote"]["quotable"])
        self.assertIsNone(out["quote"]["total_bp"])
        self.assertIn("no exit can be priced", out["reading"])


if __name__ == "__main__":
    unittest.main()
