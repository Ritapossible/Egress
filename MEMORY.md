# Memory

Durable notes for anyone - human or model - picking this up mid-flight. Facts that
were expensive to learn and are cheap to forget.

## Verified against the live venue (2026-09-14)

| Thing | Value |
|---|---|
| Spot instruments | **1,761** total: **1,175 stock**, **584 crypto**, **2 metal** |
| One `tickers` call | 582 KB, **0.81 s**, covers the entire universe |
| Auth needed | **none** - `market` is `auth: public` in Bitget's own tool surface |
| Endpoint base | `https://api.bitget.com/api/v3` |
| Orderbook depth | 20+ levels; RTSLAUSDT bid side ≈ 300,000 USDT at 20 levels |
| Snapshot on disk | ~46 KB gzipped; ~13 MB/day at 5-minute cadence |

First measured comparison, US market **closed**, single snapshot:
median spread **stock 151.3 bp** vs **crypto 10.8 bp**; p90 **1,485.8** vs **31.9**.
One observation. Not a finding until the crawl spans both phases.

## Traps already hit, with the fix

**`R*USDT` does not mean tokenized stock.** Wrong 28 times: 26 crypto pairs
swallowed (`RLCUSDT` is iExec, plus RENDER, RONIN, RAY, ROSE...) and 2 stocks
missed (`PRESPCXUSDT`, `PREOPAIUSDT`). Use `symbolType`. A test asserts the
heuristic fails, so it cannot come back as a shortcut.

**`orderbook` returns an object, not a list**, and its keys are `b` and `a`, not
`bids`/`asks`. The first version of `market._get` required a list and would have
rejected every depth call.

**Numbers arrive as strings.** `bid1Price` is `"359.05"`. Blank means the venue
sent nothing - which is different from zero and must stay different.

**`orderbook` and `tickers` disagree, and silence is not zero.** RPBRUSDT and
RSYKUSDT return `{"a": [], "b": []}` from the depth endpoint while the ticker
quotes them two-sided with over 2M USDT of 24h turnover. The first estimator
printed "NO EXIT" for both - a venue quirk about to be shipped as the project's
headline finding. `market.depth_or_touch` now falls back to the ticker's touch and
labels the source, so an unquotable book and an unreported one can never render as
the same number. Regression-tested in `tests/test_exitcost.py::SilenceIsNotZero`.

**`ts` in a ticker row is per-symbol**, not the fetch time. Both are stored:
`snap_ts` is ours, `venue_ts` is theirs. A stale `venue_ts` is a dead book, which
is a liquidity signal rather than a bug.

## Environment

- **No API key is needed or wanted.** If a credential ever appears in this repo,
  something has gone wrong.
- The LLM half, when it arrives, uses the hackathon Qwen endpoint:
  `https://hackathon.bitgetops.com/v1`, model `qwen3.8-max`, via `QWEN_API_KEY`.
  That is the *only* secret this project should ever hold, and it is unrelated to
  Bitget's trading API key.
- Python 3.10+, **stdlib only** at runtime. `ruff` and `mypy` are dev tools.
- The sibling project's `bitget-signal` MCP probe found **17 of 19 tools return
  `ConnectTimeout`** - their server cannot reach FRED, Yahoo, CoinGecko, RSS or
  Finnhub, though those hosts answer fine from an ordinary machine. Only
  `technical_analysis` and `crypto_derivatives` work. **Do not design around
  those skills.** Bitget's own public API is the integration surface.

## The venue's two volume feeds disagree on stocks

Sum 24 hourly candles for a symbol and hold it against that symbol's rolling
`turnover24h`:

| | ratio |
|---|---|
| BTCUSDT, ETHUSDT, SOLUSDT | **0.97 - 0.98** |
| RMSFTUSDT | 4.2 |
| RAAPLUSDT / RTSLAUSDT | 5.9 / 6.1 |
| RNVDAUSDT / RPBRUSDT | 8.5 / 9.0 |
| RSYKUSDT | **15.7** |

Base volume and quote volume diverge by the SAME factor, so it is not a units or
price error. The factor differs per symbol, so it is not a fixed multiplier. Which
feed is right cannot be settled from outside.

