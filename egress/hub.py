"""A second, independent read of the same order book, through the Bitget Agent Hub.

WHY THIS EXISTS. Egress's largest stated limit is that two of the venue's own
volume feeds disagree about the liquid names - candle volume runs roughly 8x to
20x the 24h turnover its own ticker reports for the same symbol - and from
outside there is no way to say which one is right. Six symbols are excluded from
validation for exactly that reason.

A project whose whole argument is "the venue's own numbers do not always agree"
should not then read the book through one client and call it settled. The Agent
Hub CLI reaches the same exchange over a different SDK, a different process and
a different code path. Asking it the same question and comparing the answers is
the cheapest real check available: if two independent clients walk the same book
to the same cost, that cost is a property of the market rather than of our HTTP
layer.

IT IS NOT A WRAPPER. The temptation with the Hub is to route the existing REST
call through it and claim an integration. That would add a logo and no
information. This does the opposite: it keeps the existing path exactly as it
is and uses the Hub as an adversary to it, priced by the same `exitcost` code so
that any difference in the answer is a difference in the book and not in the
arithmetic.

CREDENTIALS. None. `bgc discover --tool market` reports `auth: public` and the
market domain is documented as "no credentials required"; verified on 2026-09-22
by calling `orderbook` for RTSLAUSDT with the Bitget key variables unset.

THE INVOCATION IS DISCOVERED, NOT GUESSED. Ballast's first cut at this CLI
guessed `trade place-order --notional` and every part of it was wrong. The call
below came from `bgc discover --tool market`:

    bgc market --action orderbook --category SPOT --symbol RTSLAUSDT --limit 5

and the payload arrives wrapped - the book is under `data`, with asks at `a`,
bids at `b`, each level a [price, size] pair of numbers.

    python3 -m egress.hub RTSLAUSDT        # compare both reads of one symbol
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

from . import exitcost

BGC_BIN = "bgc"
TIMEOUT_S = 25
CATEGORY = "SPOT"
# Deep enough that the comparison is about the book rather than about the first
# level, bounded so one symbol is one quick call.
DEPTH = 50

# A cost difference under this is the two reads landing on different
# milliseconds of a live book, not a disagreement about it.
AGREE_BP = 0.5


class HubUnavailable(RuntimeError):
    """The Hub could not be asked. Never silently treated as agreement."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def installed() -> bool:
    return shutil.which(BGC_BIN) is not None


def _run(args: list[str]) -> dict:
    if not installed():
        raise HubUnavailable("bgc is not on PATH")
    try:
        proc = subprocess.run([BGC_BIN, *args], capture_output=True, text=True,
                              timeout=TIMEOUT_S,
                              env={**os.environ, "NO_COLOR": "1"})
    except subprocess.TimeoutExpired:
        raise HubUnavailable(f"bgc did not answer in {TIMEOUT_S}s") from None
    except OSError as exc:
        raise HubUnavailable(f"{type(exc).__name__}: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise HubUnavailable(f"bgc exit {proc.returncode}: "
                             f"{detail[0][:160] if detail else 'no output'}")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise HubUnavailable(f"bgc returned unparseable output: {exc}") from exc
    data = payload.get("data")
    if not isinstance(data, dict):
        raise HubUnavailable("bgc response carried no data object")
    return data


def _levels(rows: object) -> list[list[float]]:
    out: list[list[float]] = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            try:
                price, size = float(row[0]), float(row[1])
            except (TypeError, ValueError):
                continue
            if price > 0 and size > 0:
                out.append([price, size])
    return out


def orderbook(symbol: str, depth: int = DEPTH) -> tuple[list, list]:
    """(bids, asks) for one symbol, through the Hub. Raises HubUnavailable."""
    data = _run(["market", "--action", "orderbook", "--category", CATEGORY,
                 "--symbol", symbol, "--limit", str(depth)])
    bids, asks = _levels(data.get("b")), _levels(data.get("a"))
    if not bids or not asks:
        raise HubUnavailable(f"the Hub returned no two-sided book for {symbol}")
    return bids, asks


def compare(symbol: str, notional_usdt: float,
            ours: exitcost.ExitQuote | None = None) -> dict:
    """Price the same exit through both clients and report the difference.

    `ours` is the quote the rest of the system already computed, so the two are
    the same question rather than two questions that happen to rhyme. Both are
    priced by `exitcost`, so any gap is the book and not the arithmetic.
    """
    out: dict = {"symbol": symbol, "notional_usdt": notional_usdt,
                 "source": "bitget-agent-hub", "agree_within_bp": AGREE_BP}
    try:
        bids, asks = orderbook(symbol)
    except HubUnavailable as exc:
        out.update(available=False, reason=exc.reason)
        return out

    theirs = exitcost.from_book(symbol, notional_usdt, bids, asks, "orderbook")
    out.update(available=True, hub_total_bp=exitcost.jsonable(theirs.total_bp),
               hub_levels=theirs.levels_used,
               hub_filled_usdt=exitcost.jsonable(theirs.filled_usdt))
    if ours is None or not exitcost.quotable(ours.total_bp) \
            or not exitcost.quotable(theirs.total_bp):
        out["verdict"] = "not compared"
        return out

    gap = abs(float(theirs.total_bp) - float(ours.total_bp))
    out.update(ours_total_bp=exitcost.jsonable(ours.total_bp),
               gap_bp=round(gap, 2),
               verdict="agree" if gap <= AGREE_BP else "disagree")
    return out


if __name__ == "__main__":
    import sys

    from . import market

    sym = sys.argv[1] if len(sys.argv) > 1 else "RTSLAUSDT"
    size = float(sys.argv[2]) if len(sys.argv) > 2 else 40_000.0
    bids, asks, source = market.depth_or_touch(sym)
    mine = exitcost.from_book(sym, size, bids, asks, source)
    result = compare(sym, size, mine)
    print(json.dumps(result, indent=1))
