#!/usr/bin/env python3
"""Compare docs/X_POST.md against the record, right before posting.

The draft is the one artifact that cannot be corrected afterwards, and it is the
only one nothing checked. It sat for three days quoting "2,127 tokenized US
stocks, 1,967 snapshots, 6.1 bp open to 54.5 bp overnight" while the crawl had
moved the universe to 2,589, the sample to 2,658 and the spreads with it.

A unit test is the wrong shape for this: the crawl moves these figures every
twenty minutes, so pinning them would turn the suite red continuously and teach
everyone to ignore it. What matters is that the draft is true at the moment it
is pasted. So this is a command you run then.

It reads the committed pages and state/ only - no network, no rebuild - because
the crawl regenerates both from the same measurement.

Every OCCURRENCE is checked, not merely one. The first version asked whether the
right number appeared somewhere in the file, and a draft that carried the current
figure in its source table and a stale one in the tweet body passed it - which is
backwards, since the tweet body is the part that gets posted.

What it does not catch: a figure REMOVED from one draft while the others still
state it correctly. It checks the values that are there. A figure that disappears
from every draft is reported as GONE.

    python3 tools/check_post.py

Exit status is 1 if any figure in the draft disagrees with the record.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAFT = ROOT / "docs" / "X_POST.md"


def _text(page: str) -> str:
    raw = (ROOT / "docs" / page).read_text()
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def _phase_rows(evidence: str) -> dict[str, dict[str, float]]:
    """The phase table, read back out of the page that publishes it."""
    head = evidence.find("Market phase Listed 30d+")
    if head < 0:
        raise SystemExit("the evidence page no longer carries the phase table")
    rows = {}
    pattern = (r"(open|pre|post|overnight|weekend) ([\d.]+) bp ([\d.]+) bp "
               r"([\d.]+) bp ([\d.]+)x ([\d,]+)")
    for m in re.finditer(pattern, evidence[head:head + 1200]):
        rows[m.group(1)] = {
            "established": float(m.group(2)),
            "new": float(m.group(3)),
            "crypto": float(m.group(4)),
            "snapshots": int(m.group(6).replace(",", "")),
        }
    if "open" not in rows or "overnight" not in rows:
        raise SystemExit(f"phase table parsed as {sorted(rows)}")
    return rows


def expectations() -> list[tuple[str, list[str], str]]:
    """(what it is, every way the draft writes it, the value it must carry)."""
    index, evidence = _text("index.html"), _text("evidence.html")
    phase = _phase_rows(evidence)
    day, night = phase["open"], phase["overnight"]

    universe = json.loads((ROOT / "state" / "universe.json").read_text())
    stocks = universe["counts"]["stock"]

    manifest = [json.loads(line) for line in
                (ROOT / "state" / "manifest.jsonl").read_text().splitlines()
                if line.strip()]
    rows_m = sum(e.get("rows", 0) for e in manifest) / 1e6

    hub = json.loads((ROOT / "state" / "hub_crosscheck.json").read_text())["counts"]

    snaps = re.search(r"([\d,]+) snapshots", index)
    if not snaps:
        raise SystemExit("the landing page no longer states the sample size")

    excl = re.search(r"excludes (\d+) symbols", evidence)
    ratio = re.search(r"candle volume runs ([\d.]+)\u00d7 to ([\d.]+)\u00d7", evidence)

    out: list[tuple[str, list[str], str]] = [
        ("tokenized US stocks",
         [r"Bitget lists ([\d,]+) tokenized", r"\| ([\d,]+) tokenized US stocks"],
         f"{stocks:,}"),
        ("snapshots in the sample",
         [r"([\d,]+) snapshots"], snaps.group(1)),
        ("rows crawled",
         [r"([\d.]+)M rows"], f"{rows_m:.1f}"),
        ("spread while New York is open",
         [r"([\d.]+) bp spread while New York is open",
          r"spread you entered on was ([\d.]+) bp",
          r"\| ([\d.]+) bp open"],
         f"{day['established']:.1f}"),
        ("spread overnight",
         [r"\u2192 ([\d.]+) bp overnight", r"Right now it's ([\d.]+) bp"],
         f"{night['established']:.1f}"),
        ("overnight vs open",
         [r"bp overnight\. ([\d.]+)x", r"widen ([\d.]+)x vs market hours",
          r"Measured: ([\d.]+)x the daytime spread",
          r"overnight \(([\d.]+)\u00d7\)"],
         f"{night['established'] / day['established']:.1f}"),
        ("overnight, listed under 30 days",
         [r"Listed under 30 days: ([\d]+) bp", r"listed this month, ([\d]+) bp",
          r"\| ([\d]+) bp overnight"],
         f"{night['new']:.0f}"),
        ("crypto control, open",
         [r"same venue: ([\d.]+) \u2192", r"crypto ([\d.]+) \u2192",
          r"([\d.]+) bp open, [\d.]+ bp overnight"],
         f"{day['crypto']:.1f}"),
        ("crypto control, overnight",
         [r"same venue: [\d.]+ \u2192 ([\d.]+)\.",
          r"crypto [\d.]+ \u2192 ([\d.]+) ",
          r"[\d.]+ bp open, ([\d.]+) bp overnight"],
         f"{night['crypto']:.1f}"),
        ("crypto control ratio",
         [r"same engine: ([\d.]+)x", r"\(([\d.]+)\u00d7\) \| phase table, crypto"],
         f"{night['crypto'] / day['crypto']:.2f}"),
        ("Agent Hub, symbols compared",
         [r"([\d]+) of [\d]+ symbols could be priced",
          r"\| ([\d]+) of [\d]+ priced through the Agent Hub"],
         str(hub["agreed"])),
        ("Agent Hub, symbols asked",
         [r"[\d]+ of ([\d]+) symbols could be priced",
          r"\| [\d]+ of ([\d]+) priced through the Agent Hub"],
         str(hub["asked"])),
        ("Hub could not price",
         [r"The other ([\d]+) names return no two-sided book"],
         str(hub["unavailable"])),
    ]
    if excl:
        out.append(("symbols excluded from validation",
                    [r"([\d]+) symbols are excluded"], excl.group(1)))
    if ratio:
        out.append(("volume feeds disagree, low",
                    [r"candle volume runs ([\d.]+)\u00d7"], ratio.group(1)))
        out.append(("volume feeds disagree, high",
                    [r"candle volume runs [\d.]+\u00d7\u2013([\d.]+)\u00d7"],
                    ratio.group(2)))
    return out


def main() -> int:
    draft = DRAFT.read_text()
    bad = []
    print("Checking docs/X_POST.md against the committed record\n")
    for what, patterns, expected in expectations():
        found = [m for p in patterns for m in re.findall(p, draft)]
        if not found:
            bad.append((what, expected, "the draft no longer states it"))
            print(f"  [GONE ] {what}: expected {expected}")
            continue
        wrong = sorted({f for f in found if f != expected})
        mark = "ok " if not wrong else "STALE"
        print(f"  [{mark}] {what}: {expected} "
              f"({len(found)} mention{'s' if len(found) != 1 else ''})")
        if wrong:
            bad.append((what, expected, f"the draft says {', '.join(wrong)}"))
    if bad:
        print(f"\n{len(bad)} figure(s) in the draft disagree with the record:")
        for what, expected, why in bad:
            print(f"  - {what}: should be {expected}; {why}")
        print("\nDo not post until the draft says what the site says.")
        return 1
    print("\nEvery figure in the draft matches the published record, "
          "in every place it appears.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