`validate.feed_agreement` gates on this and EXCLUDES a symbol rather than
averaging over a number already shown to be unreliable. Do not remove that gate to
get a bigger sample: a validation that validates against bad data is worse than
none, because it produces a figure people trust.

## The append-only store has exactly one writer

The gzipped daily snapshot is binary, so git cannot merge it. Running
`crawl --once` locally while the Action was mid-run produced a genuine rebase
conflict on `state/snapshots/*.csv.gz` and `state/manifest.jsonl`.

Resolution: **the runner's copy always wins.** It holds the continuous record; a
local snapshot is scaffolding. During a rebase that means `git checkout --ours --
state/` (in a rebase, "ours" is the upstream being replayed onto).

Better: do not write to `state/` locally at all while the Action runs. Point
`EGRESS_STATE` at a scratch directory for local work.

## Rendering and screenshots

**Headless Chromium lays out ~85 px wider than `--window-size`.** A 400 px window
renders a 485 px viewport but screenshots at 400 px, so the right edge is CROPPED
and it looks exactly like horizontal overflow. Two hours could be lost redesigning
a layout that was never broken. Measure instead: inject a probe that reports
`document.documentElement.clientWidth`, `scrollWidth`, and any element whose right
edge exceeds the viewport. 485 px is this build's floor, so narrower than that
cannot be measured here at all.

### A closed `<details>` hides its content with `content-visibility`

The menu is one markup in two shapes: inline links on a wide screen, a native
disclosure on a narrow one, and no script either way. Overriding
`.menu ul{display:flex}` makes the links paint on desktop, but the `<details>`
box still measures **zero wide**, because Chromium hides the content through
`::details-content{content-visibility:hidden}` rather than through the child's
own `display`. The links therefore painted out of a zero-width box and off the
right edge of the header at every desktop width. The fix is to override the
pseudo-element itself:

```css
.menu::details-content{content-visibility:visible;display:contents}
```

Engines without `::details-content` ignore the rule and fall back to the older
`display:none`-on-content behaviour, which lays out correctly, so this is a safe
progressive enhancement rather than a dependency.

Caught only because the responsiveness check measures `getBoundingClientRect()`
per element instead of comparing `scrollWidth` to `clientWidth`: the header did
not widen the page, so the page-level check was green while five pages had
unreachable navigation. **`scrollWidth === clientWidth` is not proof that
nothing is off-screen.**

### Six inline tabs stop fitting long before a phone

The mobile breakpoint was 700 px; the menu ran out of room at about 900. The
header collapses to the pill one breakpoint earlier than the layout does, which
is why there are two media queries rather than one.

### The site went blank at midnight UTC and still claimed fifty snapshots

`facts.by_snapshot()` defaulted to `date.today()`. The footer counts the
manifest, so it kept reporting the whole record; every table on the site read
one day and emptied the moment the date rolled over, staying empty until the
first snapshot of the new day landed. Found by opening the built page the
morning after a crawl and seeing a site that asserted 50 snapshots and showed
nothing.

Omitting the day now means the WHOLE record (`store.days()` reads the manifest,
not the filenames, so an unfinished day is invisible for the same reason its
rows are). Passing a day still narrows, which is what `validate` wants.

**The general rule: two numbers on one page that come from different readers of
the same record must be tested against each other.** `test_facts.py` now asserts
the summary count equals the manifest count; had that test existed, the bug
could not have shipped.

### A landing page is not a table of contents

The landing page grew four cards describing the four other pages - a sitemap
restating the menu directly above it, and on a phone an endless stack. Replaced
with one comparison built from the record. A landing page makes one argument;
navigation is the menu's job.

### NaN is a valid Python float and an invalid JSON token

`json.dumps({"x": float("nan")})` emits a bare `NaN`. Every conforming parser
rejects it, so the browser threw a SyntaxError and the desk showed "could not be
reached" for an answer the server had computed correctly. The client even had a
`q.total_bp === q.total_bp` NaN guard - dead code that could never fire, which is
what a contract nobody tested end to end looks like.

