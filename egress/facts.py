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
    kinds = {s: r["type"] for s, r in universe.load(root).items()}

    # ONE DAY AT A TIME. Materialising the whole record at once cost 311 MB at
    # two days and was heading for a gigabyte by the end of the week; only the
    # per-snapshot summaries need to outlive the day they came from, and there
    # are a couple of hundred of those rather than a million rows.
    out = []
    for one in wanted:
        grouped: dict[int, list[dict]] = {}
        for row in store.read_day(one, root):
            grouped.setdefault(int(row["snap_ts"]), []).append(row)
        out.extend(_summarise(grouped, kinds))
    return sorted(out, key=lambda r: r["snap_ts"])


def _summarise(grouped: dict[int, list[dict]], kinds: dict[str, str]) -> list[dict]:
    """One summary per snapshot in a single day's rows."""
    out = []
    for snap_ts, batch in sorted(grouped.items()):
        at = dt.datetime.fromtimestamp(snap_ts / 1000, UTC)
        entry: dict = {"snap_ts": snap_ts, "at": at.isoformat(),
                       "phase": sessions.phase(at)}
        for kind in ("stock", "crypto"):
            spreads = [s for r in batch if kinds.get(r["symbol"]) == kind
                       if (s := spread_bp(r)) is not None]
            touches = [t for r in batch if kinds.get(r["symbol"]) == kind
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
        for kind in ("stock", "crypto"):
            medians = [g[kind]["median_spread_bp"] for g in group
                       if g[kind]["median_spread_bp"] is not None]
            row[kind] = round(st.median(medians), 1) if medians else None
        if row["stock"] and row["crypto"]:
            row["ratio"] = round(row["stock"] / row["crypto"], 1)
        rows.append(row)
    return sorted(rows, key=lambda r: r["phase"])


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
    latest = snapshots[-1] if snapshots else {}
    return {
        "generated": dt.datetime.now(UTC).isoformat(timespec="seconds"),
        "universe": counts,
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
