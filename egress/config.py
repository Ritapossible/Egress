"""Paths, endpoints and the few constants the crawler needs.

No API key appears anywhere in this project. Every endpoint used is public
(`auth: public` in Bitget's own tool surface), which is why the crawler can run
unattended on a shared runner with nothing to leak.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = Path(os.environ.get("EGRESS_STATE", ROOT / "state"))

API = "https://api.bitget.com/api/v3"
TICKERS = f"{API}/market/tickers"
INSTRUMENTS = f"{API}/market/instruments"
ORDERBOOK = f"{API}/market/orderbook"

# One GET returns every spot instrument, so the whole universe is one request.
# Measured 2026-09-14: 1,761 rows, 582 KB, 0.81 s.
CATEGORY = "SPOT"

HTTP_TIMEOUT_S = 25
HTTP_RETRIES = 3
USER_AGENT = "egress/0.1 (+https://github.com/Ritapossible/Egress)"

# 5 minutes. Fast enough to resolve the US open and close to the bar, slow
# enough that six days of the full universe stays a few hundred MB.
DEFAULT_INTERVAL_S = 300
