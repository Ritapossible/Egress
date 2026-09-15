"""The reader translates; it never judges.

Everything the model returns is treated as hostile input: a ticker is validated
against a shape, a size is clamped, and anything else in the response is
discarded. The point is that a bad model produces a visibly wrong SPEC, never
an invented number.
"""
from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import llm


def reply(content: str):
    """A stand-in for the chat-completions envelope."""
    body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
    return mock.MagicMock(__enter__=mock.MagicMock(
        return_value=io.BytesIO(body)), __exit__=mock.MagicMock(return_value=False))


def compile_with(content: str) -> dict:
    with mock.patch.dict("os.environ", {"QWEN_API_KEY": "test-key"}), \
         mock.patch("urllib.request.urlopen", return_value=reply(content)):
        return llm.compile_question("what does leaving 40k of TSLA cost?")


class Extraction(unittest.TestCase):
    def test_a_plain_object(self):
        out = compile_with('{"ticker":"TSLA","notional_usdt":40000,"confident":true}')
        self.assertEqual(out["ticker"], "TSLA")
        self.assertEqual(out["notional_usdt"], 40000.0)

    def test_a_fenced_object_with_prose_around_it(self):
        out = compile_with('Sure!\n```json\n{"ticker":"nvda"}\n```\nHope that helps')
        self.assertEqual(out["ticker"], "NVDA")

    def test_a_missing_size_defaults_rather_than_failing(self):
        self.assertEqual(compile_with('{"ticker":"AAPL"}')["notional_usdt"], 25_000.0)


class HostileOutput(unittest.TestCase):
    """Whatever the model does, the desk must not price a fiction."""

    def test_a_ticker_that_is_not_a_ticker_is_dropped(self):
        for junk in ('"tesla motors inc"', '"<script>"', '"TOOLONGTICKER"', '"R TSLA"'):
            with self.subTest(junk=junk):
                self.assertIsNone(compile_with(f'{{"ticker":{junk}}}')["ticker"])

    def test_a_null_ticker_is_honoured(self):
        self.assertIsNone(compile_with('{"ticker":null}')["ticker"])

    def test_a_negative_or_absurd_size_is_clamped(self):
        self.assertEqual(compile_with('{"ticker":"TSLA","notional_usdt":-5}')
                         ["notional_usdt"], 1.0)
        self.assertEqual(compile_with('{"ticker":"TSLA","notional_usdt":1e12}')
                         ["notional_usdt"], 50_000_000.0)

    def test_a_non_numeric_size_falls_back(self):
        self.assertEqual(compile_with('{"ticker":"TSLA","notional_usdt":"lots"}')
                         ["notional_usdt"], 25_000.0)

    def test_a_cost_the_model_volunteered_is_not_carried_through(self):
        out = compile_with('{"ticker":"TSLA","total_bp":3,"answer":"it is free"}')
        self.assertEqual(set(out), {"ticker", "notional_usdt", "confident", "model"})

    def test_prose_with_no_json_is_a_typed_failure(self):
        with self.assertRaises(llm.ReaderUnavailable):
            compile_with("I think leaving TSLA costs about 12 basis points.")

    def test_broken_json_is_a_typed_failure(self):
        with self.assertRaises(llm.ReaderUnavailable):
            compile_with('{"ticker": "TSLA",,}')

    def test_a_json_array_is_a_typed_failure(self):
        with self.assertRaises(llm.ReaderUnavailable):
            compile_with('["TSLA"]')


class Transport(unittest.TestCase):
    def test_no_key_is_a_typed_failure_not_a_crash(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
             self.assertRaises(llm.ReaderUnavailable) as caught:
            llm.compile_question("q")
        self.assertIn("QWEN_API_KEY", caught.exception.reason)

    def test_an_http_error_is_typed(self):
        with mock.patch.dict("os.environ", {"QWEN_API_KEY": "k"}), \
             mock.patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
                 "u", 429, "Too Many Requests", {}, None)), \
             self.assertRaises(llm.ReaderUnavailable) as caught:
            llm.compile_question("q")
        self.assertIn("429", caught.exception.reason)

    def test_an_unreachable_reader_is_typed(self):
        with mock.patch.dict("os.environ", {"QWEN_API_KEY": "k"}), \
             mock.patch("urllib.request.urlopen",
                        side_effect=urllib.error.URLError("dns")), \
             self.assertRaises(llm.ReaderUnavailable):
            llm.compile_question("q")

    def test_the_key_is_sent_as_a_bearer_header_and_not_in_the_url(self):
        captured = {}
        def capture(req, timeout=None):
            captured["url"] = req.full_url
            captured["auth"] = req.get_header("Authorization")
            return reply('{"ticker":"TSLA"}')
        with mock.patch.dict("os.environ", {"QWEN_API_KEY": "secret-key"}), \
             mock.patch("urllib.request.urlopen", capture):
            llm.compile_question("q")
        self.assertEqual(captured["auth"], "Bearer secret-key")
        self.assertNotIn("secret-key", captured["url"])

    def test_the_question_is_truncated_before_it_is_sent(self):
        captured = {}
        def capture(req, timeout=None):
            captured["body"] = json.loads(req.data)
            return reply('{"ticker":"TSLA"}')
        with mock.patch.dict("os.environ", {"QWEN_API_KEY": "k"}), \
             mock.patch("urllib.request.urlopen", capture):
            llm.compile_question("T" * 5000)
        self.assertEqual(len(captured["body"]["messages"][1]["content"]), 600)


if __name__ == "__main__":
    unittest.main()
