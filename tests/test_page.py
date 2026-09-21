"""The site must state the record, not a memory of it.

MEMORY.md rule 5: no measured figure is ever typed into a template. These tests
enforce it by perturbing the facts and checking the pages follow. They also hold
the multi-page structure together: every menu tab is its own file, and the
chrome is identical on all of them.
"""
from __future__ import annotations

import re
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
        {"phase": "open", "snapshots": 5, "stock": 18.8, "stock_established": 18.8,
         "stock_recent": 44.0, "crypto": 11.3, "ratio": 1.7},
        {"phase": "overnight", "snapshots": 7, "stock": 158.0,
         "stock_established": 158.0, "stock_recent": 620.0, "crypto": 10.3,
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

FILES = [file for file, *_ in page.PAGES]


def render(name="index.html", facts=None):
    return page.render(name, facts or FACTS)


class EveryTabIsItsOwnPage(unittest.TestCase):
    def test_the_five_tabs_each_have_a_file(self):
        self.assertEqual(FILES, ["index.html", "evidence.html",
                                 "validation.html", "method.html", "docs.html"])

    def test_the_menu_is_the_same_on_every_page_and_links_to_files(self):
        for name in FILES:
            html = render(name)
            with self.subTest(page=name):
                for target in FILES:
                    self.assertIn(f'href="{target}"', html)

    def test_the_current_tab_is_marked_and_only_the_current_tab(self):
        for name in FILES:
            html = render(name)
            with self.subTest(page=name):
                self.assertEqual(html.count('aria-current="page"'), 1)
                self.assertIn(f'<a href="{name}" class="here"', html)

    def test_the_menu_opens_without_javascript(self):
        """A <details> disclosure is the whole mobile menu. No script."""
        html = render()
        self.assertIn('<details class="menu">', html)
        self.assertIn("<summary", html)

    def test_no_page_links_to_a_fragment_that_lives_on_another_page(self):
        """The bug this replaces: #evidence in the menu of a page without it."""
        for name in FILES:
            html = render(name)
            ids = set(re.findall(r'id="([^"]+)"', html))
            for frag in set(re.findall(r'href="#([^"]+)"', html)):
                with self.subTest(page=name, fragment=frag):
                    self.assertIn(frag, ids)

    def test_an_unknown_page_is_an_error_not_an_empty_file(self):
        with self.assertRaises(KeyError):
            page.render("nope.html", FACTS)


class RendersFromTheRecord(unittest.TestCase):
    def test_the_universe_count_comes_from_facts(self):
        html = render()
        self.assertIn("1,175", html)
        self.assertIn("584", html)

    def test_both_phases_are_shown_with_their_snapshot_counts(self):
        html = render("evidence.html")
        for fragment in ("18.8 bp", "158.0 bp", "11.3 bp", "15.3x"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)

    def test_a_floor_is_marked_as_a_floor(self):
        """A cost the book could not fully price must not read as exact."""
        html = render("method.html")
        self.assertIn("&gt;22 bp", html)
        self.assertIn("13 bp", html)

    def test_a_symbol_the_venue_would_not_price_is_shown_not_dropped(self):
        html = render("method.html")
        self.assertIn("RDEADUSDT", html)
        self.assertIn("not in the ticker feed", html)

    def test_touch_sourced_rows_say_so(self):
        self.assertIn("top of book only", render("method.html"))

    def test_the_method_page_declares_its_figures_estimated(self):
        self.assertIn("estimated, never observed", render("method.html"))

    def test_perturbing_the_facts_moves_the_page(self):
        """The guard against a number being typed into the template."""
        moved = render(facts={**FACTS, "universe": {"stock": 99, "crypto": 7}})
        self.assertIn("99", moved)
        self.assertNotIn("1,175", moved)

    def test_perturbing_the_facts_moves_the_evidence_page_too(self):
        other = {**FACTS, "phases": [
            {"phase": "open", "snapshots": 2, "stock": 4.4, "stock_established": 4.4,
             "stock_recent": 9.9, "crypto": 9.1,
             "ratio": 0.5}]}
        moved = render("evidence.html", other)
        self.assertIn("4.4 bp", moved)
        self.assertNotIn("158.0 bp", moved)

    def test_gap_count_is_singular_or_plural_correctly(self):
        one = render(facts={**FACTS,
                            "coverage": {**FACTS["coverage"],
                                         "gaps": [{"minutes": 60}]}})
        self.assertIn("Gap in the record", one)
        self.assertIn("Gaps in the record", render())

    def test_the_taker_fee_on_the_method_page_is_the_one_the_code_charges(self):
        from egress import exitcost
        self.assertIn(f"{exitcost.TAKER_FEE_BP:g} bp taker fee",
                      render("method.html"))

    def test_the_docs_state_the_record_size_from_the_record(self):
        html = render("docs.html")
        self.assertIn("21,132", html)
        self.assertIn("1,761", html)


class TheDocsPageIsStandard(unittest.TestCase):
    """A judge who has never seen the repo has to be able to reproduce a number."""

    def setUp(self):
        self.html = render("docs.html")

    def test_it_carries_the_sections_a_docs_page_is_expected_to_have(self):
        for slug, _label in page.DOC_SECTIONS:
            with self.subTest(section=slug):
                self.assertIn(f'id="{slug}"', self.html)
                self.assertIn(f'href="#{slug}"', self.html)

    def test_the_quickstart_is_runnable_not_prose(self):
        for command in ("git clone", "python -m egress.crawl --once",
                        "python -m egress.page"):
            with self.subTest(command=command):
                self.assertIn(command, self.html)

    def test_every_stored_column_is_documented(self):
        from egress import store
        for column in store.COLUMNS:
            with self.subTest(column=column):
                self.assertIn(f"<td class='sym'>{column}</td>", self.html)

    def test_the_endpoint_is_documented_with_its_method(self):
        self.assertIn("POST /api/ask", self.html)

    def test_limitations_are_on_the_page_not_only_in_the_repo(self):
        for limit in ("A quote is not a fill", "The record is short",
                      "Research only"):
            with self.subTest(limit=limit):
                self.assertIn(limit, self.html)


class StandsAlone(unittest.TestCase):
    def test_no_external_request_of_any_kind(self):
        """Files a judge can open offline. No CDN, no webfont, no tracker.

        `http://www.w3.org/2000/svg` is excluded deliberately: it is an XML
        namespace identifier, required on the inline favicon, and never fetched
        by anything. Matching it would be matching a string, not a request.
        """
        for name in FILES:
            html = render(name).replace("http://www.w3.org/2000/svg", "")
            for forbidden in ("http://", "fonts.googleapis", "cdn.",
                              "<iframe", "@import"):
                with self.subTest(page=name, forbidden=forbidden):
                    self.assertNotIn(forbidden, html)

    def test_the_favicon_is_inline_not_a_file_request(self):
        for name in FILES:
            with self.subTest(page=name):
                self.assertIn('rel="icon" href="data:image/svg+xml,',
                              render(name))

    def test_every_link_out_points_at_the_source_repository(self):
        for name in FILES:
            hosts = {re.match(r"https://([^/\"]+)", u).group(1)
                     for u in re.findall(r'https://[^"\s]+', render(name))}
            with self.subTest(page=name):
                self.assertEqual(hosts, {"github.com"})

    def test_the_only_script_is_the_desk_and_only_where_the_desk_is(self):
        """Inline script would force unsafe-inline into the CSP."""
        index = render()
        self.assertIn('<script src="desk.js"></script>', index)
        self.assertEqual(index.count("<script"), 1)
        for name in FILES[1:]:
            with self.subTest(page=name):
                self.assertEqual(render(name).count("<script"), 0)

    def test_every_page_is_responsive(self):
        for name in FILES:
            html = render(name)
            with self.subTest(page=name):
                self.assertIn('name="viewport"', html)
                self.assertIn("@media", html)

    def test_wide_tables_are_wrapped_so_they_scroll_rather_than_crush(self):
        """The mobile bug: a table column wrapping one word per line."""
        for name in ("evidence.html", "method.html", "docs.html"):
            html = render(name)
            with self.subTest(page=name):
                self.assertEqual(html.count('<table class="tbl">'),
                                 html.count('<div class="scroll">'))


class TheDesk(unittest.TestCase):
    """Track 3 is a research workbench, so there has to be somewhere to ask."""

    def setUp(self):
        self.html = render()

    def test_there_is_an_input_that_posts_to_the_endpoint(self):
        self.assertIn('id="ask"', self.html)
        self.assertIn('action="/api/ask"', self.html)
        self.assertIn('<input id="q"', self.html)

    def test_the_form_still_has_a_label_for_screen_readers(self):
        self.assertIn('for="q"', self.html)

    def test_the_answer_region_announces_itself(self):
        self.assertIn('aria-live="polite"', self.html)

    def test_the_page_says_what_needs_javascript_and_what_does_not(self):
        """Asserted on collapsed whitespace: a source line wrap is not a
        content change, and a test that breaks on one is a nuisance."""
        flat = " ".join(self.html.split())
        self.assertIn("needs JavaScript", flat)
        self.assertIn("nothing else on this site does", flat)


class TheDeskIsTheProduct(unittest.TestCase):
    """Track 3 is execution assistance. The thing to use comes first, and the
    landing page is not a table of contents for the menu above it."""

    @staticmethod
    def hero(html):
        start = html.index('<div class="hero">')
        return html[start:html.index('<div class="grid-panel">', start)]

    def test_the_ask_form_is_inside_the_hero(self):
        self.assertIn('id="ask"', self.hero(render()))

    def test_the_form_is_the_first_thing_a_visitor_can_act_on(self):
        html = render()
        body = html[html.index("<body>"):]
        self.assertLess(body.index('id="ask"'), body.index("</section>"))

    def test_the_hero_has_no_competing_call_to_action(self):
        """The old primary button sent the visitor away from the product."""
        hero = self.hero(render())
        self.assertNotIn('class="btn solid"', hero)
        self.assertNotIn("See the evidence", hero)

    def test_the_landing_page_does_not_restate_the_menu_as_cards(self):
        """Four cards describing four pages is a sitemap, not content."""
        html = render()
        self.assertNotIn('class="cards"', html)
        self.assertNotIn("Four pages", html)

    def test_the_landing_page_makes_one_argument_not_a_tour(self):
        html = render()
        self.assertEqual(html.count("<h2>"), 1)


class TheFinding(unittest.TestCase):
    """The landing page's single claim, and it comes from the record."""

    def test_both_phases_are_shown_with_their_crypto_control(self):
        html = render()
        for fragment in ("158", "19", "crypto control 10 bp",
                         "crypto control 11 bp"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, html)

    def test_the_headline_ratio_is_computed_not_typed(self):
        """158.0 / 18.8 is 8.4x, so the headline must say 8."""
        self.assertIn("quotes 8x wider", render())

    def test_perturbing_a_phase_moves_the_headline(self):
        other = {**FACTS, "phases": [
            {"phase": "open", "snapshots": 5, "stock": 10.0,
             "stock_established": 10.0, "crypto": 11.3},
            {"phase": "overnight", "snapshots": 7, "stock": 300.0,
             "stock_established": 300.0, "crypto": 10.3}]}
        moved = render(facts=other)
        self.assertIn("quotes 30x wider", moved)
        self.assertNotIn("quotes 8x wider", moved)

    def test_a_record_with_only_one_phase_omits_the_panel_entirely(self):
        """Half a comparison is worse than none."""
        one = {**FACTS, "phases": [
            {"phase": "open", "snapshots": 5, "stock": 18.8,
             "stock_established": 18.8, "crypto": 11.3}]}
        html = render(facts=one)
        self.assertNotIn('class="compare"', html)
        self.assertNotIn("wider once New York shuts", html)

    def test_a_weekend_record_stands_in_for_an_overnight_one(self):
        wk = {**FACTS, "phases": [
            {"phase": "open", "snapshots": 5, "stock": 18.8,
             "stock_established": 18.8, "crypto": 11.3},
            {"phase": "weekend", "snapshots": 9, "stock": 200.0,
             "stock_established": 200.0, "crypto": 10.1}]}
        html = render(facts=wk)
        self.assertIn('class="compare"', html)
        self.assertIn("weekend", html)


class Chrome(unittest.TestCase):
    def test_the_header_carries_a_menu_not_an_event_name(self):
        for name in FILES:
            html = render(name)
            with self.subTest(page=name):
                self.assertIn("<nav", html)
                self.assertNotIn("Bitget AI Base Camp", html)

    def test_the_footer_brand_carries_the_accent_not_the_label_grey(self):
        """Same accent as the Ask button, so the two read as one system."""
        html = render()
        self.assertIn('<h3 class="mark">Egress</h3>', html)
        self.assertIn(".foot-top h3.mark{color:var(--accent)}", html)
        self.assertIn(".ask button", html)

    def test_the_footer_states_provenance_and_its_limits_on_every_page(self):
        for name in FILES:
            html = render(name)
            with self.subTest(page=name):
                self.assertIn("None is typed", html)
                self.assertIn("Not advice", html)
                self.assertIn("MIT licensed", html)

    def test_every_page_has_exactly_one_h1(self):
        for name in FILES:
            with self.subTest(page=name):
                self.assertEqual(render(name).count("<h1>"), 1)

    def test_writing_the_site_emits_every_page_and_the_script(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(page.facts, "build", return_value=FACTS):
            out = Path(tmp)
            index = page.write(out)
            self.assertEqual(index.name, "index.html")
            for name in [*FILES, "desk.js"]:
                with self.subTest(file=name):
                    self.assertTrue((out / name).exists())


if __name__ == "__main__":
    unittest.main()


class TheInstrumentBreakdownAddsUp(unittest.TestCase):
    """The docs line read "2,710 listed instruments (2,127 tokenized stocks,
    581 crypto pairs)" while universe.json held stock 2,127, crypto 581 and
    metal 2. The total was right; the parenthetical was two short, because it
    named two categories by hand and the third had been added since.

    A reader who adds the numbers up finds the page disagreeing with itself,
    on a site whose entire argument is that its figures are checkable.
    """

    def test_every_category_is_named(self):
        from egress.page import _breakdown
        out = _breakdown({"stock": 2127, "crypto": 581, "metal": 2})
        for token in ("2,127", "581", "2 metals"):
            self.assertIn(token, out)

    def test_a_category_nobody_anticipated_still_appears(self):
        from egress.page import _breakdown
        self.assertIn("3 widgets", _breakdown({"stock": 10, "widget": 3}))

    def test_the_parts_sum_to_the_total_the_page_prints(self):
        import json
        from pathlib import Path

        from egress.page import _breakdown

        path = Path(__file__).resolve().parent.parent / "state" / "universe.json"
        counts = json.loads(path.read_text())["counts"]
        line = _breakdown(counts)
        printed = sum(int(part.split()[0].replace(",", ""))
                      for part in line.split(", "))
        self.assertEqual(printed, sum(counts.values()),
                         f"the breakdown {line!r} does not sum to the total")

    def test_one_of_a_kind_is_singular(self):
        from egress.page import _breakdown
        self.assertIn("1 metal,", _breakdown({"metal": 1, "stock": 5}) + ",")

    def test_an_empty_universe_says_so_rather_than_printing_nothing(self):
        from egress.page import _breakdown
        self.assertEqual(_breakdown({}), "nothing listed")
