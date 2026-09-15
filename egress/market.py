"""The Bitget public market client. Two endpoints, no credentials.

Every failure is typed. A crawler that cannot tell "the venue said nothing" from
"we failed to ask" writes gaps into the record that look like data.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import config


class MarketUnavailable(RuntimeError):
    """The venue could not be read. Carries why, for the manifest."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _get(url: str, params: dict[str, str], *, timeout_s: int | None = None,
         retries: int | None = None) -> Any:
    """GET a public endpoint and return its `data`, or raise MarketUnavailable.

    `timeout_s`/`retries` exist so the request path can spend a budget a user
    will wait for while the crawler keeps its patient one. See config.
    """
    timeout_s = timeout_s if timeout_s is not None else config.HTTP_TIMEOUT_S
    retries = retries if retries is not None else config.HTTP_RETRIES
    # Encoded, not interpolated. Nothing user-supplied reaches here today -
    # symbols are looked up in the listed universe first - but a query string
    # built by hand is one careless caller away from being a request forgery.
    full = f"{url}?{urllib.parse.urlencode(params)}" if params else url
    last = "no attempt"
    for attempt in range(retries):
        if attempt:
            time.sleep(2 ** attempt)
        req = urllib.request.Request(full, headers={"User-Agent": config.USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            last = f"http {exc.code}"
            continue
        except urllib.error.URLError as exc:
            last = f"unreachable: {exc.reason}"
            continue
        except TimeoutError:
            last = f"timeout after {timeout_s}s"
            continue
        except json.JSONDecodeError as exc:
            last = f"malformed json: {exc}"
            continue
        if str(body.get("code")) not in ("00000", "0"):
            last = f"api code {body.get('code')}: {str(body.get('msg'))[:80]}"
            continue
        data = body.get("data")
        # tickers/instruments return a list; orderbook returns an object. Both
        # are valid - only None or a scalar means the venue told us nothing.
        if not isinstance(data, (list, dict)):
            last = f"data is {type(data).__name__}, expected a list or object"
            continue
        return data
    raise MarketUnavailable(last)


def instruments(*, quick: bool = False) -> list[dict]:
    """Every spot instrument, with the metadata that says what it actually is."""
    return _get(config.INSTRUMENTS, {"category": config.CATEGORY}, **_budget(quick))


def tickers(*, quick: bool = False) -> list[dict]:
    """Top of book for the whole universe in one request."""
    return _get(config.TICKERS, {"category": config.CATEGORY}, **_budget(quick))


def _budget(quick: bool) -> dict:
    """The impatient budget for anything a user is waiting on."""
    if not quick:
        return {}
    return {"timeout_s": config.REQUEST_TIMEOUT_S,
            "retries": config.REQUEST_RETRIES}


def ticker(symbol: str, *, quick: bool = False) -> dict:
    """One symbol's top of book, straight from the ticker feed.

    Needed because `orderbook` and `tickers` disagree: some symbols return an
    empty depth book while the ticker shows a live two-sided quote and millions
    in 24h turnover. See `depth_or_touch`.
    """
    for row in tickers(quick=quick):
        if row.get("symbol") == symbol:
            return row
    raise MarketUnavailable(f"{symbol} is not in the ticker feed")


def depth_or_touch(symbol: str, limit: int = 150,
                   *, quick: bool = False) -> tuple[list, list, str]:
    """(bids, asks, source) - the best view of the book the venue will give.

    `source` is "orderbook" when real depth came back, "touch" when only the
    ticker's best bid and offer are available, and "none" when neither is.

    The distinction is the point. An empty depth response is NOT proof of an
    empty market: RPBRUSDT and RSYKUSDT both return `{"a": [], "b": []}` while
    quoting two-sided with over 2M USDT of 24h turnover. Treating that silence as
    zero liquidity would report a venue quirk as a finding about the asset.
    """
    bids, asks = orderbook(symbol, limit, quick=quick)
    if bids or asks:
        return bids, asks, "orderbook"
    try:
        row = ticker(symbol, quick=quick)
    except MarketUnavailable:
        return [], [], "none"

    def level(price_key: str, size_key: str) -> list:
        try:
            price, size = float(row.get(price_key) or 0), float(row.get(size_key) or 0)
        except (TypeError, ValueError):
            return []
        return [[price, size]] if price > 0 and size > 0 else []

    touch_bids, touch_asks = level("bid1Price", "bid1Size"), level("ask1Price", "ask1Size")
    if touch_bids or touch_asks:
        return touch_bids, touch_asks, "touch"
    return [], [], "none"


def candles(symbol: str, interval: str = "5m", limit: int = 100) -> list[dict]:
    """Traded bars for one symbol: what ACTUALLY printed, not what was quoted.

    The venue names the interval `5m`, not `5min` - the latter is rejected with
    code 40020. Rows arrive as positional strings; they are named here so no
    caller has to count columns.
    """
    rows = _get(config.CANDLES, {"category": config.CATEGORY, "symbol": symbol,
                                 "interval": interval, "limit": str(limit)})
    out = []
    for row in rows if isinstance(rows, list) else []:
        if len(row) < 7:
            continue
        try:
            out.append({"ts": int(row[0]), "open": float(row[1]),
                        "high": float(row[2]), "low": float(row[3]),
                        "close": float(row[4]), "base_vol": float(row[5]),
                        "quote_vol": float(row[6])})
        except (TypeError, ValueError):
            continue
    return sorted(out, key=lambda r: r["ts"])


def orderbook(symbol: str, limit: int = 150,
              *, quick: bool = False) -> tuple[list, list]:
    """(bids, asks) for one symbol, each a list of [price, size], best first.

    On demand only, never in the crawl loop. The venue names these `b` and `a`;
    they are unpacked here so no caller has to know that.
    """
    data = _get(config.ORDERBOOK,
                {"category": config.CATEGORY, "symbol": symbol, "limit": str(limit)},
                **_budget(quick))
    if not isinstance(data, dict):
        raise MarketUnavailable(f"orderbook for {symbol} was not an object")
    def side(key: str) -> list:
        out = []
        for level in data.get(key, []):
            try:
                price, size = float(level[0]), float(level[1])
            except (TypeError, ValueError, IndexError):
                # One unreadable level is not a reason to lose the book, but it
                # must not become a bare ValueError either: this module's
                # contract is that every failure is typed.
                continue
            out.append([price, size])
        return out
    return side("b"), side("a")
