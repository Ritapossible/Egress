"""Walk the same book through two independent clients and publish the difference.

Egress's biggest stated limit is that two of the venue's own volume feeds
disagree about the liquid names, so six symbols are excluded from validation.
A project making that argument owes the reader the same scepticism about its
own reads: everything here comes through one HTTP client, and a bug in that
client would look exactly like a property of the market.

So the same order is priced twice - once through `egress.market` as usual, once
through the Bitget Agent Hub CLI, a different SDK in a different process - and
both are costed by the same `exitcost` code so any gap is the book rather than
the arithmetic. Agreement is not proof of correctness; it does rule out our own
transport as the explanation, which is the part that was previously unchecked.

The symbols are validation's own list, imported rather than restated: the point
is to cover the six names validation had to exclude.

    python3 tools/hub_crosscheck.py            # -> state/hub_crosscheck.json
    python3 tools/hub_crosscheck.py --notional 10000
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from egress import exitcost, hub, market, validate  # noqa: E402

OUT = ROOT / "state" / "hub_crosscheck.json"
NOTIONAL = 25_000.0


def build(notional: float = NOTIONAL, symbols=None) -> Path:
    symbols = list(symbols or validate.DEFAULT_SYMBOLS)
    rows = []
    for symbol in symbols:
        row: dict = {"symbol": symbol}
        try:
            bids, asks, source = market.depth_or_touch(symbol)
        except market.MarketUnavailable as exc:
            rows.append({**row, "verdict": "ours unavailable", "detail": str(exc)[:120]})
            continue
        ours = exitcost.from_book(symbol, notional, bids, asks, source)
        rows.append({**row, **hub.compare(symbol, notional, ours),
                     "our_source": source})

    compared = [r for r in rows if r.get("verdict") in ("agree", "disagree")]
    gaps = [r["gap_bp"] for r in compared if isinstance(r.get("gap_bp"), (int, float))]
    payload = {
        "built_on": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "notional_usdt": notional,
        "hub_installed": hub.installed(),
        "agree_within_bp": hub.AGREE_BP,
        "counts": {
            "asked": len(rows),
            "compared": len(compared),
            "agreed": sum(1 for r in compared if r["verdict"] == "agree"),
            "disagreed": sum(1 for r in compared if r["verdict"] == "disagree"),
            "unavailable": sum(1 for r in rows if r.get("available") is False),
        },
        "max_gap_bp": round(max(gaps), 2) if gaps else None,
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    return OUT


def load() -> dict | None:
    try:
        return json.loads(OUT.read_text())
    except (OSError, json.JSONDecodeError):
        return None


if __name__ == "__main__":
    size = NOTIONAL
    if "--notional" in sys.argv:
        size = float(sys.argv[sys.argv.index("--notional") + 1])
    path = build(size)
    d = json.loads(path.read_text())
    c = d["counts"]
    print(f"wrote {path.name} ({path.stat().st_size:,} bytes)")
    print(f"  {c['compared']} of {c['asked']} compared · {c['agreed']} agree · "
          f"{c['disagreed']} disagree · max gap {d['max_gap_bp']} bp")
    for row in d["rows"]:
        mark = {"agree": "=", "disagree": "!"}.get(row.get("verdict"), "?")
        print(f"  {mark} {row['symbol']:12} {row.get('verdict', '-'):16} "
              f"ours {row.get('ours_total_bp', '-')} hub {row.get('hub_total_bp', '-')}"
              f"{'  ' + row.get('reason', '') if row.get('reason') else ''}")
