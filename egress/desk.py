"""The research desk: one question in, one answered exit plan out.

The flow is fixed and each step is visible in the answer:

    question -> reader compiles a spec -> ticker resolved to a LIVE symbol
             -> book fetched -> cost walked -> plan, with what it could not verify

The resolution step matters as much as the reader. A ticker only becomes a symbol
if that symbol is actually listed right now: selection from the live universe,
never generation. The model can say RTSLAUSDT all it likes; if the venue does not
list it, the desk says so instead of pricing a thing that does not exist.
"""
from __future__ import annotations

import datetime as dt

from . import exitcost, llm, sessions, universe

UTC = dt.timezone.utc
SLICE_CHOICES = (1, 4, 12)


def resolve(ticker: str, symbols: dict[str, dict] | None = None) -> str | None:
    """US ticker -> a listed tokenized-stock symbol, or None. Never invented."""
    listed = symbols if symbols is not None else universe.load()
    wanted = ticker.strip().upper()
    for candidate in (f"R{wanted}USDT", f"{wanted}USDT"):
        row = listed.get(candidate)
        if row and row.get("type") == "stock" and row.get("status") == "online":
            return candidate
    return None


def answer(question: str, symbols: dict[str, dict] | None = None) -> dict:
    """The whole desk. Every failure is a stated answer, never an exception."""
    now = dt.datetime.now(UTC)
    out: dict = {"question": question[:600], "at": now.isoformat(timespec="seconds"),
                 "phase": sessions.phase(now), "basis": "estimated"}

    try:
        spec = llm.compile_question(question)
    except llm.ReaderUnavailable as exc:
        out["error"] = f"could not read the question: {exc.reason}"
        return out

    out["spec"] = spec
    if not spec["ticker"]:
        out["error"] = ("no US stock ticker found in that question. Name one, "
                        "for example: what does leaving 40,000 USDT of TSLA cost?")
        return out

    symbol = resolve(spec["ticker"], symbols)
    if not symbol:
        out["error"] = (f"{spec['ticker']} is not listed as a tokenized stock on "
                        f"this venue right now, so there is nothing to price.")
        return out
    out["symbol"] = symbol

    notional = spec["notional_usdt"]
    quote = exitcost.for_symbol(symbol, notional)
    out["quote"] = quote.to_record()

    if quote.reference and quote.reference > 0:
        bids, asks, _ = _book(symbol)
        out["max_exit_200bp"] = exitcost.max_exit(bids, asks, 200.0)
        out["plan"] = [exitcost.sliced(symbol, notional, n, bids, asks)
                       for n in SLICE_CHOICES]

    out["unverified"] = list(quote.unverified)
    out["reading"] = _reading(out)
    return out


def _book(symbol: str) -> tuple[list, list, str]:
    """The book, or an empty one. A venue that will not answer is not a crash."""
    from . import market
    try:
        return market.depth_or_touch(symbol)
    except market.MarketUnavailable:
        return [], [], "none"


def _reading(out: dict) -> str:
    """One plain sentence, built from the numbers rather than from the model."""
    quote = out.get("quote") or {}
    if not quote or quote.get("total_bp") != quote.get("total_bp"):
        return "There is no two-sided market here, so no exit can be priced."
    floor = ">" if quote.get("exhausted") or quote.get("source") == "touch" else ""
    cost = f"{floor}{quote['total_bp']:,.0f} bp ({floor}{quote['total_usdt']:,.0f} USDT)"
    line = (f"Leaving {quote['requested_usdt']:,.0f} USDT of "
            f"{quote['symbol']} costs about {cost} in one clip, "
            f"with the {out['phase']} book as it stands.")
    if quote.get("source") == "touch":
        line += (" The venue returned no depth for this symbol, only a top-of-book "
                 "quote, so that is a floor and not an estimate.")
    return line
