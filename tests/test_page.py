"""The site must state the record, not a memory of it.

MEMORY.md rule 5: no measured figure is ever typed into a template. These tests
enforce it by perturbing the facts and checking the pages follow. They also hold
the multi-page structure together: every menu tab is its own file, and the
chrome is identical on all of them.
"""
from __future__ import annotations

import html
import json
import re
import sys
import unittest
from pathlib import Path
from typing import ClassVar

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

    def test_the_parts_sum_to_the_total_on_the_rendered_page(self):
        """Read off the built HTML, not off the helper.

        The first version of this test called `_breakdown` directly with counts
        from universe.json. It passed the moment the helper was written - while
        the published page still carried the old two-category line, because the
        page had not been regenerated yet. A test of a renderer that never
        renders proves the renderer compiles, nothing more.

        FACTS carries three categories summing to listed_total, so the old
        two-category line fails this by exactly the 2 it used to drop.
        """
        import html
        import re
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as out, \
                mock.patch.object(page.facts, "build", return_value=FACTS):
            page.write(Path(out))
            built = (Path(out) / "docs.html").read_text()

        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", built)))
        line = re.search(r"([\d,]+) listed instruments \(([^)]*)\)", text)
        self.assertIsNotNone(line, "the instrument sentence is not on the page")
        total = int(line.group(1).replace(",", ""))
        # ", " and not ",": the counts are thousands-separated, so splitting on
        # the comma alone turns "2,127 tokenized stocks" into 2 and 127.
        parts = [int(part.split()[0].replace(",", ""))
                 for part in line.group(2).split(", ")]
        self.assertEqual(sum(parts), total,
                         f"the page prints {total:,} but its parts sum to "
                         f"{sum(parts):,}: {line.group(2)!r}")

    def test_one_of_a_kind_is_singular(self):
        from egress.page import _breakdown
        self.assertIn("1 metal,", _breakdown({"metal": 1, "stock": 5}) + ",")

    def test_an_empty_universe_says_so_rather_than_printing_nothing(self):
        from egress.page import _breakdown
        self.assertEqual(_breakdown({}), "nothing listed")


class TheSkillsSectionMatchesTheProbe(unittest.TestCase):
    """The page must not claim more about a Skill than its record supports.

    The easy failure here is the one every hackathon page makes: naming an
    integration and leaving the result unshown, so a reader assumes it works.
    The numbers on the page come from state/signal.json or they are not on it.
    """

    RECORD: ClassVar[dict] = {
        "checked_at": "2026-09-21T09:56:59+00:00",
        "feed_count": 44, "equity_capable": ["cnbc"],
        "catalogs_answering": 3, "live_answering": 0,
        "results": [
            {"tool": "news_feed", "action": "sources", "kind": "catalog",
             "answered": True, "feeds": 44},
            {"tool": "news_feed", "action": "latest", "kind": "live",
             "answered": True, "articles": 0, "feeds_reporting": 44},
            {"tool": "crypto_price", "action": "price", "kind": "live",
             "answered": False, "reason": "ConnectTimeout"},
        ],
    }

    def rendered(self, record):
        import html as _h
        import re as _re

        from egress.page import _skills
        return _re.sub(r"\s+", " ", _h.unescape(_re.sub(r"<[^>]+>", " ",
                                                        _skills(record))))

    def test_the_counts_come_from_the_record(self):
        out = self.rendered(self.RECORD)
        self.assertIn("3 of its catalog calls answer", out)
        self.assertIn("0 of its live-data calls", out)
        self.assertIn("44 feeds", out)

    def test_the_equity_capable_feeds_are_named_not_counted(self):
        """"one feed could cover a stock" is a claim; naming it is checkable."""
        self.assertIn("cnbc", self.rendered(self.RECORD))

    def test_a_failed_call_shows_its_reason(self):
        """Asserted with a reason that appears nowhere else.

        The first version looked for "ConnectTimeout", which the prose above
        the table also names - so it passed with the row's reason removed
        entirely. A substring that the page hardcodes proves nothing about
        what the record rendered.
        """
        record = dict(self.RECORD)
        record["results"] = [dict(r) for r in self.RECORD["results"]]
        record["results"][-1]["reason"] = "upstream refused: EGRESS-PROBE-XYZ"
        self.assertIn("EGRESS-PROBE-XYZ", self.rendered(record))

    def test_every_probed_call_is_listed(self):
        out = self.rendered(self.RECORD)
        for row in self.RECORD["results"]:
            with self.subTest(tool=row["tool"], action=row["action"]):
                self.assertIn(row["action"], out)

    def test_no_record_means_no_claim(self):
        out = self.rendered(None)
        self.assertIn("has not run yet", out)
        for forbidden in ("44", "answer", "feeds reporting"):
            self.assertNotIn(f"{forbidden} feeds", out)

    def test_the_section_reaches_the_built_page(self):
        import html as _h
        import re as _re
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as out, \
                mock.patch.object(page.facts, "build", return_value=FACTS), \
                mock.patch.object(page.signal, "load", return_value=self.RECORD):
            page.write(Path(out))
            built = (Path(out) / "docs.html").read_text()
        text = _re.sub(r"\s+", " ", _h.unescape(_re.sub(r"<[^>]+>", " ", built)))
        self.assertIn("Bitget Skills", text)
        self.assertIn("equity_price_quote", text)
        self.assertIn("3 of its catalog calls answer", text)


