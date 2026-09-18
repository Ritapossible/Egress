"""Everything the page states, computed from the record.

No measured figure is ever typed into a template. A number that a human retyped
is a number that goes stale the moment the record moves, and nobody notices for
weeks. Every value the page shows comes from here, and here reads only what the
crawler wrote.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics as st
from collections import deque
from pathlib import Path

from . import config, exitcost, market, sessions, store, universe, validate

UTC = dt.timezone.utc


def spread_bp(row: dict) -> float | None:
    """Round-trip spread in basis points, or None where there is no market."""
    try:
        bid, ask = float(row["bid"] or 0), float(row["ask"] or 0)
    except (TypeError, ValueError, KeyError):
        return None
    if bid <= 0 or ask <= 0 or bid >= ask:
        return None
    return (ask - bid) / ((ask + bid) / 2) * 1e4


def touch_usdt(row: dict) -> float | None:
    """How much is quoted at the best bid, in USDT."""
    try:
        bid, size = float(row["bid"] or 0), float(row["bid_size"] or 0)
    except (TypeError, ValueError, KeyError):
        return None
    return bid * size if bid > 0 and size > 0 else None


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def by_snapshot(day: dt.date | None = None, root: Path | None = None) -> list[dict]:
    """One summary per completed snapshot: spreads and touch, split by type.

    `day` narrows to a single UTC day; omitting it reads the entire record.
    """
    root = root or config.STATE
    # No day given means the WHOLE record, not today's slice of it. Defaulting
    # to today emptied every table on the site at 00:00 UTC and left it empty
    # until the first snapshot of the new day landed, while the footer went on
    # reporting the full snapshot count from the manifest. See MEMORY.md.
    wanted = [day] if day else store.days(root)
    listed = universe.load(root)
    kinds = {s: r["type"] for s, r in listed.items()}
    launches = {s: int(r["launch_ms"]) for s, r in listed.items()
                if str(r.get("launch_ms") or "").isdigit()}

    # ONE DAY AT A TIME. Materialising the whole record at once cost 311 MB at
    # two days and was heading for a gigabyte by the end of the week; only the
    # per-snapshot summaries need to outlive the day they came from, and there
    # are a couple of hundred of those rather than a million rows.
    out = []
    for one in wanted:
        grouped: dict[int, list[dict]] = {}
        for row in store.read_day(one, root):
            grouped.setdefault(int(row["snap_ts"]), []).append(row)
        out.extend(_summarise(grouped, kinds, launches))
    return sorted(out, key=lambda r: r["snap_ts"])


# How long a name must have been listed before its spread is allowed into the
# headline medians.
#
# Measured 2026-09-18, and the reason this constant exists: Bitget listed 480
# tokenized stocks in one wave, and the cross-sectional overnight median jumped
# from 165 bp to 260 bp overnight. Nothing about the market changed. The new
# names alone sit at 636 bp overnight against 63 bp for names listed a month or
# more, so a median taken over "whatever is listed today" tracks the venue's
# listing calendar rather than its liquidity, and the published ratio moved
# 19x -> 21x -> 24x on that alone.
#
# Thirty days is a month of overnight windows: long enough that a name has been
# through the thing being measured. The cohort is decided per snapshot from the
# venue's own launchTime, so a name crosses into the headline on its own
# thirtieth day and nothing has to be re-dated by hand.
ESTABLISHED_DAYS = 30
_ESTABLISHED_MS = ESTABLISHED_DAYS * 86_400_000


def cohort(kind: str, snap_ts: int, launch_ms: int | None) -> str:
    """Which series a symbol's spread belongs to in one snapshot.

    Crypto is never split: the control has to stay the same population in every
    row or it stops being a control.
    """
    if kind != "stock":
        return kind
    if launch_ms is None:
        return "stock_recent"
    return ("stock_established" if snap_ts - launch_ms >= _ESTABLISHED_MS
            else "stock_recent")


SERIES = ("stock", "stock_established", "stock_recent", "crypto")


def _summarise(grouped: dict[int, list[dict]], kinds: dict[str, str],
               launches: dict[str, int] | None = None) -> list[dict]:
    """One summary per snapshot in a single day's rows."""
    out = []
    for snap_ts, batch in sorted(grouped.items()):
        at = dt.datetime.fromtimestamp(snap_ts / 1000, UTC)
        entry: dict = {"snap_ts": snap_ts, "at": at.isoformat(),
                       "phase": sessions.phase(at)}
        launch = launches or {}
        # "stock" stays the whole listed population so the split can be checked
        # against it; the two cohorts partition it.
        member = {
            s: ({"stock", cohort("stock", snap_ts, launch.get(s))}
                if k == "stock" else {k})
            for s, k in kinds.items()
        }
        for kind in SERIES:
            spreads = [s for r in batch if kind in member.get(r["symbol"], ())
                       if (s := spread_bp(r)) is not None]
            touches = [t for r in batch if kind in member.get(r["symbol"], ())
                       if (t := touch_usdt(r)) is not None]
            entry[kind] = {
                "quoted": len(spreads),
                "median_spread_bp": round(st.median(spreads), 1) if spreads else None,
                "p90_spread_bp": round(_percentile(spreads, 0.9), 1) if spreads else None,
                "median_touch_usdt": round(st.median(touches)) if touches else None,
            }
        out.append(entry)
    return out


