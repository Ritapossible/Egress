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

from . import config, market, signal, store, universe

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
    try:
        path = store.append(stored, snap_ts, root)
    except OSError as exc:
        # A full disk or a read-only mount ends this snapshot, not the shift.
        # Nothing was recorded in the manifest, so the gap stays visible.
        if verbose:
            print(f"[{dt.datetime.now(UTC):%H:%M:%S}] WRITE FAILED - {exc}",
                  flush=True)
        return {"ok": False, "reason": f"write failed: {exc}", "snap_ts": snap_ts}
    took = time.time() - started
    if verbose:
        print(f"[{dt.datetime.now(UTC):%H:%M:%S}] {len(stored):,} rows "
              f"-> {path.name} ({took:.2f}s)", flush=True)
    return {"ok": True, "rows": len(stored), "snap_ts": snap_ts,
            "seconds": round(took, 2)}


# How often the listed universe is re-read inside a shift.
#
# It used to be read once, at the top of a 5.5-hour run. The quotes and the
# pages were 20 minutes old and the listing count could be six hours old, so
# when Bitget listed 480 tokenized stocks in one wave the site kept saying 1,175
# for most of a day - a number nobody had typed and nobody could see was stale.
# An hour is far inside how fast listings actually move, and costs one extra
# request an hour against a crawler already making one every five minutes.
UNIVERSE_REFRESH_S = 3600


def _refresh_universe(root, verbose: bool) -> bool:
    """Re-read the listing. A venue blip here must never cost the shift.

    The previous universe is still on disk and the quotes are the half that
    cannot be caught up later, so this reports and carries on.
    """
    try:
        counts = universe.snapshot(root)["counts"]
    except (market.MarketUnavailable, OSError) as exc:
        if verbose:
            print(f"[{dt.datetime.now(UTC):%H:%M:%S}] universe refresh failed "
                  f"({exc}); carrying the stored one", flush=True)
        return False
    if verbose:
        print(f"[{dt.datetime.now(UTC):%H:%M:%S}] universe: "
              f"{', '.join(f'{v:,} {k}' for k, v in sorted(counts.items()))}",
              flush=True)
    return True


def loop(hours: float, interval_s: int = config.DEFAULT_INTERVAL_S,
         root=None, verbose: bool = True,
         universe_s: int = UNIVERSE_REFRESH_S) -> dict:
    """Snapshot on a fixed grid until the budget runs out."""
    deadline = time.time() + hours * 3600
    taken = failed = 0
    listings = 0
    next_universe = time.time()
    if verbose:
        print(f"crawling every {interval_s}s for {hours}h "
              f"(until {dt.datetime.now(UTC) + dt.timedelta(hours=hours):%H:%M}Z)",
              flush=True)
    while time.time() < deadline:
        if time.time() >= next_universe:
            listings += _refresh_universe(root, verbose)
            next_universe = time.time() + universe_s
        result = snapshot(root, verbose)
        taken += bool(result["ok"])
        failed += not result["ok"]
        # Target the next grid point, so work time never accumulates into drift.
        nxt = (int(time.time() / interval_s) + 1) * interval_s
        nap = min(nxt - time.time(), deadline - time.time())
        if nap <= 0:
            break
        time.sleep(nap)
    return {"taken": taken, "failed": failed, "universe_refreshes": listings}


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
    ap.add_argument("--signal", action="store_true",
                    help="probe bitget-signal and record what it returned")
    args = ap.parse_args(argv)

    if args.coverage:
        print(json.dumps(store.coverage(), indent=1))
        return 0
    if args.signal:
        # Once per crawl session, not once per snapshot. The record is about
        # the Skill's state, which does not change every twenty minutes, and
        # hammering a service that is already timing out is not a probe.
        record = signal.write()
        print(json.dumps(json.loads(record.read_text()), indent=1))
        return 0
    if args.universe:
        print(json.dumps(universe.snapshot()["counts"], indent=1))
        return 0
    if args.loop:
        # The loop refreshes the listing itself, on its own clock, starting
        # with the first pass - see UNIVERSE_REFRESH_S.
        result = loop(args.hours, args.interval)
        print(json.dumps(result))
        return 0 if result["taken"] else 1
    # --once is the default: a bare `python -m egress.crawl` takes one snapshot,
    # which is the safe thing for a hand-run command to do.
    return 0 if snapshot()["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