class TheFrozenResearchTaskIsReadableWithoutJavaScript(unittest.TestCase):
    """The desk is the product and it is unreachable with scripts off.

    `/ask` is a 404, the homepage says it needs JavaScript and a configured
    reader, and the answer arrives from a POST. A judge browsing with scripts
    disabled never sees the thing being judged do its job. This section is the
    fix, so it has to actually contain the numbers - rendered from the captured
    file, never retyped into prose.
    """

    def frozen(self) -> dict:
        path = Path(__file__).resolve().parent.parent / "state" / "research_task.json"
        return json.loads(path.read_text())

    def test_every_captured_task_is_rendered(self):
        record = self.frozen()
        out = page.research_task(record)
        self.assertTrue(record["tasks"], "nothing was captured")
        for task in record["tasks"]:
            with self.subTest(task=task["kind"]):
                self.assertIn(html.escape(task["question"]), out)
                answer = task["answer"]
                headline = answer.get("headline") or answer.get("error")
                self.assertIn(html.escape(headline), out,
                              "the rendered task does not carry its own answer")

    def test_the_figures_come_from_the_capture_not_from_prose(self):
        record = self.frozen()
        out = page.research_task(record)
        for task in record["tasks"]:
            quote = (task["answer"].get("quote") or {})
            if not quote:
                continue
            with self.subTest(task=task["kind"]):
                self.assertIn(f'{quote["book_usdt"]:,.0f} USDT', out,
                              "the book depth on the page is not the captured one")
                self.assertIn(f'{quote["slippage_bp"]:,.2f} bp', out,
                              "the slippage on the page is not the captured one")

    def test_the_pair_covers_a_fill_and_a_failure_to_fill(self):
        """One worked example proves only the happy path. The thin name is
        there to show the desk refusing to quote a number it cannot stand
        behind, and it is the half a judge should be looking for."""
        kinds = {t["kind"] for t in self.frozen()["tasks"]}
        self.assertEqual(kinds, {"liquid", "thin"})
        thin = next(t for t in self.frozen()["tasks"] if t["kind"] == "thin")
        self.assertIn(">", thin["answer"]["headline"],
                      "the thin case does not degrade to a marked floor")

    def test_nothing_captured_says_so_rather_than_rendering_nothing(self):
        out = page.research_task(None)
        self.assertIn("freeze_task.py", out)
        self.assertNotIn("<dl>", out)

    def test_the_evidence_page_carries_the_task_and_the_caveat(self):
        built = (Path(__file__).resolve().parent.parent / "docs" / "evidence.html")
        text = built.read_text()
        self.assertIn("One research task, frozen", text)
        self.assertIn("What is not validated yet", text)
        self.assertIn("as a quote", text)
        self.assertIn("as a fill", text)


