"""The request path must fit inside the serverless function's budget.

A timeout raised for a good local reason is how a working endpoint becomes a
platform 504: the function is killed mid-answer and the client gets an HTML
error page it cannot parse. These tests make that arithmetic a failing test
rather than a comment nobody rechecks.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from fnmatch import fnmatch
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

    @staticmethod
    def included() -> str:
        cfg = json.loads((ROOT / "vercel.json").read_text())
        return cfg["functions"]["api/ask.py"]["includeFiles"]

    def test_every_file_the_desk_reads_at_runtime_ships_with_it(self):
        """Found the hard way, twice.

        Without state/universe.json every valid ticker answers "not listed".
        Without state/benchmark.json the verdict and the comparison vanish -
        which shipped, because includeFiles named one file rather than the set.
        So this reads the source for the paths instead of trusting a list.
        """
        source = "\n".join((ROOT / "egress" / name).read_text()
                            for name in ("desk.py", "universe.py"))
        wanted = set(re.findall(r'config\.STATE\) / "([^"]+\.json)"', source))
        self.assertEqual(wanted, {"universe.json", "benchmark.json",
                                  "symbol_marks.json"},
                         "the desk reads a state file this test does not know "
                         "about - check it is in vercel.json includeFiles")
        pattern = self.included()
        for name in wanted:
            with self.subTest(file=name):
                self.assertTrue(fnmatch(f"state/{name}", pattern),
                                f"state/{name} is not matched by {pattern!r}, "
                                f"so it will not exist on the deployment")

    def test_the_declared_files_actually_exist_in_the_repo(self):
        matched = list(ROOT.glob(self.included()))
        self.assertTrue(matched, f"{self.included()!r} matches nothing")

    def test_the_snapshots_do_not_ship_with_the_function(self):
        """They grow ~11 MB a day and the function never reads them."""
        for path in (ROOT / "state" / "snapshots").glob("*"):
            rel = str(path.relative_to(ROOT))
            with self.subTest(file=rel):
                self.assertFalse(fnmatch(rel, self.included()),
                                 "the crawler's record must not be bundled "
                                 "into the serverless function")


if __name__ == "__main__":
    unittest.main()