def phase_table(snapshots: list[dict]) -> list[dict]:
    """Median of the per-snapshot medians, grouped by market phase.

    Reported with the snapshot count behind each row, because a phase seen once
    is an anecdote and the page has to say which it is showing.
    """
    buckets: dict[str, list[dict]] = {}
    for snap in snapshots:
        buckets.setdefault(snap["phase"], []).append(snap)
    rows = []
    for phase, group in buckets.items():
        row: dict = {"phase": phase, "snapshots": len(group)}
        for kind in SERIES:
            medians = [g[kind]["median_spread_bp"] for g in group
                       if g.get(kind, {}).get("median_spread_bp") is not None]
            row[kind] = round(st.median(medians), 1) if medians else None
        # The headline ratio is the established cohort against the control. The
        # all-names ratio is kept beside it so the composition effect is visible
        # rather than quietly corrected away.
        if row.get("stock_established") and row["crypto"]:
            row["ratio"] = round(row["stock_established"] / row["crypto"], 1)
        if row["stock"] and row["crypto"]:
            row["ratio_all"] = round(row["stock"] / row["crypto"], 1)
        rows.append(row)
    # Regime order, not alphabetical: a reader follows the trading day, and
    # "open, overnight, post, pre" reads like a sorting accident.
    order = {"open": 0, "pre": 1, "post": 2, "overnight": 3,
             "weekend": 4, "holiday": 5}
    return sorted(rows, key=lambda r: (order.get(r["phase"], 9), r["phase"]))


def worked_example(symbols: list[str], notional: float = 25_000.0) -> list[dict]:
    """Live exit quotes for a handful of names, spanning the liquidity range."""
    kinds = {s: r["type"] for s, r in universe.load().items()}
    out = []
    for symbol in symbols:
        try:
            quote = exitcost.for_symbol(symbol, notional)
        except (market.MarketUnavailable, ValueError) as exc:
            # A symbol the venue will not price is a row that says so, not a
            # missing row and not a crash. The page shows the gap.
            out.append({"symbol": symbol, "error": str(exc)[:80],
                        "kind": kinds.get(symbol, "unknown")})
            continue
        record = quote.to_record()
        record["kind"] = kinds.get(symbol, "unknown")
        record["floor"] = quote.exhausted or quote.source == "touch"
        out.append(record)
    return out


# A symbol's own recent spread history, per phase.
#
# KEEP is a bounded window, not the whole record: unbounded accumulation across
# ~2,200 symbols and a thousand snapshots is hundreds of megabytes, and the
# question being answered is "is this name quoting unusually wide RIGHT NOW",
# which is about recent behaviour rather than all of history.
#
# MIN_MARKS is the floor below which a percentile is noise dressed as a fact. A
# p50 from four observations is not a typical value, and publishing it would be
# the same sin as the cross-sectional median it replaces.
SYMBOL_MARK_KEEP = 96
SYMBOL_MARK_MIN = 12


def by_symbol_phase(root: Path | None = None, keep: int = SYMBOL_MARK_KEEP,
                    min_marks: int = SYMBOL_MARK_MIN) -> dict:
    """Each symbol's own recent spread distribution, by phase.

    This exists because the desk was comparing the wrong things. It divided a
    size-aware exit COST by a cross-sectional median SPREAD and called the
    result "10x cheaper" - two different quantities, and a comparison the
    evidence page explicitly forbids ("a median spread is not a cost; it is the
    price of the first share, not of the position"). It also flattered any
    liquid name, because the denominator included symbols where the requested
    size is unfillable at any displayed price: those contribute a wide spread,
    never a cost.

    The honest comparison is like for like and, better, about the name actually
    being asked about: this symbol's quote now against this symbol's own
    typical quote in this phase.
    """
    window: dict[tuple[str, str], deque] = {}
    phase_of: dict[int, str] = {}
    for day in store.days(root):
        for row in store.read_day(day, root):
            value = spread_bp(row)
            if value is None:
                continue
            # Phase is per snapshot, and there are ~2.2M rows: deriving it per
            # row costs a datetime and a holiday lookup each time.
            stamp = int(row["snap_ts"])
            phase = phase_of.get(stamp)
            if phase is None:
                phase = phase_of[stamp] = sessions.phase(
                    dt.datetime.fromtimestamp(stamp / 1000, UTC))
            key = (row["symbol"], phase)
            seen = window.get(key)
            if seen is None:
                seen = window[key] = deque(maxlen=keep)
            seen.append(value)

    out: dict[str, dict] = {}
    for (symbol, phase), values in window.items():
        if len(values) < min_marks:
            continue
        ordered = sorted(values)
        out.setdefault(symbol, {})[phase] = {
            "p50": round(_percentile(ordered, 0.5), 2),
            "p90": round(_percentile(ordered, 0.9), 2),
            "n": len(ordered),
        }
    return out


