"""The crawler. One request every five minutes, the whole universe each time.

    python -m egress.crawl --once                 one snapshot, then exit
    python -m egress.crawl --loop --hours 5.8     run until just under a 6h job cap
    python -m egress.crawl --coverage             what the record holds so far

This is the only time-critical part of the project. The exit-cost estimator can
be written on the last day; the week of quotes it is measured against cannot. An
hour not crawled is an hour nobody can go back for.

Design notes that matter:

- **Every instrument is stored, not only the tokenized stocks.** The crypto pairs
  are the control group. Without them a venue-wide liquidity change and a
  tokenized-stock one look identical.
- **Failures are recorded, not retried into silence.** A snapshot that could not
  be fetched appends nothing to the manifest and prints why. Gaps stay visible.
- **The clock does not drift.** Each sleep targets the next multiple of the
  interval rather than sleeping a fixed amount after variable work, so snapshots
  land on a regular grid and a slow request cannot walk the schedule.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time

from . import config, market, store, universe

UTC = dt.timezone.utc


def snapshot(root=None, verbose: bool = True) -> dict:
    """Fetch the universe once and store it. Returns what happened."""
    started = time.time()
    snap_ts = int(started * 1000)
    try:
        rows = market.tickers()
    except market.MarketUnavailable as exc:
        if verbose:
            print(f"[{dt.datetime.now(UTC):%H:%M:%S}] FAILED - {exc.reason}", flush=True)
        return {"ok": False, "reason": exc.reason, "snap_ts": snap_ts}

    stored = store.rows_from(rows, snap_ts)
    path = store.append(stored, snap_ts, root)
    took = time.time() - started
    if verbose:
        print(f"[{dt.datetime.now(UTC):%H:%M:%S}] {len(stored):,} rows "
              f"-> {path.name} ({took:.2f}s)", flush=True)
    return {"ok": True, "rows": len(stored), "snap_ts": snap_ts,
            "seconds": round(took, 2)}


def loop(hours: float, interval_s: int = config.DEFAULT_INTERVAL_S,
         root=None, verbose: bool = True) -> dict:
    """Snapshot on a fixed grid until the budget runs out."""
    deadline = time.time() + hours * 3600
    taken = failed = 0
    if verbose:
        print(f"crawling every {interval_s}s for {hours}h "
              f"(until {dt.datetime.now(UTC) + dt.timedelta(hours=hours):%H:%M}Z)",
              flush=True)
    while time.time() < deadline:
        result = snapshot(root, verbose)
        taken += bool(result["ok"])
        failed += not result["ok"]
        # Target the next grid point, so work time never accumulates into drift.
        nxt = (int(time.time() / interval_s) + 1) * interval_s
        nap = min(nxt - time.time(), deadline - time.time())
        if nap <= 0:
            break
        time.sleep(nap)
    return {"taken": taken, "failed": failed}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="one snapshot, then exit")
    ap.add_argument("--loop", action="store_true", help="keep snapshotting")
    ap.add_argument("--hours", type=float, default=5.8,
                    help="how long to loop (default fits a 6h job cap)")
    ap.add_argument("--interval", type=int, default=config.DEFAULT_INTERVAL_S,
                    help="seconds between snapshots")
    ap.add_argument("--universe", action="store_true",
                    help="refresh the instrument classification and exit")
    ap.add_argument("--coverage", action="store_true",
                    help="report what the record holds, then exit")
    args = ap.parse_args(argv)

    if args.coverage:
        print(json.dumps(store.coverage(), indent=1))
        return 0
    if args.universe:
        print(json.dumps(universe.snapshot()["counts"], indent=1))
        return 0
    if args.loop:
        # Refreshed at the top of every run: listings come and go, and knowing
        # when a symbol appeared is part of the record.
        universe.snapshot()
        result = loop(args.hours, args.interval)
        print(json.dumps(result))
        return 0 if result["taken"] else 1
    # --once is the default: a bare `python -m egress.crawl` takes one snapshot,
    # which is the safe thing for a hand-run command to do.
    return 0 if snapshot()["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
