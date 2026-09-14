"""Is the US equity market open at a given instant?

The crawler does not import this. It records raw timestamps and nothing else, so
that a mistake in this calendar can never contaminate the stored record - only
the analysis on top of it, which can be rerun. Interpretation belongs downstream
of collection.

Times are UTC. US clocks fall back on 2026-11-01, after this study ends, so the
whole window is EDT and the conversion is a constant.
"""
from __future__ import annotations

import datetime as dt

UTC = dt.timezone.utc

# Regular US equity trading, 09:30-16:00 ET, expressed in UTC during EDT.
OPEN_UTC = dt.time(13, 30)
CLOSE_UTC = dt.time(20, 0)

# US market holidays in the study window and either side of it.
HOLIDAYS_2026 = frozenset({
    dt.date(2026, 1, 1), dt.date(2026, 1, 19), dt.date(2026, 2, 16),
    dt.date(2026, 4, 3), dt.date(2026, 5, 25), dt.date(2026, 6, 19),
    dt.date(2026, 7, 3), dt.date(2026, 9, 7), dt.date(2026, 11, 26),
    dt.date(2026, 12, 25),
})


def is_trading_day(day: dt.date) -> bool:
    return day.weekday() <= 4 and day not in HOLIDAYS_2026


def is_open(when: dt.datetime) -> bool:
    """True while the reference market is open, so a maker can hedge."""
    when = when.astimezone(UTC)
    if not is_trading_day(when.date()):
        return False
    return OPEN_UTC <= when.timetz().replace(tzinfo=None) < CLOSE_UTC


def phase(when: dt.datetime) -> str:
    """open | overnight | weekend | holiday - the four regimes to compare."""
    when = when.astimezone(UTC)
    day = when.date()
    if day in HOLIDAYS_2026:
        return "holiday"
    if day.weekday() > 4:
        return "weekend"
    return "open" if is_open(when) else "overnight"
