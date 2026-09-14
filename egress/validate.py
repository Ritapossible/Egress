"""Does the displayed book predict what actually trades?

The estimator prices an exit from quotes. Quotes are promises. The check is to
compare them against prints: size resting at the touch when a five-minute bar
opened, against the volume that went through during it.

**The check refuses to run on a feed it cannot trust, and that is most of this
universe.** Before comparing anything, `feed_agreement` sums twenty-four hourly
bars and holds the total against the same symbol's rolling 24h turnover. For
crypto the two land within 2% of each other. For tokenized stocks they diverge by
a symbol-dependent factor measured between 6x and 16x - and base volume and quote
volume diverge by the SAME factor, so it is not a price or units error, and the
factor varies per symbol, so it is not a constant multiplier either.

Which of the two feeds is right cannot be determined from outside. So the
validation reports the disagreement and then excludes those symbols rather than
quietly averaging over a number it has just shown to be unreliable. A validation
that validates against bad data is worse than no validation, because it produces a
figure people trust.

**What the surviving comparison can and cannot show.** A ratio above 1 means more
traded than was ever displayed, so the book refilled - the estimator is
conservative there, and that direction has only one explanation. A ratio below 1
is ambiguous by construction: unconsumed size may have been withdrawn before
anyone could hit it, or may simply have gone unwanted. Idle liquidity and phantom
liquidity look identical from outside, and this data cannot separate them.
"""
from __future__ import annotations

import datetime as dt
import statistics as st
from pathlib import Path

from . import facts, market, sessions, store, universe

UTC = dt.timezone.utc
BAR_MS = 300_000

# How far the two volume feeds may differ before a symbol is untrustworthy.
# Crypto sits at 0.98; the stock side runs 6x and up, so the band is not delicate.
AGREE_LOW, AGREE_HIGH = 0.80, 1.25


def _bar_of(snap_ts: int) -> int:
    return (snap_ts // BAR_MS) * BAR_MS


def feed_agreement(symbol: str) -> dict:
    """Do the venue's candle volume and its 24h turnover describe one market?"""
    try:
        bars = market.candles(symbol, "1H", 24)
        row = market.ticker(symbol)
    except market.MarketUnavailable as exc:
        return {"symbol": symbol, "agrees": False, "reason": exc.reason}
    if len(bars) < 20:
        return {"symbol": symbol, "agrees": False,
                "reason": f"only {len(bars)} hourly bars available"}
    try:
        turnover = float(row.get("turnover24h") or 0)
    except (TypeError, ValueError):
        turnover = 0.0
    if turnover <= 0:
        return {"symbol": symbol, "agrees": False, "reason": "no 24h turnover"}
    summed = sum(b["quote_vol"] for b in bars)
    ratio = summed / turnover
    return {
        "symbol": symbol, "bars_24h_usdt": round(summed, 2),
        "ticker_24h_usdt": round(turnover, 2), "ratio": round(ratio, 3),
        "agrees": AGREE_LOW <= ratio <= AGREE_HIGH,
        "reason": "" if AGREE_LOW <= ratio <= AGREE_HIGH else
                  f"candle volume is {ratio:.1f}x the ticker's 24h turnover",
    }


def touch_by_bar(symbol: str, day: dt.date, root: Path | None = None) -> dict[int, float]:
    """{bar_start_ms: USDT resting at the best bid when that bar opened}."""
    out: dict[int, float] = {}
    for row in store.read_day(day, root):
        if row["symbol"] != symbol:
            continue
        value = facts.touch_usdt(row)
        if value is None:
            continue
        out.setdefault(_bar_of(int(row["snap_ts"])), value)
    return out


def for_symbol(symbol: str, day: dt.date | None = None,
               root: Path | None = None) -> dict:
    """Quoted touch against printed volume, bar by bar - if the feeds agree."""
    day = day or dt.datetime.now(UTC).date()
    agreement = feed_agreement(symbol)
    if not agreement.get("agrees"):
        return {"symbol": symbol, "bars": 0, "excluded": True,
                "feed_ratio": agreement.get("ratio"),
                "reason": agreement.get("reason", "feeds disagree")}

    quoted = touch_by_bar(symbol, day, root)
    if not quoted:
        return {"symbol": symbol, "bars": 0,
                "reason": "no recorded quotes for this symbol on this day"}
    try:
        bars = market.candles(symbol, "5m", 100)
    except market.MarketUnavailable as exc:
        return {"symbol": symbol, "bars": 0, "reason": exc.reason}

    paired = []
    for bar in bars:
        start = _bar_of(bar["ts"])
        touch = quoted.get(start)
        if touch is None or touch <= 0:
            continue
        at = dt.datetime.fromtimestamp(start / 1000, UTC)
        paired.append({"bar": start, "phase": sessions.phase(at),
                       "quoted_usdt": round(touch, 2),
                       "printed_usdt": round(bar["quote_vol"], 2),
                       "ratio": round(bar["quote_vol"] / touch, 3)})
    if not paired:
        return {"symbol": symbol, "bars": 0,
                "reason": "no bar overlapped a recorded quote"}
    ratios = [p["ratio"] for p in paired]
    return {"symbol": symbol, "bars": len(paired),
            "feed_ratio": agreement.get("ratio"),
            "median_ratio": round(st.median(ratios), 3),
            "min_ratio": round(min(ratios), 3), "max_ratio": round(max(ratios), 3),
            "bars_that_printed_nothing": sum(1 for p in paired
                                             if p["printed_usdt"] == 0),
            "pairs": paired}


def run(symbols: list[str] | None = None, day: dt.date | None = None,
        root: Path | None = None) -> dict:
    kinds = {s: r["type"] for s, r in universe.load(root).items()}
    symbols = symbols or ["RNVDAUSDT", "RTSLAUSDT", "RAAPLUSDT", "RMSFTUSDT",
                          "RSYKUSDT", "RPBRUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT"]
    results = [for_symbol(s, day, root) for s in symbols]
    scored = [r for r in results if r.get("bars")]
    excluded = [r for r in results if r.get("excluded")]

    all_pairs = [p for r in scored for p in r["pairs"]]
    by_phase = {}
    for phase in {p["phase"] for p in all_pairs}:
        vals = [p["ratio"] for p in all_pairs if p["phase"] == phase]
        by_phase[phase] = {"bars": len(vals),
                           "median_ratio": round(st.median(vals), 3)}

    return {
        "measured": dt.datetime.now(UTC).isoformat(timespec="seconds"),
        "symbols": len(results), "scored": len(scored), "excluded": len(excluded),
        "excluded_detail": [{"symbol": r["symbol"], "feed_ratio": r.get("feed_ratio"),
                             "reason": r["reason"]} for r in excluded],
        "excluded_kinds": sorted({kinds.get(r["symbol"], "unknown")
                                  for r in excluded}),
        "bars": len(all_pairs),
        "median_ratio": round(st.median([p["ratio"] for p in all_pairs]), 3)
                        if all_pairs else None,
        "by_phase": by_phase,
        "silent_bars": sum(1 for p in all_pairs if p["printed_usdt"] == 0),
        "per_symbol": [{k: v for k, v in r.items() if k != "pairs"} for r in results],
    }