class TheUniverseCountSaysWhatItCounts(unittest.TestCase):
    """2,127 is the venue's own number, but it is reachable from exactly one
    endpoint and the obvious one does not carry the field. Anyone reconciling
    it against another source lands elsewhere and calls the headline inflated,
    so the query is stated on the page that prints the number."""

    def counts(self) -> dict:
        path = Path(__file__).resolve().parent.parent / "state" / "universe.json"
        return json.loads(path.read_text())["counts"]

    def test_the_definition_quotes_the_endpoint_that_carries_the_field(self):
        out = page.universe_definition(self.counts())
        self.assertIn("/api/v3/market/instruments", out)
        self.assertIn('symbolType', out)
        self.assertIn("/api/v2/spot/public/symbols", out)

    def test_the_stated_count_is_the_measured_count(self):
        counts = self.counts()
        out = page.universe_definition(counts)
        self.assertIn(f'{counts["stock"]:,} tokenized stocks', out,
                      "the definition does not quote the measured stock count")

    def test_the_heuristic_that_disagrees_is_named_with_its_number(self):
        """The prefix heuristic is the likely source of any rival count, and it
        is wrong in both directions. Saying which way, and by how much, is what
        makes this a reconciliation rather than an assertion."""
        out = page.universe_definition(self.counts())
        self.assertIn("2,150", out)
        self.assertIn("RLCUSDT", out)
        self.assertIn("PRESPCXUSDT", out)


class TheSubmissionDescriptionStaysHonest(unittest.TestCase):
    """PLAN.md spent four days claiming the demo and the research task were not
    started while both were shipped. This is the document a judge reads end to
    end, so the same drift here is worse.

    The figures in it are an explicitly timestamped snapshot - the crawl moves
    them every twenty minutes and pinning them would turn this file red on
    every commit. What is enforced is the part that is not allowed to drift:
    all six parts present, the snapshot labelled as one, and no claim that
    contradicts the measured record.
    """

    def doc(self) -> str:
        return (Path(__file__).resolve().parent.parent
                / "docs" / "SUBMISSION.md").read_text()

    def validation(self) -> dict:
        """From the rendered page, not from facts.build().

        Building the facts re-runs the crawl and the validation against the
        live venue - 85 seconds and a network dependency, inside a suite that
        is supposed to be neither. The built page already carries the numbers
        and is what a reader actually sees.
        """
        text = (Path(__file__).resolve().parent.parent
                / "docs" / "evidence.html").read_text()
        found = re.search(r"candle volume runs ([\d.]+)&times; to ([\d.]+)&times;",
                          text)
        self.assertIsNotNone(found, "the evidence page no longer states the range")
        return {"lo": float(found.group(1)), "hi": float(found.group(2))}

    def test_all_six_parts_are_present(self):
        doc = self.doc()
        for n, title in ((1, "Thesis"), (2, "Target user and product value"),
                         (3, "Validation data and key metrics"), (4, "Progress"),
                         (5, "Deliverables"), (6, "Take on AI trading")):
            with self.subTest(part=n):
                self.assertIn(f"## {n} · {title}", doc,
                              f"part {n} is missing from the description")

    def test_the_figures_are_labelled_as_a_snapshot(self):
        """Unlabelled numbers in a document nobody regenerates become lies by
        the second day. This one says so, and says which source wins."""
        doc = self.doc()
        self.assertIn("is a snapshot", doc)
        self.assertIn("the site is right and this file", doc)

    def test_the_limit_on_validation_is_stated_not_buried(self):
        """Scoring covers the three crypto controls and no tokenized stock. A
        judge who finds that themselves, after reading a confident thesis, has
        found something we hid."""
        doc = self.doc()
        self.assertIn("no tokenized stock at all", doc)
        self.assertIn("as a quote, not yet as a fill", doc)
        self.assertIn("No return claim is made", doc)

    def test_the_exclusion_ratios_match_the_validation_record(self):
        """These were published once as "646x to 5,902x" on an outside review's
        say-so. They are an order of magnitude smaller and measure something
        else. The document has to agree with the file."""
        measured = self.validation()
        doc = self.doc()

        # The bad figure is allowed on the page, but only where it is being
        # retracted. This project records corrections rather than deleting the
        # sentence that was wrong, so the test has to tell the two apart.
        for line in doc.splitlines():
            if "646" in line or "5,902" in line:
                self.assertIn("outside review gave", line,
                              "the discredited ratio appears as a live claim")

        # It must be the feed comparison, not a depth comparison.
        self.assertIn("24h turnover its own ticker reports", doc)

        # And the measured range must still be the order of magnitude the prose
        # describes. If the venue's feeds ever diverge by hundreds of times,
        # the wording stops being true and this should say so.
        self.assertLess(measured["hi"], 100,
                        "the measured ratios moved into the range the "
                        "discredited figure claimed; the prose needs re-checking")
        self.assertGreater(measured["lo"], 1,
                           "the feeds now agree, so the exclusion reason is stale")

    def test_the_x_post_is_still_flagged_as_outstanding(self):
        """It is an invalidation criterion. The moment this row quietly reads
        as done without a link, the submission looks complete and is not."""
        doc = self.doc()
        self.assertIn("#BitgetHackathon", doc)
        self.assertIn("@Bitget_AI", doc)
        self.assertTrue("⚠️" in doc or "fill in" in doc,
                        "the X post row no longer flags itself as outstanding")


