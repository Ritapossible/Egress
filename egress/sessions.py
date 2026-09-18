"""Is the US equity market open at a given instant?

The crawler does not import this. It records raw timestamps and nothing else, so
that a mistake in this calendar can never contaminate the stored record - only
the analysis on top of it, which can be rerun. Interpretation belongs downstream
of collection.

Times are UTC. The Eastern offset is COMPUTED, not assumed: hardcoding the
summer conversion is wrong by an hour from November to March, which would
silently mislabel an hour of every trading day for five months of the year.
"""
from __future__ import annotations

import datetime as dt

UTC = dt.timezone.utc

# Regular US equity trading is 09:30-16:00 ET. In UTC that is 13:30-20:00 while
# daylight time is in force and 14:30-21:00 while standard time is - an hour
# that a hardcoded constant gets silently wrong for five months of the year.
OPEN_ET = dt.time(9, 30)
CLOSE_ET = dt.time(16, 0)
# US extended hours. These matter because the claim being measured is about
# whether a market maker can hedge: in pre and post there is a real, thin book
# on the reference venue, and between 20:00 and 04:00 ET there is none at all.
# Folding all three into one "overnight" bucket averaged a regime that has some
# liquidity together with one that has none.
PRE_OPEN_ET = dt.time(4, 0)
POST_CLOSE_ET = dt.time(20, 0)

# US daylight saving: second Sunday in March to first Sunday in November.
# Computed rather than tabulated so this does not expire with a hardcoded year.
OPEN_UTC = dt.time(13, 30)          # kept for readers of the EDT window
CLOSE_UTC = dt.time(20, 0)

# US market holidays. 2026 covers the study window; 2027 is here so the
# calendar does not quietly start calling holidays trading days in January.
HOLIDAYS = frozenset({
    dt.date(2026, 1, 1), dt.date(2026, 1, 19), dt.date(2026, 2, 16),
    dt.date(2026, 4, 3), dt.date(2026, 5, 25), dt.date(2026, 6, 19),
    dt.date(2026, 7, 3), dt.date(2026, 9, 7), dt.date(2026, 11, 26),
    dt.date(2026, 12, 25),
    dt.date(2027, 1, 1), dt.date(2027, 1, 18), dt.date(2027, 2, 15),
    dt.date(2027, 3, 26), dt.date(2027, 5, 31), dt.date(2027, 6, 18),
    dt.date(2027, 7, 5), dt.date(2027, 9, 6), dt.date(2027, 11, 25),
    dt.date(2027, 12, 24),
})


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> dt.date:
    """The nth given weekday of a month, e.g. the 2nd Sunday in March."""
    first = dt.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + dt.timedelta(days=offset + 7 * (nth - 1))


def is_dst(day: dt.date) -> bool:
    """US Eastern daylight time: 2nd Sunday in March to 1st Sunday in November.

    The transitions happen at 02:00 local, which is inside the overnight phase
    on both days, so resolving to the day is enough for a market calendar.
    """
    start = _nth_weekday(day.year, 3, 6, 2)      # Sunday == 6
    end = _nth_weekday(day.year, 11, 6, 1)
    return start <= day < end


def utc_offset_hours(day: dt.date) -> int:
    """Hours to add to Eastern time to get UTC. 4 in summer, 5 in winter."""
    return 4 if is_dst(day) else 5


def open_close_utc(day: dt.date) -> tuple[dt.time, dt.time]:
    """The regular session in UTC for that particular day."""
    shift = utc_offset_hours(day)
    return (dt.time((OPEN_ET.hour + shift) % 24, OPEN_ET.minute),
            dt.time((CLOSE_ET.hour + shift) % 24, CLOSE_ET.minute))


def is_trading_day(day: dt.date) -> bool:
    return day.weekday() <= 4 and day not in HOLIDAYS


def is_open(when: dt.datetime) -> bool:
    """True while the reference market is open, so a maker can hedge."""
    when = when.astimezone(UTC)
    if not is_trading_day(when.date()):
        return False
    opens, closes = open_close_utc(when.date())
    return opens <= when.timetz().replace(tzinfo=None) < closes


def eastern(when: dt.datetime) -> dt.datetime:
    """The same instant in Eastern time.

    The offset is chosen from the UTC date, which is what `is_open` already
    does; keeping one convention matters more here than the half hour it can
    misplace at the turn of a day, because the two must agree on where the
    regular session starts and ends.
    """
    when = when.astimezone(UTC)
    return when - dt.timedelta(hours=utc_offset_hours(when.date()))


def phase(when: dt.datetime) -> str:
    """open | pre | post | overnight | weekend | holiday.

    Pre and post are split out because they are not the same regime as a shut
    market. The reference venue quotes in both, thinly, so a maker can still
    hedge; between 20:00 and 04:00 ET it cannot. Measuring them as one bucket
    mixed a market with some liquidity into a claim about having none.
    """
    when = when.astimezone(UTC)
    day = when.date()
    if day in HOLIDAYS:
        return "holiday"
    if day.weekday() > 4:
        return "weekend"
    if is_open(when):
        return "open"
    # In Eastern time, not UTC: the post window is 16:00-20:00 ET, which is
    # 20:00-00:00 UTC in summer, and a UTC comparison cannot express a window
    # whose end wraps past midnight.
    clock = eastern(when).time()
    if PRE_OPEN_ET <= clock < OPEN_ET:
        return "pre"
    if CLOSE_ET <= clock < POST_CLOSE_ET:
        return "post"
    return "overnight"
