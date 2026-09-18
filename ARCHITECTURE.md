# Architecture

## The shape

```
   Bitget public API                    no credentials, anywhere in this project
   ----------------
   market/instruments  ──┐
   market/tickers      ──┤
   market/orderbook    ──┘
           │
           ▼
   egress/market.py        typed failures; never a bare except
           │
           ├──► egress/universe.py     what each symbol IS (symbolType)
           │        └─► state/universe.json
           │
           └──► egress/crawl.py        the loop: one request / 5 min
                    │
                    ▼
                 egress/store.py       append-only, manifest-gated
                    ├─► state/snapshots/YYYY-MM-DD.csv.gz
                    └─► state/manifest.jsonl
                             │
                             ▼
                 egress/sessions.py    open | overnight | weekend | holiday
                             │          (analysis only - the crawler never imports it)
                             ▼
                    estimator  ·  research desk  ·  page
                                              │
                                              ▼
                              docs/{index,evidence,validation,
                                    method,docs}.html
```

The site is one page per menu tab, generated from the same fact set by
`egress/page.py`. Each file is static, carries no request to anything external,
and can be opened from a checkout. `docs/index.html` is the only one that loads
a script, because it is the only one with the desk on it.

## The five decisions that matter

### 1. Collection is separate from interpretation

`crawl.py` records raw venue timestamps and nothing else. It does not import
`sessions.py`, does not label a row "overnight", does not decide what is a stock.

If the market calendar is wrong, only the analysis is wrong, and the analysis can
be rerun. A crawler that baked its interpretation into the file would have
contaminated a week of collection that cannot be repeated.

### 2. The manifest is the authority, not the CSV

Rows are written first, then the snapshot is recorded. Never the reverse.

A crawler killed mid-write - a reclaimed runner, a six-hour job cap - leaves a
short snapshot on disk, and a short snapshot is indistinguishable from a thin
market. The manifest holds the row count the writer actually completed, so an
unfinished snapshot is simply absent from it and the reader skips it. Gaps then
show up as gaps rather than as quiet, plausible data.

`store.coverage()` reports them explicitly, including the minutes lost.

### 3. Every instrument is stored, not only the subject

The universe moves: 1,175 tokenized stocks on 14 Sep 2026, 1,655 four days later after Bitget listed 480 in one wave, alongside ~585 crypto pairs and 2 metals. All of it
is recorded.

The crypto pairs are the **control group**: same venue, same matching engine,
same fee schedule, and no reason for their liquidity to care whether the NYSE is
open. Without them, a venue-wide change in spreads and a tokenized-stock one look
identical, and the central claim would be unfalsifiable.

First snapshot, US market closed: median stock spread **151.3 bp**, median crypto
spread **10.8 bp**. One observation, not yet a finding - which is exactly what
the crawl is for.

### 4. `symbolType`, never the ticker prefix

Treating `R*USDT` as tokenized stock is wrong 28 times in the live listing set:
it swallows 26 crypto pairs (`RLCUSDT` is iExec, `RENDERUSDT`, `RONINUSDT`...)
and misses 2 pre-listing stocks that carry no prefix. The venue declares
`symbolType: stock | crypto | metal`; that is what is used, and a test asserts
the heuristic would have been wrong so nobody reintroduces it as a shortcut.

### 4b. Cohort by listing age, not by whatever is listed today

The headline medians cover names listed thirty days or more (`facts.ESTABLISHED_DAYS`),
with recent listings reported beside them rather than mixed in.

This is not tidiness. A median taken across every quoted name is a median over
Bitget's listing calendar as much as over its liquidity: the 480-name wave on
17 Sep moved the overnight figure from 165 bp to 260 bp with nothing happening
in the market, and the published ratio had already drifted 19x to 24x on
composition alone.

Split, the record says something sharper. Overnight, names listed thirty days or
more sit near 66 bp; names listed more recently sit near 589 bp. Listing age
predicts overnight spread better than anything else measured here. The cohort is
decided per snapshot from the venue's own `launchTime`, so a name joins the
headline on its own thirtieth day and nothing is re-dated by hand.

### 5. Zero runtime dependencies

stdlib only - `urllib`, `gzip`, `csv`, `json`, `datetime`. The crawler runs on a
bare Python 3.10+ with no install step, which is why it can sit on a free runner
for a week without a supply chain to break. `ruff` and `mypy` are development
tools, never imported.

## Storage

`state/snapshots/YYYY-MM-DD.csv.gz` - one file per UTC day, appended as gzip
members (they concatenate, so appending is a real append: no rewrite, no lock).

| column | meaning |
|---|---|
| `snap_ts` | when **we** fetched, ms. All rows in one snapshot share it |
| `symbol` | e.g. `RTSLAUSDT` |
| `bid` / `ask` | best bid and offer |
| `bid_size` / `ask_size` | size at the touch |
| `last` | last traded price |
| `turnover24h` | rolling 24h turnover; differencing gives flow |
| `venue_ts` | when **the venue** last updated this symbol |

`venue_ts` is kept deliberately. A book that has not updated in hours is a dead
book, and that staleness is itself a liquidity signal rather than an artifact.

Cost: ~46 KB per snapshot gzipped, ~13 MB per day at a 5-minute cadence.

## Cadence, and why five minutes

Fast enough to resolve the 13:30 UTC open and the 20:00 UTC close to the bar.
Slow enough that a week of the full universe stays under 100 MB.

Each sleep targets the next multiple of the interval rather than sleeping a fixed
amount after variable work, so a slow request cannot walk the schedule and
snapshots land on a regular grid.

## Running it for a week

GitHub Actions caps a job at 6 hours and treats cron as best effort - this
project's sibling saw delays of 1h23m, 1h52m and 3h17m in a single week. So the
crawler is a **long-running job, not a cron tick**: a scheduled run every 6 hours
starts a loop that snapshots for 5.8 hours and commits as it goes. A delayed
start costs a gap, and the gap is recorded rather than hidden.

It also runs anywhere Python does (`python -m egress.crawl --loop`), so a laptop
or a VPS is a valid fallback if the runner proves unreliable.
