"""The Bitget public market client. Two endpoints, no credentials.

Every failure is typed. A crawler that cannot tell "the venue said nothing" from
"we failed to ask" writes gaps into the record that look like data.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from . import config


class MarketUnavailable(RuntimeError):
    """The venue could not be read. Carries why, for the manifest."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _get(url: str, params: dict[str, str]) -> Any:
    """GET a public endpoint and return its `data`, or raise MarketUnavailable."""
    query = "&".join(f"{k}={v}" for k, v in params.items())
    full = f"{url}?{query}" if query else url
    last = "no attempt"
    for attempt in range(config.HTTP_RETRIES):
        if attempt:
            time.sleep(2 ** attempt)
        req = urllib.request.Request(full, headers={"User-Agent": config.USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT_S) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            last = f"http {exc.code}"
            continue
        except urllib.error.URLError as exc:
            last = f"unreachable: {exc.reason}"
            continue
        except TimeoutError:
            last = f"timeout after {config.HTTP_TIMEOUT_S}s"
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


def instruments() -> list[dict]:
    """Every spot instrument, with the metadata that says what it actually is."""
    return _get(config.INSTRUMENTS, {"category": config.CATEGORY})


def tickers() -> list[dict]:
    """Top of book for the whole universe in one request."""
    return _get(config.TICKERS, {"category": config.CATEGORY})


def ticker(symbol: str) -> dict:
    """One symbol's top of book, straight from the ticker feed.

    Needed because `orderbook` and `tickers` disagree: some symbols return an
    empty depth book while the ticker shows a live two-sided quote and millions
    in 24h turnover. See `depth_or_touch`.
    """
    for row in tickers():
        if row.get("symbol") == symbol:
            return row
    raise MarketUnavailable(f"{symbol} is not in the ticker feed")


def depth_or_touch(symbol: str, limit: int = 150) -> tuple[list, list, str]:
    """(bids, asks, source) - the best view of the book the venue will give.

    `source` is "orderbook" when real depth came back, "touch" when only the
    ticker's best bid and offer are available, and "none" when neither is.

    The distinction is the point. An empty depth response is NOT proof of an
    empty market: RPBRUSDT and RSYKUSDT both return `{"a": [], "b": []}` while
    quoting two-sided with over 2M USDT of 24h turnover. Treating that silence as
    zero liquidity would report a venue quirk as a finding about the asset.
    """
    bids, asks = orderbook(symbol, limit)
    if bids or asks:
        return bids, asks, "orderbook"
    try:
        row = ticker(symbol)
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


def orderbook(symbol: str, limit: int = 150) -> tuple[list, list]:
    """(bids, asks) for one symbol, each a list of [price, size], best first.

    On demand only, never in the crawl loop. The venue names these `b` and `a`;
    they are unpacked here so no caller has to know that.
    """
    data = _get(config.ORDERBOOK,
                {"category": config.CATEGORY, "symbol": symbol, "limit": str(limit)})
    if not isinstance(data, dict):
        raise MarketUnavailable(f"orderbook for {symbol} was not an object")
    def side(key: str) -> list:
        return [[float(p), float(q)] for p, q in data.get(key, [])]
    return side("b"), side("a")
