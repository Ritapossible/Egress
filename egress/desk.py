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
import json
import time

from . import config, exitcost, llm, market, sessions, universe

UTC = dt.timezone.utc
SLICE_CHOICES = (1, 4, 12)

# Listings change slowly; a question does not need a fresh download.
UNIVERSE_TTL_S = 900
_UNIVERSE_CACHE: list = [None, 0.0]


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
    # Fallback path: cached, because re-downloading the whole instrument list
    # on every question would make a missing file expensive as well as wrong.
    now = time.monotonic()
    cached, at = _UNIVERSE_CACHE
    if cached and now - at < UNIVERSE_TTL_S:
        return cached
    fetched = universe.classify(market.instruments(quick=True))
    _UNIVERSE_CACHE[0], _UNIVERSE_CACHE[1] = fetched, now
    return fetched


def _listings(ticker: str, listed: dict[str, dict]) -> list[str]:
    """Every live tokenized-stock symbol this ticker could mean, best first.

    PRE* is the third form and it is not decoration: Bitget lists tokenized
    exposure to companies that are not publicly traded, and those carry no `r`
    prefix. OPAI exists only as PREOPAIUSDT, so without this the desk told a
    holder of a listed instrument that it was not listed - the confident wrong
    answer this project exists to avoid.
    """
    wanted = ticker.strip().upper()
    return [c for c in (f"R{wanted}USDT", f"{wanted}USDT", f"PRE{wanted}USDT")
            if (row := listed.get(c))
            and row.get("type") == "stock" and row.get("status") == "online"]


def resolve(ticker: str, symbols: dict[str, dict] | None = None) -> str | None:
    """US ticker -> a listed tokenized-stock symbol, or None. Never invented."""
    listed = symbols if symbols is not None else listed_symbols()
    found = _listings(ticker, listed)
    return found[0] if found else None


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
    # SPCX trades as both RSPCXUSDT and PRESPCXUSDT, and they are different
    # instruments at different costs. Picking one silently would be exactly the
    # unstated choice the rest of this project refuses to make.
    others = [s for s in _listings(spec["ticker"],
                                   symbols if symbols is not None
                                   else listed_symbols())
              if s != symbol]
    if others:
        out["also_listed"] = others
        out["note"] = (f"{spec['ticker']} has more than one live listing on this "
                       f"venue ({', '.join([symbol, *others])}). This answer "
                       f"prices {symbol}; the others are separate books and "
                       f"will not cost the same.")

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
    record = out["quote"]
    out["reading"] = _reading(out)
    if record.get("quotable"):
        verdict = _verdict(quote_spread_bp(bids, asks), out["phase"],
                           symbol, symbol_marks())
        out["verdict"] = verdict
        out["headline"] = _headline(record)
        out["context"] = _context(verdict, symbol)
        out["advice"] = _advice(out, record)
        out["depth_note"] = _depth_note(record)
    else:
        out["headline"] = "No two-sided market - this cannot be priced."
        out["context"] = ("The venue is not showing both a bid and an ask for "
                          "this symbol right now, so there is no mid to measure "
                          "an exit against.")
    return out


def benchmark(root=None) -> dict:
    """What a typical exit costs, per phase. Absent is fine - the desk just
    stops offering the comparison rather than inventing one."""
    path = (root or config.STATE) / "benchmark.json"
    try:
        return json.loads(path.read_text()).get("phases", {})
    except (OSError, ValueError):
        return {}


# Where a quote sits against THIS NAME'S own recent quotes in the same phase.
#
# What this replaced: the desk used to divide a size-aware exit COST by a
# cross-sectional median SPREAD and report "10x cheaper than the median
# tokenized stock". Those are different quantities, and the evidence page says
# so in as many words - a median spread is the price of the first share, not of
# the position. It also flattered every liquid name, because the denominator
# included symbols where the requested size is unfillable at any displayed
# price: those contribute a wide spread and never a cost at all.
#
# So the comparison is now like for like, and about the name actually asked
# about. The cost is reported on its own and divided by nothing.
BANDS = ((0.6, "tighter than usual"), (1.5, "about usual"),
         (4.0, "wider than usual"))
WIDEST = "far wider than usual"

# The desk enforces the same floor the marks are built with, rather than
# trusting the file. A p50 from four readings is noise wearing the costume of a
# fact, and publishing one would repeat the sin this comparison replaced.
# tests/test_desk.py asserts this stays equal to facts.SYMBOL_MARK_MIN, which is
# not imported here: the serverless function should not pull in the whole
# record-reading stack to learn one integer.
MIN_MARKS = 12

# Below this a saving rounds to 0 or 1 bp and is not worth the round
# trips, the timing risk, or the sentence.
WORTH_SPLITTING_BP = 2.0


def symbol_marks(root=None) -> dict:
    """Per-symbol, per-phase spread percentiles. Absent is fine.

    Without it the desk simply stops offering a comparison rather than
    inventing one, which is the same contract benchmark() has.
    """
    path = (root or config.STATE) / "symbol_marks.json"
    try:
        return json.loads(path.read_text()).get("symbols", {})
    except (OSError, ValueError):
        return {}