class TheHubCrosscheckIsAnAdversaryNotALogo(unittest.TestCase):
    """The Agent Hub is easy to integrate dishonestly: route an existing REST
    call through it and claim a third Skill. That adds a logo and no
    information.

    What earns its place is using it against the existing path - same question,
    different SDK, same costing code - so the comparison can actually fail. So
    what is enforced here is that it *can* fail: that disagreement and
    unavailability are representable, reported, and not quietly folded into
    agreement.
    """

    def record(self) -> dict:
        path = (Path(__file__).resolve().parent.parent
                / "state" / "hub_crosscheck.json")
        return json.loads(path.read_text())

    def test_every_row_reaches_the_page(self):
        record = self.record()
        out = page.hub_crosscheck(record)
        self.assertTrue(record["rows"], "nothing was cross-checked")
        for row in record["rows"]:
            with self.subTest(symbol=row["symbol"]):
                self.assertIn(row["symbol"], out)

    def test_the_counts_on_the_page_are_the_counts_in_the_file(self):
        record = self.record()
        c = record["counts"]
        out = page.hub_crosscheck(record)
        self.assertIn(f'<b>{c["compared"]} of {c["asked"]} could be compared; '
                      f'{c["agreed"]} agree</b>', out,
                      "the page does not quote the measured comparison counts")

    def test_a_disagreement_is_shown_as_a_disagreement(self):
        """The one row that matters. If this ever renders as agreement, the
        cross-check has become decoration."""
        record = {"built_on": "2026-09-22T00:00:00+00:00", "notional_usdt": 25000.0,
                  "agree_within_bp": 0.5,
                  "counts": {"asked": 1, "compared": 1, "agreed": 0,
                             "disagreed": 1, "unavailable": 0},
                  "rows": [{"symbol": "RAAPLUSDT", "verdict": "disagree",
                            "ours_total_bp": 46.3, "hub_total_bp": 45.09,
                            "gap_bp": 1.21}]}
        out = page.hub_crosscheck(record)
        self.assertIn("disagree", out)
        self.assertIn("1.21 bp", out)
        self.assertIn("46.30 bp", out)
        self.assertIn("45.09 bp", out)

    def test_a_symbol_the_hub_cannot_price_says_why(self):
        """Two of the excluded names return no two-sided book from the Hub
        either. That is a second client finding the same thinness, and it is
        worth more than a blank cell."""
        record = {"built_on": "2026-09-22T00:00:00+00:00", "notional_usdt": 25000.0,
                  "agree_within_bp": 0.5,
                  "counts": {"asked": 1, "compared": 0, "agreed": 0,
                             "disagreed": 0, "unavailable": 1},
                  "rows": [{"symbol": "RSYKUSDT", "available": False,
                            "reason": "the Hub returned no two-sided book"}]}
        out = page.hub_crosscheck(record)
        self.assertIn("unavailable", out)
        self.assertIn("no two-sided book", out)

    def test_nothing_recorded_says_so(self):
        out = page.hub_crosscheck(None)
        self.assertIn("hub_crosscheck.py", out)
        self.assertNotIn("<table", out)

    def test_the_page_states_what_agreement_does_not_prove(self):
        """Two clients reading the same exchange inherit the same error. A
        cross-check presented as proof of correctness would be worse than none,
        because it would launder a shared mistake as confirmation."""
        built = (Path(__file__).resolve().parent.parent
                 / "docs" / "evidence.html").read_text()
        self.assertIn("The same book, read twice", built)
        self.assertIn("does not", built)
        self.assertIn("inherit the same error", built)
        self.assertIn("rule out", built)


