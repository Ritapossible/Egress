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
