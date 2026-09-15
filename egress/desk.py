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
    record = out["quote"]
    out["reading"] = _reading(out)
    if record.get("quotable"):
        verdict = _verdict(record["total_bp"], out["phase"], benchmark())
        out["verdict"] = verdict
        out["headline"] = _headline(record, verdict)
        out["context"] = _context(record, verdict, out["phase"])
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


# Where an exit sits against the median for its own market phase. The bands are
# a judgement about wording, not a measurement, so they are named here rather
# than buried in a formatter.
BANDS = ((0.5, "cheap"), (1.5, "about typical"), (4.0, "expensive"))

# Below this a saving rounds to 0 or 1 bp and is not worth the round
# trips, the timing risk, or the sentence.
WORTH_SPLITTING_BP = 2.0


def _verdict(total_bp: float, phase: str, marks: dict) -> dict:
    """One word for how this exit compares, and the figure behind it."""
    row = marks.get(phase) or {}
    median = row.get("stock_median_bp")
    if not median or median <= 0:
        return {"label": "", "median_bp": None, "ratio": None,
                "snapshots": row.get("snapshots")}
    ratio = total_bp / median
    label = "very expensive"
    for ceiling, word in BANDS:
        # Inclusive: exactly half the median cost is cheap, not "about typical".
        if ratio <= ceiling:
            label = word
            break
    return {"label": label, "median_bp": median, "ratio": round(ratio, 2),
            "snapshots": row.get("snapshots")}


def _context(quote: dict, verdict: dict, phase: str) -> str:
    """The comparison sentence, or nothing if there is no record to compare to."""
    if not verdict.get("label"):
        return ""
    median, ratio = verdict["median_bp"], verdict["ratio"]
    if ratio < 1:
        scale = f"about {1 / ratio:,.0f}x cheaper than"
    elif ratio < 1.5:
        scale = "in line with"
    else:
        scale = f"about {ratio:,.0f}x more than"
    return (f"That is {scale} the median tokenized stock in the same "
            f"{phase} conditions ({median:,.0f} bp across "
            f"{verdict['snapshots']:,} snapshots).")


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


def _headline(quote: dict, verdict: dict) -> str:
    """The first line: the number, the money, and what it means."""
    floor = ">" if quote.get("exhausted") or quote.get("source") == "touch" else ""
    label = f" - {verdict['label']}" if verdict.get("label") else ""
    return (f"{floor}{quote['total_bp']:,.0f} bp{label}. "
            f"About {floor}{quote['total_usdt']:,.0f} USDT to get out of "
            f"{quote['requested_usdt']:,.0f}.")


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
