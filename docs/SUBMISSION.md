# Submission — Bitget AI Base Camp Hackathon S2

Paste each part into the matching form field.

| Field | Value |
|---|---|
| **Track** | AI Trading Desk |
| **Sub-theme** | Execution Assistance |
| **Project** | Egress |
| **Demo** | <https://egress-v1.vercel.app> |
| **Code** | <https://github.com/Ritapossible/Egress> |
| **X post** | ⚠️ *fill in — must include `#BitgetHackathon` and `@Bitget_AI`* |

**Every figure below was measured at 2026-09-22 17:09 UTC and is a snapshot.**
The crawl re-derives all of them roughly every twenty minutes and the live site
shows the current values; nothing here is typed by hand into prose. Where a
number here and a number on the site disagree, the site is right and this file
is stale.

---

## 1 · Thesis

**Bitget lists 2,127 tokenized US stocks you can enter in one click. The market
that prices the share underneath them is open 32.5 of every 168 hours. Nobody
tells you what it costs to leave, and the answer changes by a factor of nine
depending on what time you ask.**

Measured across 1,967 snapshots and 4,466,468 rows since 2026-09-14:

| | US market open | Overnight | Multiple |
|---|---|---|---|
| Tokenized stocks, listed 30d+ | **6.1 bp** | **54.5 bp** | **8.9×** |
| Tokenized stocks, listed <30d | 10.2 bp | **644.0 bp** | 63.1× |
| Crypto (control) | 12.0 bp | 11.8 bp | **0.98×** |

**The control is the finding.** Crypto trades on the same venue, through the
same matching engine, over the same wire, and does not move at all between
sessions. So the widening is not the venue, the crawler, the clock or the
measurement — it is specific to instruments whose reference market is shut.
When New York closes, a market maker cannot hedge the share, and the quote
widens to carry that risk.

**Newly listed names are a different product.** Under thirty days old, the
overnight median is 644 bp — 10.2 bp while New York is open. A holder who
bought in the afternoon and needs out at 3am is in a different market from the
one they entered.

Egress measures what leaving costs — at your size, on your timetable — by
walking the venue's own order book, and names the positions that have no exit
at all. **It never places an order.**

## 2 · Target user and product value

**Someone holding a tokenized US stock who wants to know the exit before they
need it.**

| | |
|---|---|
| Segment | Retail to pro, self-directed. **Not** market makers, **not** HFT |
| Position | 1,000–100,000 USDT in one name |
| The moment | Either before entering, or at 3am when they want out |
| What they have today | A price, a chart, and no idea what size the book can absorb |

The venue shows a mid and a 24h volume. Neither answers *"what do I actually
get if I sell 40,000 USDT of this right now?"* — and for a tokenized stock at
3am the gap between the mid and the answer is the whole question.

**The value, stated plainly:** ask in English, get the cost of leaving, walked
from the real book, with the fee named separately, the depth behind it stated,
and an explicit list of what the number cannot see. When the book cannot fill
the order, it says so and quotes a floor rather than inventing a price.

## 3 · Validation data and key metrics

**The record.** 1,967 snapshots, 4,466,468 rows, 195.5 hours of continuous
observation since 2026-09-14, across 2,710 listed instruments (2,127 tokenized
stocks, 581 crypto pairs, 2 metals). 35 gaps, each one printed on the evidence
page rather than smoothed over.

**Method.** Walk the book from the mid, level by level, until the order is
filled or the book is exhausted. Add 10 bp assumed taker fee — the only typed
number in the system. Mark the answer `>` when the book dies before the order
does. No midpoint fiction, no assumed refill.

**What the count means.** `symbolType == "stock"` from
`/api/v3/market/instruments?category=SPOT` — the venue's own classification,
all online, 2,127 distinct base coins. The v2 public symbols endpoint returns
the same 2,710 rows and carries no `symbolType` field, which is why a count
taken there will not match; split by ticker prefix instead and you get 2,150.

### The honest state of validation

**Prediction-vs-print scoring currently covers the three crypto controls and
no tokenized stock at all.** That is the single biggest limit in this project
and it is stated here rather than buried.

- **6 of 9 symbols are excluded**, including NVDA, TSLA, AAPL and MSFT, because
  **two of the venue's own volume feeds disagree about them**: candle volume
  runs **8.2× to 18.2×** the 24h turnover its own ticker reports for the same
  symbol. Which feed is right is not settleable from outside this venue, and
  scoring a prediction against a number that may be wrong is worse than not
  scoring it.
