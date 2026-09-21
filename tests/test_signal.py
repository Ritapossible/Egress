"""bitget-signal, and the difference between empty and unreachable.

The claim this module exists to make is narrow and has to stay narrow: the
Skill answers, its catalogs are real, its live fetches are not, and its feed
list is almost entirely crypto - so it cannot explain a move in a tokenized US
stock. Every one of those is checkable, and each has a test here.

Network-free. The transport is exercised against supplied payloads.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import mcp, signal

FEEDS = ["cointelegraph", "decrypt", "cnbc", "fed", "bbc_world"]
SOURCES = {"feeds": FEEDS}
LATEST_EMPTY = [{"feed": f, "error": "", "items": []} for f in FEEDS]
LATEST_FULL = [{"feed": "cnbc", "error": "", "items": [{"title": "a"},
                                                       {"title": "b"}]},
               {"feed": "decrypt", "error": "", "items": []}]
SERIES = {"available_indicators": {"cpi": "CPI", "pce": "PCE"}}
ASSETS = {"assets": {"btc": "BTC-USD", "spx": "^GSPC"}}


def _payloads(latest=LATEST_EMPTY, price=None):
    def fake(tool, arguments=None, endpoint=None, timeout=None):
        action = (arguments or {}).get("action")
        if tool == "news_feed" and action == "sources":
            return SOURCES
        if tool == "news_feed" and action == "latest":
            return latest
        if tool == "macro_indicators":
            return SERIES
        if tool == "cross_asset":
            return ASSETS
        if tool == "crypto_price":
            if price is None:
                raise mcp.McpUnavailable("TimeoutError")
            return price
        raise AssertionError(f"unexpected call {tool} {arguments}")
    return fake


class EmptyIsNotTheSameAsUnreachable(unittest.TestCase):
    """Both are failures; they are failures of different things, and a record
    that collapses them tells a reader nothing about the service."""

    def probe(self, **kw):
        with mock.patch.object(mcp, "call", _payloads(**kw)):
            return signal.probe()

    def test_a_feed_that_answers_with_nothing_is_recorded_as_answering(self):
        row = next(r for r in self.probe()["results"]
                   if r["tool"] == "news_feed" and r["action"] == "latest")
        self.assertTrue(row["answered"])
        self.assertEqual(row["articles"], 0)
        self.assertEqual(row["feeds_reporting"], len(FEEDS))

    def test_a_tool_that_never_replies_is_recorded_as_not_answering(self):
        row = next(r for r in self.probe()["results"] if r["tool"] == "crypto_price")
        self.assertFalse(row["answered"])
        self.assertIn("Timeout", row["reason"])

    def test_articles_are_counted_inside_the_envelopes_not_across_them(self):
        """`latest` returns one envelope per feed. Counting envelopes would
        report a headline per feed where there are none - a dead upstream
        reading as a busy one."""
        self.assertEqual(signal._articles(LATEST_EMPTY), 0)
        self.assertEqual(signal._articles(LATEST_FULL), 2)

    def test_live_answering_needs_content_not_just_a_reply(self):
        """An answer of zero articles is still zero articles."""
        self.assertEqual(self.probe()["live_answering"], 0)
        self.assertEqual(self.probe(latest=LATEST_FULL)["live_answering"], 1)

    def test_the_catalogs_are_counted_separately(self):
        self.assertEqual(self.probe()["catalogs_answering"], 3)


class TheFeedListIsNamedNotCounted(unittest.TestCase):
    def test_the_equity_capable_feeds_are_identified(self):
        with mock.patch.object(mcp, "call", _payloads()):
            out = signal.probe()
        self.assertEqual(out["feed_count"], len(FEEDS))
        self.assertEqual(out["equity_capable"], ["cnbc"])

    def test_a_crypto_only_list_claims_no_equity_coverage(self):
        crypto_only = {"feeds": ["cointelegraph", "decrypt", "bitcoinist"]}

        def fake(tool, arguments=None, endpoint=None, timeout=None):
            if tool == "news_feed" and (arguments or {}).get("action") == "sources":
                return crypto_only
            return _payloads()(tool, arguments, endpoint, timeout)

        with mock.patch.object(mcp, "call", fake):
            self.assertEqual(signal.probe()["equity_capable"], [])


class TheProbeNeverRaises(unittest.TestCase):
    """The crawl must not die because a third party did."""

    def test_an_unexpected_exception_becomes_a_recorded_reason(self):
        with mock.patch.object(mcp, "call", side_effect=ValueError("boom")):
            out = signal.probe()
        self.assertEqual(len(out["results"]), len(signal.PROBES))
        self.assertTrue(all(r["answered"] is False for r in out["results"]))
        self.assertTrue(all("ValueError" in r["reason"] for r in out["results"]))

    def test_everything_down_still_produces_a_readable_record(self):
        with mock.patch.object(mcp, "call", side_effect=mcp.McpUnavailable("503")):
            out = signal.probe()
        self.assertEqual(out["feed_count"], 0)
        self.assertEqual(out["catalogs_answering"], 0)
        self.assertEqual(out["live_answering"], 0)
        json.dumps(out)  # the crawl writes this


class TheProbeWaitsLongerThanTheDesk(unittest.TestCase):
    """At the desk's six-second fuse both live actions timed out, which records
    "we gave up" where the truth was "the feed answered with nothing"."""

    def test_the_schedule_can_afford_to_wait(self):
        self.assertGreater(signal.PROBE_TIMEOUT, mcp.TIMEOUT)

    def test_the_probe_passes_its_own_timeout_down(self):
        seen = {}

        def fake(tool, arguments=None, endpoint=None, timeout=None):
            seen["timeout"] = timeout
            return SOURCES

        with mock.patch.object(mcp, "call", fake):
            signal.call("news_feed", action="sources")
        self.assertEqual(seen["timeout"], signal.PROBE_TIMEOUT)


class TheRecordRoundTrips(unittest.TestCase):
    def test_write_then_load(self):
        import tempfile

        from egress import config
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(config, "STATE", Path(d)), \
             mock.patch.object(mcp, "call", _payloads()):
            written = signal.write()
            self.assertTrue(written.exists())
            back = signal.load()
        self.assertEqual(back["feed_count"], len(FEEDS))


if __name__ == "__main__":
    unittest.main()