def feed_flags(validation: dict | None) -> dict:
    """Symbols the validation refused to score, keyed for the desk to read.

    The site names these on the validation page and then priced them on the
    desk without a word. A name this project has publicly called unreliable
    should say so where it is being used, not only where it is being audited.
    """
    out = {}
    for row in (validation or {}).get("excluded_detail") or []:
        symbol = row.get("symbol")
        if symbol:
            out[symbol] = {"ratio": row.get("feed_ratio"),
                           "reason": row.get("reason", "")}
    return out


def save_symbol_marks(root: Path | None = None,
                      marks: dict | None = None,
                      flags: dict | None = None) -> Path:
    """Write the per-symbol marks, never replacing a populated file with nothing.

    Same guard, and for the same reason, as save_benchmark: an empty file
    raises no error anywhere and silently removes the comparison from every
    answer on the live site.
    """
    root = root or config.STATE
    root.mkdir(parents=True, exist_ok=True)
    path = root / "symbol_marks.json"
    computed = by_symbol_phase(root) if marks is None else marks
    if not computed and path.exists():
        try:
            standing = json.loads(path.read_text()).get("symbols")
        except (OSError, ValueError):
            standing = None
        if standing:
            raise BenchmarkEmpty(
                f"computed no symbol marks; keeping the {len(standing)} "
                f"already in {path.name} rather than blanking the desk")
    path.write_text(json.dumps(
        {"generated": dt.datetime.now(UTC).isoformat(timespec="seconds"),
         "keep": keep_note(), "symbols": computed,
         "feed_flags": flags or {}},
        indent=1, sort_keys=True))
    return path


def keep_note() -> dict:
    """The window the marks were taken over, so the page can state it."""
    return {"observations": SYMBOL_MARK_KEEP, "minimum": SYMBOL_MARK_MIN}


def benchmark(snapshots: list[dict] | None = None) -> dict:
    """What a typical exit costs, per phase, so one answer can be put in scale.

    Written to disk at page-build time and read by the desk, because computing
    it per question would mean reading the whole record on every request. It is
    derived, never typed: the numbers here are the same ones the evidence page
    shows, and they move when the record moves.
    """
    rows = phase_table(snapshots if snapshots is not None else by_snapshot())
    return {
        "generated": dt.datetime.now(UTC).isoformat(timespec="seconds"),
        "phases": {r["phase"]: {"stock_median_bp": r["stock"],
                                "crypto_median_bp": r["crypto"],
                                "snapshots": r["snapshots"]}
                   for r in rows if r.get("stock")},
    }


class BenchmarkEmpty(RuntimeError):
    """Computed no phases where a populated benchmark already exists."""


def save_benchmark(root: Path | None = None,
                   snapshots: list[dict] | None = None) -> Path:
    """Write the benchmark, but never replace a populated one with nothing.

    The desk reads this file to judge an answer. An empty one does not produce
    an error anywhere - it silently removes the verdict and the comparison from
    every answer on the live site, which is the failure that is hardest to
    notice. One such write was observed and could not be reproduced, so the
    guard is on the consequence rather than on a cause nobody has identified.
    """
    root = root or config.STATE
    root.mkdir(parents=True, exist_ok=True)
    path = root / "benchmark.json"
    payload = benchmark(snapshots)
    if not payload["phases"] and path.exists():
        try:
            standing = json.loads(path.read_text()).get("phases")
        except (OSError, ValueError):
            standing = None
        if standing:
            raise BenchmarkEmpty(
                f"computed no phases; keeping the {len(standing)} already in "
                f"{path.name} rather than blanking the desk's comparison")
    path.write_text(json.dumps(payload, indent=1, sort_keys=True))
    return path


def build(symbols: list[str] | None = None) -> dict:
    """The whole fact set the page renders from."""
    snapshots = by_snapshot()
    counts = universe.counts(universe.load())
    # The listing is re-read on the crawler's own clock, not at page build, so
    # the page has to be able to say how old this count is rather than imply it
    # is as fresh as everything beside it.
    listed_at = universe.captured()
    latest = snapshots[-1] if snapshots else {}
    return {
        "generated": dt.datetime.now(UTC).isoformat(timespec="seconds"),
        "universe": counts,
        "listed_at": listed_at,
        "listed_total": sum(counts.values()),
        "coverage": store.coverage(),
        "latest": latest,
        "phases": phase_table(snapshots),
        "snapshots": snapshots,
        "examples": worked_example(symbols or [
            "RNVDAUSDT", "RTSLAUSDT", "RAAPLUSDT", "RSYKUSDT", "RPBRUSDT",
            "BTCUSDT",
        ]),
        "notional_usdt": 25_000.0,
        "validation": validate.run(),
    }
