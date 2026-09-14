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

from . import config, exitcost, market, sessions, store, universe

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
    """One summary per completed snapshot: spreads and touch, split by type."""
    root = root or config.STATE
    day = day or dt.datetime.now(UTC).date()
    rows = store.read_day(day, root)
    kinds = {s: r["type"] for s, r in universe.load(root).items()}

    grouped: dict[int, list[dict]] = {}
    for row in rows:
        grouped.setdefault(int(row["snap_ts"]), []).append(row)

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
    }


def save(root: Path | None = None) -> Path:
    root = root or config.STATE
    root.mkdir(parents=True, exist_ok=True)
    path = root / "facts.json"
    path.write_text(json.dumps(build(), indent=1, sort_keys=True))
    return path