def quote_spread_bp(bids: list, asks: list) -> float | None:
    """The touch spread of the book just fetched, in basis points.

    This is the quantity the marks are made of, so it is the only thing that
    may be compared against them.
    """
    if not bids or not asks:
        return None
    bid, ask = float(bids[0][0]), float(asks[0][0])
    if bid <= 0 or ask <= 0 or ask <= bid:
        return None
    return (ask - bid) / ((ask + bid) / 2) * 1e4


def _verdict(spread_bp: float | None, phase: str, symbol: str,
             marks: dict) -> dict:
    """How this name is quoting against its own recent history in this phase."""
    row = (marks.get(symbol) or {}).get(phase) or {}
    typical, seen = row.get("p50"), row.get("n")
    out = {"basis": "this symbol's own recent spread, same phase",
           "phase": phase,
           "quote_spread_bp": round(spread_bp, 2) if spread_bp is not None else None,
           "p50_bp": typical, "p90_bp": row.get("p90"), "snapshots": seen,
           "label": "", "ratio": None}
    if (spread_bp is None or not typical or typical <= 0
            or not seen or seen < MIN_MARKS):
        return out
    ratio = spread_bp / typical
    label = WIDEST
    for ceiling, word in BANDS:
        if ratio <= ceiling:
            label = word
            break
    out["ratio"] = round(ratio, 2)
    out["label"] = label
    return out


def _context(verdict: dict, symbol: str) -> str:
    """The comparison sentence, or nothing when there is nothing to compare to.

    A name with too little history gets an explicit statement of that rather
    than silence: a new listing is the position most likely to be expensive to
    leave, so "we cannot say yet" is the answer that matters most there.
    """
    if not verdict.get("label"):
        if verdict.get("quote_spread_bp") is None:
            return ""
        return (f"There is not enough recorded history for {symbol} in the "
                f"{verdict['phase']} phase to say whether that quote is normal "
                f"for this name yet.")
    now, typical = verdict["quote_spread_bp"], verdict["p50_bp"]
    wide = verdict.get("p90_bp")
    tail = ""
    if wide and now > wide:
        tail = (" That is wider than nine in ten of the recent readings for "
                "this name in this phase.")
    return (f"The quote itself is {now:,.2f} bp right now. This name's own "
            f"{verdict['phase']} median is {typical:,.2f} bp across "
            f"{verdict['snapshots']:,} readings, so the spread is "
            f"{verdict['label']} for {symbol}.{tail}")


def _advice(out: dict, quote: dict) -> str:
    """Whether splitting the order is worth doing, from the numbers."""
    plan = [p for p in out.get("plan") or [] if p.get("quotable")]
    if not plan:
        return ""
    one = next((p for p in plan if p["slices"] == 1), None)
    best = min(plan, key=lambda p: p["best_case_bp"])
    if not one or best["slices"] == 1:
        return "Splitting the order into smaller ones does not help against this book."
    saving = one["worst_case_bp"] - best["best_case_bp"]
    if saving < WORTH_SPLITTING_BP:
        return (f"Splitting it up saves under {WORTH_SPLITTING_BP:,.0f} bp even "
                f"if the book fully refills, so it is not worth the effort "
                f"here.")
    return (f"Split into {best['slices']} orders and you might save up to "
            f"{saving:,.0f} bp - but only if the book refills in between, "
            f"which a snapshot cannot promise.")


def _depth_note(quote: dict) -> str:
    if quote.get("source") == "touch":
        return ("The venue showed no depth for this symbol, only a top-of-book "
                "quote, so this is a floor and the real cost is higher.")
    if quote.get("exhausted"):
        return ("The displayed book ran out before the position did, so this is "
                "a floor: the rest has no quoted price at all.")
    return ""


def _headline(quote: dict) -> str:
    """The first line: the number and the money, compared to nothing.

    It used to carry a one-word verdict - "17 bp - cheap" - earned by dividing
    this cost by a median spread. The word now sits with the quote, in the
    sentence underneath, where the thing it describes actually lives.
    """
    floor = ">" if quote.get("exhausted") or quote.get("source") == "touch" else ""
    fee = quote.get("fee_bp")
    split = (f" {quote.get('slippage_bp', 0):,.1f} bp of that is the book, "
             f"{fee:,.0f} bp the assumed taker fee." if fee else "")
    return (f"{floor}{quote['total_bp']:,.0f} bp to leave "
            f"{quote['requested_usdt']:,.0f} USDT - about "
            f"{floor}{quote['total_usdt']:,.0f} USDT.{split}")


def _reading(out: dict) -> str:
    """One plain sentence, built from the numbers rather than from the model.

    Kept alongside the structured verdict because anything calling the endpoint
    directly wants a sentence, not a panel.
    """
    quote = out.get("quote") or {}
    if not quote or not quote.get("quotable"):
        return "There is no two-sided market here, so no exit can be priced."
    floor = ">" if quote.get("exhausted") or quote.get("source") == "touch" else ""
    cost = f"{floor}{quote['total_bp']:,.0f} bp ({floor}{quote['total_usdt']:,.0f} USDT)"
    line = (f"Leaving {quote['requested_usdt']:,.0f} USDT of "
            f"{quote['symbol']} costs about {cost} in one clip, "
            f"with the {out['phase']} book as it stands.")
    note = _depth_note(quote)
    return f"{line} {note}".strip()