class TheHubClientRefusesToGuess(unittest.TestCase):
    """Ballast's first cut at this CLI guessed the invocation and every part of
    it was wrong. These pin the shape that `bgc discover --tool market`
    actually returned, so a rewrite that goes back to guessing fails here."""

    def test_the_book_is_read_from_the_wrapped_payload(self):
        from unittest import mock

        from egress import hub
        data = {"a": [[378.49, 32.4], [378.59, 27.0]],
                "b": [[378.26, 38.88], [378.21, 69.48]]}
        with mock.patch.object(hub, "_run", return_value=data):
            bids, asks = hub.orderbook("RTSLAUSDT")
        self.assertEqual(asks[0], [378.49, 32.4])
        self.assertEqual(bids[0], [378.26, 38.88])

    def test_a_one_sided_book_is_refused_not_half_priced(self):
        from unittest import mock

        from egress import hub
        with mock.patch.object(hub, "_run",
                               return_value={"a": [[1.0, 1.0]], "b": []}), \
                self.assertRaises(hub.HubUnavailable) as caught:
            hub.orderbook("RTHINUSDT")
        self.assertIn("no two-sided book", caught.exception.reason)

    def test_an_unavailable_hub_is_never_recorded_as_agreement(self):
        """The failure mode that would make this worthless: a Hub that cannot
        answer being folded into the agreed column."""
        from unittest import mock

        from egress import hub
        with mock.patch.object(hub, "orderbook",
                               side_effect=hub.HubUnavailable("bgc is not on PATH")):
            out = hub.compare("RTSLAUSDT", 25_000.0, None)
        self.assertFalse(out["available"])
        self.assertNotIn("verdict", out)
        self.assertIn("not on PATH", out["reason"])

    def test_garbage_levels_are_dropped_not_priced(self):
        from egress import hub
        rows = [[378.49, 32.4], ["bad", 1], [0, 5], [10, 0], [1.0]]
        self.assertEqual(hub._levels(rows), [[378.49, 32.4]])

    def _compare(self, hub_bids, hub_asks, our_bids, our_asks, size=25_000.0):
        from unittest import mock

        from egress import exitcost, hub
        ours = exitcost.from_book("RTESTUSDT", size, our_bids, our_asks, "orderbook")
        with mock.patch.object(hub, "orderbook",
                               return_value=(hub_bids, hub_asks)):
            return hub.compare("RTESTUSDT", size, ours)

    def test_two_books_that_differ_are_reported_as_a_disagreement(self):
        """The property the whole cross-check rests on.

        Everything else here tested the renderer against a hand-built record,
        so relabelling every verdict "agree" inside compare() left the suite
        green - a cross-check that cannot report a difference is decoration.
        """
        thin = ([[100.0, 50.0], [90.0, 5000.0]], [[101.0, 5000.0]])
        deep = ([[100.0, 5000.0]], [[101.0, 5000.0]])
        out = self._compare(thin[0], thin[1], deep[0], deep[1])
        self.assertEqual(out["verdict"], "disagree",
                         "two materially different books were called agreement")
        self.assertGreater(out["gap_bp"], out["agree_within_bp"])

    def test_two_books_that_match_are_reported_as_agreement(self):
        same = ([[100.0, 5000.0]], [[101.0, 5000.0]])
        out = self._compare(same[0], same[1], same[0], same[1])
        self.assertEqual(out["verdict"], "agree")
        self.assertEqual(out["gap_bp"], 0.0)

    def test_the_threshold_is_the_only_thing_separating_the_two(self):
        """A gap just inside the tolerance is agreement, just outside is not.
        Pinned so the tolerance cannot be quietly widened until nothing ever
        disagrees."""
        from egress import hub
        self.assertGreater(hub.AGREE_BP, 0,
                           "a zero tolerance would call live-book drift a finding")
        self.assertLessEqual(hub.AGREE_BP, 2.0,
                             "the tolerance is wide enough to hide a real gap")