`to_record()` emits `null` plus a `quotable` flag, and `api/ask.py` serialises
with `allow_nan=False` so a regression is a stated 500 rather than a body nobody
can read. **A boundary that crosses a serialiser needs a test that actually
serialises.**

### A docstring is not an implementation

`desk.answer` said "every failure is a stated answer, never an exception" and
then let `MarketUnavailable` through to the serverless handler. The *redundant*
second fetch was guarded; the essential first one was not. Where a function
promises total behaviour, there is now a test class named after the promise.

### The reader/writer race was real, and the reader was innocent-looking

The crawl loop appends while the page build reads and `git add` stages. A
half-written gzip member raises `EOFError` - which the build swallowed via
`|| true` and committed a stale site behind a fresh-looking commit. Fixed at
three layers: members compressed up front and committed under `flock`, readers
take a shared lock, and a torn tail costs the torn snapshot rather than the
file. **`|| true` on a build step converts a loud failure into a silent one.**

### Test what you claim, or stop claiming it

`pyproject` said `>=3.10`; CI tested only 3.11. The claim happened to be true -
198 tests pass on 3.10 through 3.13 - but nothing was checking. CI now runs the
matrix it advertises.

### An answer is a judgement, not a field dump

The desk's first output listed nine labelled variables - `DEPTH SOURCE:
orderbook`, `ONE CLIP: 18 bp` - and left the reader to interpret them. Every
number was right and the panel still failed at its job, because "15 bp" means
nothing without something to compare it to.

It leads with a verdict now (cheap / about typical / expensive / very
expensive), then the comparison that justifies it, then whether to act. The
bands are a judgement about wording and are named in one place; the figure
behind them is `state/benchmark.json`, derived from the record at build time,
so the comparison moves when the record moves and is never typed. The same
16 bp reads "cheap" overnight and "expensive" while New York is open - which is
the entire point of comparing per phase.

Everything that was on the panel is still one tap away under "Show the working".
Honesty was never the problem; ordering was.

### Nothing executed the client script

Replacing `render()` deleted `var inFlight` and `fail()`, which lived between
it and `ask()`. 201 Python tests stayed green, ruff stayed green, the page
built, and the desk threw `inFlight is not defined` on the first click - it was
completely broken in production and every gate said fine.

`tools/check_desk.mjs` drives the real script in a real browser against four
recorded answer shapes, checks the panel renders, checks the button is released,
and checks an error message is escaped. Proven to catch both that bug and an
unescaped error path. **A syntax check is not an execution.**

## Working rules

1. **Probe before designing.** Every assumption above that turned out wrong was
   read from documentation. Call the endpoint, look at the bytes.
2. **Re-run every gate AFTER the last edit, and read the exit code.** CI went red
   on RUF012 in a test class appended after the lint run - the "all green" was
   true of a state that no longer existed. Gates prove nothing about code written
   since they ran. This is the second time the same mistake has been made in this
   codebase's lineage; it is written down so it is the last.
3. **A test that has never failed proves nothing.** Perturb it, watch it go red,
   restore. Done for the manifest gate and the classification.
4. **Collection is separate from interpretation.** The crawler records; analysis
   decides. A wrong calendar must never be able to spoil the week of data.
5. **No typed literals for measured numbers.** Any figure in a document or page
   comes from the record, or it goes stale silently and nobody notices.
6. **Label everything `observed` or `estimated`.** A quote is not a fill.
7. **Measure the layout, do not look at it.** Screenshots crop; a headless
   window is not the viewport. Every responsiveness claim in this project comes
   from reading `getBoundingClientRect()` on every element at eight widths, and
   from opening the menu and checking where it landed.
8. **Build the page and look at it before believing the tests.** 108 unit tests
   were green while the live site showed an empty evidence table: every test
   fed the renderer a fixture, and no test ever rendered from the real record.
9. **A gate that lives on my machine is not a gate.** The layout check that
   found the zero-width menu sat in /tmp for a week. It is `tools/check_layout.mjs`
   and a CI job now, and it has been proven to fail.
