"""The request path must fit inside the serverless function's budget.

A timeout raised for a good local reason is how a working endpoint becomes a
platform 504: the function is killed mid-answer and the client gets an HTML
error page it cannot parse. These tests make that arithmetic a failing test
rather than a comment nobody rechecks.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import config, llm

ROOT = Path(__file__).resolve().parent.parent


class RequestBudget(unittest.TestCase):
    def worst_case_s(self) -> float:
        """Reader, then the book, then the touch fallback. Plus any backoff."""
        backoff = sum(2 ** a for a in range(1, config.REQUEST_RETRIES))
        per_call = config.REQUEST_TIMEOUT_S * config.REQUEST_RETRIES + backoff
        return llm.TIMEOUT_S + per_call * 2

    def test_the_worst_case_fits_inside_the_function_budget(self):
        self.assertLess(self.worst_case_s(), config.FUNCTION_BUDGET_S,
                        "the request path can outlive the serverless function")

    def test_the_crawler_keeps_the_patient_budget(self):
        """The impatient budget must never be imposed on the record."""
        self.assertGreater(config.HTTP_TIMEOUT_S, config.REQUEST_TIMEOUT_S)
        self.assertGreater(config.HTTP_RETRIES, config.REQUEST_RETRIES)

    def test_vercel_max_duration_matches_the_declared_budget(self):
        cfg = json.loads((ROOT / "vercel.json").read_text())
        self.assertEqual(cfg["functions"]["api/ask.py"]["maxDuration"],
                         config.FUNCTION_BUDGET_S)

    def test_the_universe_ships_with_the_function(self):
        """Without it every valid ticker answers 'not listed'."""
        cfg = json.loads((ROOT / "vercel.json").read_text())
        self.assertIn("universe.json",
                      cfg["functions"]["api/ask.py"]["includeFiles"])

    def test_the_snapshots_do_not_ship_with_the_function(self):
        """They grow ~11 MB a day and the function never reads them."""
        includes = json.loads((ROOT / "vercel.json").read_text())
        included = includes["functions"]["api/ask.py"]["includeFiles"]
        self.assertNotIn("snapshots", included)


if __name__ == "__main__":
    unittest.main()
