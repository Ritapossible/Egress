"""The page must state the record, not a memory of it.

MEMORY.md rule 5: no measured figure is ever typed into a template. These tests
enforce it by perturbing the facts and checking the page follows.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from egress import page

FACTS = {
    "generated": "2026-09-14T14:00:00+00:00",
    "universe": {"stock": 1175, "crypto": 584, "metal": 2},
    "listed_total": 1761,
    "coverage": {"snapshots": 12, "rows": 21132, "gaps": []},
    "latest": {},
    "phases": [
        {"phase": "open", "snapshots": 5, "stock": 18.8, "crypto": 11.3,
         "ratio": 1.7},
        {"phase": "overnight", "snapshots": 7, "stock": 158.0, "crypto": 10.3,
         "ratio": 15.3},
    ],
    "snapshots": [],
    "notional_usdt": 25_000.0,
    "examples": [
        {"symbol": "RTSLAUSDT", "kind": "stock", "total_bp": 13.0,
         "book_usdt": 599968.0, "source": "orderbook", "floor": False},
        {"symbol": "RPBRUSDT", "kind": "stock", "total_bp": 22.0,
         "book_usdt": 21.0, "source": "touch", "floor": True},
        {"symbol": "RDEADUSDT", "kind": "stock",
         "error": "RDEADUSDT is not in the ticker feed"},
    ],
}


class RendersFromTheRecord(unittest.TestCase):
    def setUp(self):
        self.html = page.render(FACTS)

    def test_the_universe_count_comes_from_facts(self):
        self.assertIn("1,175", self.html)
        self.assertIn("584", self.html)

    def test_both_phases_are_shown_with_their_snapshot_counts(self):
        for fragment in ("18.8 bp", "158.0 bp", "11.3 bp", "15.3x"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.html)

    def test_a_floor_is_marked_as_a_floor(self):
        """A cost the book could not fully price must not read as exact."""
        self.assertIn("&gt;22 bp", self.html)
        self.assertIn("13 bp", self.html)

    def test_a_symbol_the_venue_would_not_price_is_shown_not_dropped(self):
        self.assertIn("RDEADUSDT", self.html)
        self.assertIn("not in the ticker feed", self.html)

    def test_touch_sourced_rows_say_so(self):
        self.assertIn("top of book only", self.html)

    def test_the_page_declares_its_figures_estimated(self):
        self.assertIn("estimated, never observed", self.html)

    def test_perturbing_the_facts_moves_the_page(self):
        """The guard against a number being typed into the template."""
        other = {**FACTS, "universe": {"stock": 99, "crypto": 7}}
        moved = page.render(other)
        self.assertIn("99", moved)
        self.assertNotIn("1,175", moved)

    def test_gap_count_is_singular_or_plural_correctly(self):
        one = page.render({**FACTS, "coverage": {**FACTS["coverage"],
                                                 "gaps": [{"minutes": 60}]}})
        self.assertIn("Gap in the record", one)
        self.assertIn("Gaps in the record", self.html)


class StandsAlone(unittest.TestCase):
    def test_no_external_request_of_any_kind(self):
        """One file a judge can open offline. No CDN, no webfont, no tracker."""
        html = page.render(FACTS)
        for forbidden in ("http://", "fonts.googleapis", "cdn.", "<script",
                          "<iframe", "@import"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, html)

    def test_the_only_link_out_is_the_source_repository(self):
        html = page.render(FACTS)
        self.assertEqual(html.count("https://"), 1)
        self.assertIn("github.com/Ritapossible/Egress", html)

    def test_it_is_responsive(self):
        html = page.render(FACTS)
        self.assertIn('name="viewport"', html)
        self.assertIn("@media", html)


if __name__ == "__main__":
    unittest.main()
