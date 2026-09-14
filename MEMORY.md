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

## Working rules

1. **Probe before designing.** Every assumption above that turned out wrong was
   read from documentation. Call the endpoint, look at the bytes.
2. **A test that has never failed proves nothing.** Perturb it, watch it go red,
   restore. Done for the manifest gate and the classification.
3. **Collection is separate from interpretation.** The crawler records; analysis
   decides. A wrong calendar must never be able to spoil the week of data.
4. **No typed literals for measured numbers.** Any figure in a document or page
   comes from the record, or it goes stale silently and nobody notices.
5. **Label everything `observed` or `estimated`.** A quote is not a fill.