- On the symbols that can be scored, printed volume runs a median **37×** the
  depth visible at the touch, over 219 bars. That ratio is why a spread is not
  a cost and why the desk walks the book instead.

**So the overnight widening holds as a quote, not yet as a fill.** It is
measured on every name the crawl can see; it is not yet confirmed against
executions on the liquid names. Those are the ones where it matters most.

**No return claim is made.** Egress does not trade, does not backtest a
strategy, and has no P&L. It measures a cost.

## 4 · Progress

**Built and working:** the crawler (running roughly every twenty minutes,
committing what it saw), the universe classifier, the book-walking exit-cost
estimator, the live desk behind `POST /api/ask`, the Qwen reader, both Bitget
Skills on the answer path, the phase study, the validation page including what
it cannot validate, and a public site that states its own limits.

**Not built:** order placement (by choice — the project holds no trading
credential), multi-position portfolios, deep-book history.

**Problems found and published rather than quietly corrected:**

1. **The R-prefix heuristic was wrong 27 ways.** Treating `R*USDT` as a
   tokenized stock swallows 25 ordinary crypto pairs (`RLCUSDT` is iExec, not
   Royal Caribbean) and misses two stocks carrying no prefix. A liquidity study
   built on it would have reported crypto liquidity as tokenized-stock
   liquidity. Fixed by reading the venue's own `symbolType`.
2. **Two of the venue's volume feeds disagree.** Found while validating, not
   assumed. It is the reason six symbols are excluded, and it is on the page.
3. **The desk used to raise through the handler.** A 503 became an HTML 500 the
   client could not read an error out of. Now every failure is a stated one.
4. **`NaN` serialised as invalid JSON.** A cost the book could not price broke
   the browser parser instead of showing the honest answer already computed.
5. **An outside review gave the exclusion ratios as "646× to 5,902×".** They
   are 8.2× to 18.2×, and of a different quantity. The figures on the page are
   now read from the validation record rather than retyped.

**Held back deliberately:** the Agent Hub integration. Read-only depth through
the Hub would wrap REST this project already calls directly, which adds a logo
and no capability. Stated rather than silently skipped.

## 5 · Deliverables

| | |
|---|---|
| **Live demo** | <https://egress-v1.vercel.app> — no key of yours needed |
| **Frozen research task** | `/evidence#task` — one real run, captured from the live API into static HTML, readable with JavaScript off |
| **Evidence** | `/evidence` — the phase table, the gaps, and what is not validated |
| **Method** | `/method` — how the book is walked |
| **Validation** | `/validation` — including the symbols it refuses to score |
| **Handbook map** | `docs/HACKATHON.md` — each requirement to the file that satisfies it |
| **Source** | <https://github.com/Ritapossible/Egress> |
| **API** | `POST /api/ask` with `{"q": "..."}` |
| **Tests** | `python3 -m unittest discover -s tests` — network-free, key-free |

## 6 · Take on AI trading

**The model should read the question, not answer it.**

Egress gives Qwen exactly one job: turn *"what does leaving 40k of TSLA cost?"*
into `{TSLA, 40000}`. There is no field in its output contract for a price, a
spread, a cost or a recommendation, and the desk does not read one. Every number
in the answer is walked from the venue's book by code that can be checked.

That division is not a limitation we are apologising for — it is the whole
design. Natural language is genuinely hard and models are genuinely good at it.
Arithmetic over an order book is genuinely easy and models are genuinely bad at
it. Handing the model the part it is good at, and refusing it the part where a
plausible-looking wrong number costs someone real money, is what makes the
answer trustworthy enough to act on.

The same principle governs the second Skill. `bitget-signal` is on the answer
path, and it **cannot move the number** — the block is built after the cost is
fixed, and a test asserts the entire answer is byte-identical whether the news
service replies, returns nothing, or dies. Today it returns nothing, and the
desk prints that rather than assembling a briefing out of an empty feed. A model
that fills silence with something is the failure mode this field has to design
against.

---

## Role of the LLM (separate form field)

**Qwen `qwen3.8-max`**, via `https://hackathon.bitgetops.com/v1`, temperature 0.

**What it does:** compiles a plain-English question into a ticker and a notional.
That is the entire contract.

**What it cannot do:** there is no price, size, side or recommendation field in
its output, and no code path reads one. With no key configured it reports itself
unavailable and the desk says so rather than guessing a ticker.

**Verification:** ask the live API anything and compare the compiled spec in the
response against the numbers beside it — the numbers come from the book.