class TheReadmeClaimsMatchTheCode(unittest.TestCase):
    """The README is the first thing a judge reads and the last thing anyone
    regenerates. PLAN.md spent four days under-reporting this project; the
    README can just as easily over-report it.

    Every Skill it names has to be wired somewhere, and every Skill that is
    wired has to be named - a Skill table that drifts either way is worse than
    no table, because it is the part being scored.
    """

    def readme(self) -> str:
        return (Path(__file__).resolve().parent.parent / "README.md").read_text()

    def test_every_skill_the_readme_names_has_a_module_behind_it(self):
        readme = self.readme()
        for claim, module in (("bitget-mcp-server", "mcp.py"),
                              ("bitget-signal", "signal.py"),
                              ("Agent Hub CLI", "hub.py")):
            with self.subTest(skill=claim):
                self.assertIn(claim, readme, f"{claim} is not named in the README")
                path = Path(__file__).resolve().parent.parent / "egress" / module
                self.assertTrue(path.exists(),
                                f"the README claims {claim} but {module} is gone")

    def test_the_readme_names_the_module_that_reaches_each_skill(self):
        readme = self.readme()
        for module in ("egress/mcp.py", "egress/signal.py", "egress/hub.py"):
            with self.subTest(module=module):
                self.assertIn(module, readme,
                              f"{module} is wired but the README does not say where")

    def test_the_hub_is_not_described_as_a_wrapper(self):
        """The whole reason it earns a place is that it argues with the existing
        read. If that framing ever softens into "we also call the Hub", the
        integration has become a logo."""
        readme = self.readme()
        self.assertIn("adversary", readme)
        self.assertIn("not a wrapper", readme.lower())

    def test_the_readme_still_refuses_to_type_a_measurement(self):
        """Its own stated discipline: no figure typed into this file, because a
        number in a document goes stale the moment the record moves. The Skill
        section must not have smuggled one in."""
        readme = self.readme()
        self.assertIn("nothing in this README is a measurement", readme)
        # The only numbers allowed are the venue's own feed count and the fuse,
        # both of which are properties of the code rather than of the record.
        import re
        skills = readme[readme.index("## The Bitget Skills"):
                        readme.index("## Run it")]
        bad = [n for n in re.findall(r"\b\d+\.\d+\b", skills)]
        self.assertEqual(bad, [],
                         f"a measured figure was typed into the README: {bad}")
