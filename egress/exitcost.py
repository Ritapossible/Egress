"""What it costs to leave a position, measured against the book that exists.

The question this answers is not "what is it worth" but "what would I actually
receive". Those differ by the spread, by how far down the book the order reaches,
and by the fee - and for most of the 1,175 listed tokenized stocks they differ by
a great deal more than their holders expect.

Three decisions worth stating, because each one could have been made dishonestly:

**The reference is the mid, not the best bid.** Crossing the spread is a real cost
that the seller pays. Quoting against the bid would hide half of it, and on a name
whose spread is 1,485 bp - the p90 of this universe with the US market shut - that
is the entire number.

**Running out of book is a result, not an error.** Most of this universe cannot
absorb a serious position at any displayed price. `exhausted` says so, `filled_usdt`
says how far it got, and nothing is extrapolated past the last level. A tool that
raised here would be hiding its most important finding.

**Slicing returns bounds, never a point estimate.** Splitting an order over time is
only cheaper if the book refills, and whether it refills is precisely what a
snapshot cannot see. So both ends are computed - full replenishment and none - and
the honest answer is stated as the interval between them. The crawl is what will
eventually narrow it.

Every figure here is `estimated`. A displayed quote is not a fill: size can be
withdrawn, and a real order moves the book it is measuring.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field, replace

from . import market

UTC = dt.timezone.utc

# Bitget spot taker, in basis points. An ASSUMPTION, not a measurement: fee tiers
# are account-specific and this project holds no credentials to read them. Stated
# here so it can be overridden and so no reader mistakes it for an observation.
TAKER_FEE_BP = 10.0

Level = tuple[float, float]          # (price, size in base units)


def quotable(value: float | None) -> bool:
    """False for None, NaN and infinity - the three ways a cost can be absent."""
    return value is not None and math.isfinite(value)


def jsonable(value: float | None) -> float | None:
    """A float JSON can actually carry, or None. Never NaN, never infinity."""
    return value if quotable(value) else None


@dataclass(frozen=True)
class ExitQuote:
    """One estimate of leaving one position. All costs in basis points."""

    symbol: str
    side: str                        # "sell" to exit a long, "buy" to exit a short
    requested_usdt: float
    filled_usdt: float
    quantity: float
    vwap: float
    reference: float                 # mid at the time of the quote
    slippage_bp: float
    fee_bp: float
    levels_used: int
    book_usdt: float                 # everything displayed on that side
    exhausted: bool
    at: dt.datetime
    source: str = "orderbook"
    unverified: list[str] = field(default_factory=list)

    @property
    def total_bp(self) -> float:
        return round(self.slippage_bp + self.fee_bp, 2)

    @property
    def total_usdt(self) -> float:
        return round(self.requested_usdt * self.total_bp / 1e4, 2)

    def to_record(self) -> dict:
        """A JSON-safe view. Unquotable reads as null, never as NaN.

        `NaN` is a valid Python float and an INVALID JSON token: `json.dumps`
        emits a bare `NaN` that every conforming parser rejects, so a quote the
        book could not price used to reach the browser as a parse error rather
        than as the honest answer the desk had already computed.
        """
        return {
            "symbol": self.symbol, "side": self.side,
            "requested_usdt": round(self.requested_usdt, 2),
            "filled_usdt": round(self.filled_usdt, 2),
            "quantity": round(self.quantity, 8),
            "vwap": self.vwap, "reference": self.reference,
            "slippage_bp": jsonable(self.slippage_bp), "fee_bp": self.fee_bp,
            "total_bp": jsonable(self.total_bp),
            "total_usdt": jsonable(self.total_usdt),
            "quotable": quotable(self.total_bp),
            "levels_used": self.levels_used, "book_usdt": round(self.book_usdt, 2),
            "exhausted": self.exhausted, "source": self.source,
            "at": self.at.isoformat(),
            "basis": "estimated", "unverified": list(self.unverified),
        }


def mid_price(bids: list[Level], asks: list[Level]) -> float | None:
    """None when either side is empty or the book is crossed - both are real."""
    if not bids or not asks:
        return None
    best_bid, best_ask = bids[0][0], asks[0][0]
    if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
        return None
    return (best_bid + best_ask) / 2


def walk(levels: list[Level], quantity: float) -> tuple[float, float, int]:
    """Consume `quantity` base units. Returns (proceeds, filled_qty, levels_used).

    Stops at the end of the displayed book rather than extrapolating.
    """
    proceeds = filled = 0.0
    used = 0
    for price, size in levels:
        if filled >= quantity:
            break
        if price <= 0 or size <= 0:
            continue
        take = min(size, quantity - filled)
        proceeds += take * price
        filled += take
        used += 1
    return proceeds, filled, used


def quote(symbol: str, notional_usdt: float, bids: list[Level], asks: list[Level],
          fee_bp: float = TAKER_FEE_BP, side: str = "sell",
          at: dt.datetime | None = None) -> ExitQuote:
    """Cost of exiting `notional_usdt` of `symbol`, valued at the mid."""
    if notional_usdt <= 0:
        raise ValueError("notional must be positive")
    at = at or dt.datetime.now(UTC)
    unverified = [
        "displayed size is not guaranteed - quotes can be withdrawn before a fill",
        "a real order moves the book this is measured against",
        f"taker fee assumed at {fee_bp:.1f} bp; account tiers are not readable",
    ]

    reference = mid_price(bids, asks)
    if reference is None:
        return ExitQuote(
            symbol, side, notional_usdt, 0.0, 0.0, 0.0, 0.0, float("nan"),
            fee_bp, 0, 0.0, True, at,
            unverified=[*unverified,
                        "no two-sided market: cost is unquotable"])

    book = bids if side == "sell" else asks
    book_usdt = sum(p * q for p, q in book if p > 0 and q > 0)
    wanted_qty = notional_usdt / reference
    proceeds, filled_qty, used = walk(book, wanted_qty)

    if filled_qty <= 0:
        return ExitQuote(
            symbol, side, notional_usdt, 0.0, 0.0, 0.0, reference, float("nan"),
            fee_bp, 0, book_usdt, True, at,
            unverified=[*unverified,
                        "no displayed size on the exit side: cost is unquotable"])

    vwap = proceeds / filled_qty
    slippage = (reference - vwap) / reference * 1e4
    if side == "buy":
        slippage = -slippage
    exhausted = filled_qty < wanted_qty * 0.9999
    if exhausted:
        unverified.append(
            f"the displayed book absorbed only {proceeds / notional_usdt:.1%} "
            f"of this position; the rest has no quoted price")
    return ExitQuote(
        symbol=symbol, side=side, requested_usdt=notional_usdt,
        filled_usdt=round(proceeds, 6), quantity=filled_qty,
        vwap=round(vwap, 8), reference=round(reference, 8),
        slippage_bp=round(slippage, 2), fee_bp=fee_bp, levels_used=used,
        book_usdt=book_usdt, exhausted=exhausted, at=at, unverified=unverified)


def for_symbol(symbol: str, notional_usdt: float, depth: int = 150,
               fee_bp: float = TAKER_FEE_BP) -> ExitQuote:
    """Fetch the best available view of the book and quote against it.

    Falls back to the ticker's touch when the depth endpoint returns nothing but
    a quote exists, and says so - an unquotable book and an unreported one are
    different facts and must never render as the same number.
    """
    bids, asks, source = market.depth_or_touch(symbol, depth)
    return from_book(symbol, notional_usdt, bids, asks, source, fee_bp)


def from_book(symbol: str, notional_usdt: float, bids: list[Level],
              asks: list[Level], source: str,
              fee_bp: float = TAKER_FEE_BP) -> ExitQuote:
    """Quote against a book the caller already fetched.

    Exists so one question costs one round trip: the desk needs the same book
    for the quote, the slicing plan and the max-exit search, and fetching it
    twice let those three describe two different moments of the market.
    """
    result = quote(symbol, notional_usdt, bids, asks, fee_bp)
    extra = list(result.unverified)
    if source == "touch":
        extra.append(
            "the venue returned no depth for this symbol, only a top-of-book "
            "quote; everything below the touch is UNKNOWN, not absent - this is "
            "a floor on the cost, not an estimate of it")
    elif source == "none":
        extra.append("the venue returned neither depth nor a quote for this symbol")
    return replace(result, source=source, unverified=extra)


def max_exit(bids: list[Level], asks: list[Level], budget_bp: float,
             fee_bp: float = TAKER_FEE_BP, tolerance_usdt: float = 1.0) -> float:
    """Largest position exitable within `budget_bp`, in USDT.

    The inverse question, and usually the more useful one: not "what does this
    cost" but "how much can I actually get out of". Bisection, because cost is
    monotonic in size as the order eats deeper into the book.
    """
    reference = mid_price(bids, asks)
    if reference is None or budget_bp <= fee_bp:
        return 0.0
    ceiling = sum(p * q for p, q in bids if p > 0 and q > 0)
    if ceiling <= 0:
        return 0.0
    if quote("", ceiling, bids, asks, fee_bp).total_bp <= budget_bp:
        return round(ceiling, 2)

    low, high = 0.0, ceiling
    while high - low > tolerance_usdt:
        mid = (low + high) / 2
        if quote("", mid, bids, asks, fee_bp).total_bp <= budget_bp:
            low = mid
        else:
            high = mid
    return round(low, 2)


def sliced(symbol: str, notional_usdt: float, slices: int,
           bids: list[Level], asks: list[Level],
           fee_bp: float = TAKER_FEE_BP) -> dict:
    """Cost of exiting in `slices` clips, as an interval, never a point.

    Lower bound assumes the book fully refills between clips; upper bound assumes
    it never does, which is the same as one clip. The truth sits between, and a
    snapshot cannot say where - only a record of how this book behaves over time
    can, which is what the crawl is accumulating.
    """
    if slices < 1:
        raise ValueError("slices must be at least 1")
    one = quote(symbol, notional_usdt, bids, asks, fee_bp)
    per = quote(symbol, notional_usdt / slices, bids, asks, fee_bp)
    # Every NaN comparison is False, so sorted() would silently keep input order
    # and could report the worst case as the best one.
    ends = [v for v in (per.total_bp, one.total_bp) if quotable(v)]
    best, worst = (min(ends), max(ends)) if len(ends) == 2 else (None, None)
    return {
        "symbol": symbol, "slices": slices,
        "notional_usdt": round(notional_usdt, 2),
        "best_case_bp": best, "worst_case_bp": worst,
        "quotable": best is not None,
        "basis": "estimated",
        "assumption_best": "the book fully refills between clips",
        "assumption_worst": "the book never refills (identical to one clip)",
        "unverified": ["replenishment between clips is not observable from a "
                       "snapshot; the crawl is what will narrow this interval"],
    }
