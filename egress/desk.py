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

from . import exitcost, llm, market, sessions, universe

UTC = dt.timezone.utc
SLICE_CHOICES = (1, 4, 12)


def listed_symbols() -> dict[str, dict]:
    """The listed universe, from the record or straight from the venue.

    `universe.load()` returns {} when the file is absent - which on a
    deployment that did not ship `state/universe.json` would make EVERY valid
    ticker answer "not listed": a confident wrong answer, the one failure mode
    this project exists to avoid. So an empty load is treated as a missing
    file, not as an empty market, and the venue is asked directly.
    """
    stored = universe.load()
    if stored:
        return stored
    return universe.classify(market.instruments(quick=True))


def resolve(ticker: str, symbols: dict[str, dict] | None = None) -> str | None:
    """US ticker -> a listed tokenized-stock symbol, or None. Never invented."""
    listed = symbols if symbols is not None else listed_symbols()
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

    try:
        symbol = resolve(spec["ticker"], symbols)
    except market.MarketUnavailable as exc:
        out["error"] = ("the listed universe could not be read, so no ticker "
                        f"can be resolved right now: {exc.reason}")
        return out
    if not symbol:
        out["error"] = (f"{spec['ticker']} is not listed as a tokenized stock on "
                        f"this venue right now, so there is nothing to price.")
        return out
    out["symbol"] = symbol

    notional = spec["notional_usdt"]
    # ONE fetch for the whole answer. The quote, the plan and the max-exit
    # search must describe the same book, and a venue that will not answer is a
    # stated result rather than an exception - this function promises that.
    try:
        bids, asks, source = market.depth_or_touch(symbol, quick=True)
    except market.MarketUnavailable as exc:
        out["error"] = (f"the venue would not return a book for {symbol}: "
                        f"{exc.reason}")
        return out

    quote = exitcost.from_book(symbol, notional, bids, asks, source)
    out["quote"] = quote.to_record()

    if quote.reference and quote.reference > 0:
        out["max_exit_200bp"] = exitcost.max_exit(bids, asks, 200.0)
        out["plan"] = [exitcost.sliced(symbol, notional, n, bids, asks)
                       for n in SLICE_CHOICES]

    out["unverified"] = list(quote.unverified)
    out["reading"] = _reading(out)
    return out


def _reading(out: dict) -> str:
    """One plain sentence, built from the numbers rather than from the model."""
    quote = out.get("quote") or {}
    if not quote or not quote.get("quotable"):
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
