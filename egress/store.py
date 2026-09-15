"""Append-only snapshot store: one gzipped CSV per UTC day, plus a manifest.

Two files, two jobs. The CSV holds the rows. The manifest holds one line per
snapshot that COMPLETED, with the row count the writer actually wrote.

That split is the whole point. A crawler killed mid-write - a runner reclaimed,
a six-hour job ending - leaves a short snapshot behind, and a short snapshot is
indistinguishable from a thin market unless something recorded what was expected.
The manifest is that something: a snapshot nobody finished never appears in it,
and the reader skips it. Gaps are then visible as gaps rather than as quiet data.

gzip members concatenate, so appending is a real append: no rewrite, no lock, and
a partial tail costs at most the snapshot being written.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import io
import itertools
import json
from pathlib import Path

from . import config

UTC = dt.timezone.utc
COLUMNS = ("snap_ts", "symbol", "bid", "ask", "bid_size", "ask_size",
           "last", "turnover24h", "venue_ts")

SNAPSHOT_DIR = "snapshots"
MANIFEST = "manifest.jsonl"


def _day_path(root: Path, when: dt.datetime) -> Path:
    return root / SNAPSHOT_DIR / f"{when:%Y-%m-%d}.csv.gz"


def _num(row: dict, key: str) -> str:
    """Venue numbers arrive as strings. Blank means the venue sent nothing."""
    value = row.get(key)
    return "" if value in (None, "") else str(value)


def rows_from(tickers: list[dict], snap_ts: int) -> list[tuple]:
    """Flatten a ticker payload into storable rows.

    Every instrument is kept, not just the tokenized stocks. The 584 crypto pairs
    trade on the same engine under the same fee schedule and have no reason to
    care whether the NYSE is open, which makes them the control group. A study
    that only stored its subject could not tell a venue-wide effect from a
    tokenized-stock one.
    """
    return [
        (snap_ts, r.get("symbol", ""), _num(r, "bid1Price"), _num(r, "ask1Price"),
         _num(r, "bid1Size"), _num(r, "ask1Size"), _num(r, "lastPrice"),
         _num(r, "turnover24h"), _num(r, "ts"))
        for r in tickers if r.get("symbol")
    ]


def append(rows: list[tuple], snap_ts: int, root: Path | None = None,
           note: str = "") -> Path:
    """Write one snapshot, then record it. Never the other way round."""
    root = root or config.STATE
    when = dt.datetime.fromtimestamp(snap_ts / 1000, UTC)
    path = _day_path(root, when)
    path.parent.mkdir(parents=True, exist_ok=True)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    if not path.exists():
        writer.writerow(COLUMNS)
    writer.writerows(rows)
    with gzip.open(path, "at", encoding="utf-8") as fh:
        fh.write(buf.getvalue())

    # Recorded only after the rows are durable, so the manifest can never claim
    # a snapshot that is not on disk.
    record = {"snap_ts": snap_ts, "at": when.isoformat(), "rows": len(rows),
              "file": path.name}
    if note:
        record["note"] = note
    manifest = root / MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return path


def manifest(root: Path | None = None) -> list[dict]:
    """Every completed snapshot, oldest first."""
    path = (root or config.STATE) / MANIFEST
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue          # a torn final line loses one snapshot, not the day
    return sorted(out, key=lambda r: r["snap_ts"])


def days(root: Path | None = None) -> list[dt.date]:
    """Every UTC day the manifest vouches for, oldest first.

    Read from the manifest rather than from the filenames in snapshots/, so a
    day whose file exists but whose snapshots were never completed is absent
    here for the same reason its rows are skipped in read_day.
    """
    seen = {dt.datetime.fromtimestamp(r["snap_ts"] / 1000, UTC).date()
            for r in manifest(root)}
    return sorted(seen)


def read_day(day: dt.date, root: Path | None = None) -> list[dict]:
    """Rows for one UTC day, keeping only snapshots the manifest vouches for."""
    root = root or config.STATE
    path = _day_path(root, dt.datetime(day.year, day.month, day.day, tzinfo=UTC))
    if not path.exists():
        return []
    complete = {r["snap_ts"] for r in manifest(root)}
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            # Each appended member repeats no header, but a day that was started
            # fresh has one; DictReader yields it as a row of its own names.
            if row.get("symbol") == "symbol":
                continue
            try:
                if int(row["snap_ts"]) in complete:
                    out.append(row)
            except (TypeError, ValueError):
                continue
    return out


def coverage(root: Path | None = None) -> dict:
    """What the record actually contains - counts, span, and the gaps."""
    records = manifest(root)
    if not records:
        return {"snapshots": 0, "rows": 0, "gaps": []}
    stamps = [r["snap_ts"] for r in records]
    gaps = []
    for earlier, later in itertools.pairwise(stamps):
        minutes = (later - earlier) / 60000
        if minutes > 2 * (config.DEFAULT_INTERVAL_S / 60):
            gaps.append({"from": earlier, "to": later, "minutes": round(minutes, 1)})
    return {
        "snapshots": len(records),
        "rows": sum(r["rows"] for r in records),
        "first": records[0]["at"],
        "last": records[-1]["at"],
        "hours": round((stamps[-1] - stamps[0]) / 3600000, 2),
        "gaps": gaps,
    }
