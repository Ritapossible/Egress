"""What each listed symbol actually is.

`symbolType` is the authoritative field and the reason this module exists. The
obvious shortcut - treat anything matching R*USDT as a tokenized stock - is wrong
28 times in the current listing set. It swallows 26 ordinary crypto pairs
(RENDERUSDT, RONINUSDT, RLCUSDT - iExec, not Royal Caribbean) and misses two
pre-listing stocks that do not carry the prefix at all. A study built on that
heuristic would have reported crypto liquidity as tokenized-stock liquidity.

Measured 2026-09-14: 1,175 stock, 584 crypto, 2 metal.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import config, market

STOCK = "stock"
CRYPTO = "crypto"
UTC = dt.timezone.utc


def classify(instruments: list[dict]) -> dict[str, dict]:
    """symbol -> the facts about it that matter for a liquidity study."""
    out = {}
    for row in instruments:
        symbol = row.get("symbol")
        if not symbol:
            continue
        out[symbol] = {
            "type": row.get("symbolType", "unknown"),
            "base": row.get("baseCoin", ""),
            "status": row.get("status", ""),
            # The venue's own price band. Stocks sit at 0.1, crypto at 0.02 - a
            # 10% collar is the venue conceding these move differently.
            "band": row.get("buyLimitPriceRatio", ""),
            "min_order_usdt": row.get("minOrderAmount", ""),
            "launch_ms": row.get("launchTime", ""),
        }
    return out


def snapshot(root: Path | None = None) -> dict:
    """Fetch and store the universe. Listings change; that is itself a finding."""
    root = root or config.STATE
    rows = classify(market.instruments())
    payload = {
        "captured": dt.datetime.now(UTC).isoformat(),
        "counts": counts(rows),
        "symbols": rows,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "universe.json").write_text(json.dumps(payload, indent=1, sort_keys=True))
    return payload


def load(root: Path | None = None) -> dict[str, dict]:
    path = (root or config.STATE) / "universe.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text()).get("symbols", {})


def counts(symbols: dict[str, dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in symbols.values():
        out[row["type"]] = out.get(row["type"], 0) + 1
    return dict(sorted(out.items()))


def of_type(symbols: dict[str, dict], kind: str) -> list[str]:
    return sorted(s for s, r in symbols.items() if r["type"] == kind)
