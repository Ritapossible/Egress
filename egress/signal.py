"""bitget-signal, the handbook's perception layer, asked honestly.

What it is: 19 research tools on a second MCP host, no account and no key.
What it does for a desk that prices tokenized US stocks: less than it looks,
and saying exactly how much less is the point of this module.

Three things were measured rather than assumed, each of which changes the
claim that can be made:

1. **The tools take an `action`.** Calling them bare returns
   `{"error": "Unknown action: "}`, which reads like a dead service and is
   not one. Every call here names its action.
2. **Catalog actions answer; live-data actions do not.** `news_feed/sources`,
   `macro_indicators/series_list` and `cross_asset/assets_list` all return
   their catalogs. `news_feed/latest` returns all 44 feeds with `items: []`
   and `crypto_price/price` returns `ConnectTimeout('')` - the service runs,
   its own outbound fetches time out.
3. **The feed list is not about equities.** Of 44 feeds, one - CNBC - could
   plausibly carry a US stock story. The rest are crypto, tech and general
   news. So this cannot explain why RTSLAUSDT is wide; at best it is a
   control, the same way the crypto spread control works elsewhere here.

Probed on a schedule rather than per question. A desk answer must not wait on
a third party that is timing out, and a timestamped record of what a Skill
returned is worth more than a spinner.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import config, mcp

ENDPOINT = "https://datahub.noxiaohao.com/mcp"

# Of the 44 configured feeds, the ones that could carry a US stock story at
# all. Named rather than counted, so the claim can be checked.
EQUITY_CAPABLE = ("cnbc",)

# Catalog actions, which answer, paired with the live action they catalogue.
# A probe that only called the working half would be advertising.
PROBES = (
    ("news_feed", {"action": "sources"}, "catalog"),
    ("news_feed", {"action": "latest", "limit": 5}, "live"),
    ("macro_indicators", {"action": "series_list"}, "catalog"),
    ("cross_asset", {"action": "assets_list"}, "catalog"),
    ("crypto_price", {"action": "price", "symbol": "BTC"}, "live"),
)

OUT = "signal.json"


# The desk's fuse is six seconds because someone is waiting. This runs on a
# schedule, and the two answers it has to tell apart - "the feed returned no
# items" and "we gave up before it replied" - are different facts about the
# service. Waiting long enough to distinguish them is the whole point.
PROBE_TIMEOUT = 25


def call(tool: str, **arguments) -> object:
    """One bitget-signal tool, by name, with its action."""
    return mcp.call(tool, arguments, endpoint=ENDPOINT, timeout=PROBE_TIMEOUT)


def _articles(payload: object) -> int:
    """How many articles came back, across the per-feed envelopes.

    `news_feed/latest` answers with one envelope per feed, each carrying its
    own `items`. Counting the envelopes would report 44 headlines where there
    are none - a dead upstream reading as a busy one.
    """
    if not isinstance(payload, list):
        return 0
    return sum(len(f.get("items") or []) for f in payload if isinstance(f, dict))


def probe() -> dict:
    """Ask every probe and record what each returned. Never raises."""
    now = dt.datetime.now(dt.timezone.utc)
    out: dict = {"checked_at": now.isoformat(timespec="seconds"),
                 "endpoint": ENDPOINT, "results": []}
    feeds: list[str] = []
    for tool, arguments, kind in PROBES:
        row: dict = {"tool": tool, "action": arguments.get("action"), "kind": kind}
        try:
            payload = call(tool, **arguments)
        except Exception as exc:  # BLE001 ignored here: recorded, never swallowed
            row.update(answered=False, reason=f"{type(exc).__name__}: {exc}"[:160])
            out["results"].append(row)
            continue

        row["answered"] = True
        if isinstance(payload, dict) and isinstance(payload.get("feeds"), list):
            feeds = list(payload["feeds"])
            row["feeds"] = len(feeds)
        elif tool == "news_feed":
            row["articles"] = _articles(payload)
            row["feeds_reporting"] = (len(payload) if isinstance(payload, list) else 0)
        elif isinstance(payload, dict) and payload.get("text", "").startswith("Error"):
            row.update(answered=False, reason=payload["text"][:160])
        elif isinstance(payload, dict):
            keys = [k for k, v in payload.items() if isinstance(v, dict)]
            row["entries"] = sum(len(payload[k]) for k in keys) or len(payload)
        out["results"].append(row)

    out["feeds"] = feeds
    out["feed_count"] = len(feeds)
    out["equity_capable"] = [f for f in feeds if f in EQUITY_CAPABLE]
    out["catalogs_answering"] = sum(
        1 for r in out["results"] if r["kind"] == "catalog" and r.get("answered"))
    out["live_answering"] = sum(
        1 for r in out["results"]
        if r["kind"] == "live" and r.get("answered") and
        (r.get("articles", 0) > 0 or r.get("entries", 0) > 0))
    return out


def path() -> Path:
    return config.STATE / OUT


def write(out: Path | None = None) -> Path:
    target = out or path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(probe(), indent=1, sort_keys=True) + "\n")
    return target


def load() -> dict | None:
    try:
        return json.loads(path().read_text())
    except (OSError, ValueError):
        return None
