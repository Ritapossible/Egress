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
        """One file a judge can open offline. No CDN, no webfont, no tracker.

        `http://www.w3.org/2000/svg` is excluded deliberately: it is an XML
        namespace identifier, required on the inline favicon, and never fetched
        by anything. Matching it would be matching a string, not a request.
        """
        html = page.render(FACTS).replace("http://www.w3.org/2000/svg", "")
        for forbidden in ("http://", "fonts.googleapis", "cdn.",
                          "<iframe", "@import"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, html)

    def test_the_favicon_is_inline_not_a_file_request(self):
        html = page.render(FACTS)
        self.assertIn('rel="icon" href="data:image/svg+xml,', html)

    def test_every_link_out_points_at_the_source_repository(self):
        import re
        html = page.render(FACTS)
        hosts = {re.match(r"https://([^/\"]+)", u).group(1)
                 for u in re.findall(r'https://[^"\s]+', html)}
        self.assertEqual(hosts, {"github.com"})

    def test_the_only_script_is_the_desk_and_it_is_external(self):
        """Inline script would force unsafe-inline into the CSP."""
        html = page.render(FACTS)
        self.assertIn('<script src="desk.js"></script>', html)
        self.assertEqual(html.count("<script"), 1)

    def test_it_is_responsive(self):
        html = page.render(FACTS)
        self.assertIn('name="viewport"', html)
        self.assertIn("@media", html)


if __name__ == "__main__":
    unittest.main()


class TheDesk(unittest.TestCase):
    """Track 3 is a research workbench, so there has to be somewhere to ask."""

    def setUp(self):
        self.html = page.render(FACTS)

    def test_there_is_an_input_that_posts_to_the_endpoint(self):
        self.assertIn('id="ask"', self.html)
        self.assertIn('action="/api/ask"', self.html)
        self.assertIn('<input id="q"', self.html)

    def test_the_form_still_has_a_label_for_screen_readers(self):
        self.assertIn('for="q"', self.html)

    def test_the_answer_region_announces_itself(self):
        self.assertIn('aria-live="polite"', self.html)

    def test_the_page_says_what_needs_javascript_and_what_does_not(self):
        self.assertIn("needs JavaScript", self.html)
        self.assertIn("read fine with", self.html)


class Navigation(unittest.TestCase):
    def test_the_header_carries_a_menu_not_an_event_name(self):
        html = page.render(FACTS)
        self.assertIn("<nav", html)
        for target in ("#desk", "#evidence", "#validation", "#method"):
            with self.subTest(target=target):
                self.assertIn(f'href="{target}"', html)
        self.assertNotIn("Bitget AI Base Camp", html)

    def test_the_footer_states_provenance_and_its_limits(self):
        html = page.render(FACTS)
        self.assertIn("none is typed", html)
        self.assertIn("Not advice", html)
