# Egress

**Bitget lists tokenized US stocks you can enter in one click. Egress measures
what it costs to leave.**

Built for the Bitget AI Base Camp Hackathon S2 - AI Trading Desk, Execution
Assistance.

Live: [egress-v1.vercel.app](https://egress-v1.vercel.app)

---

Every other tool for tokenized equities is built for the same ten names. The risk
lives in the rest: listed in one click, and in practice unexitable. You find out
at the moment you need out.

Egress crawls the whole listed universe every five minutes and answers a question
nobody else is asking - *at my size, what does leaving actually cost, and when is
it cheapest?*

## What it does

- **Crawls** every listed spot instrument on a five minute cadence into an
  append-only, manifest-gated record.
- **Estimates** the cost of an exit by walking the live book from the mid, adding
  the taker fee, and marking a floor where the displayed book runs out.
- **Validates** the quotes against the prints, and refuses to compare any symbol
  whose own two volume feeds disagree.
- **Answers** a plain-English question at the desk, live at
  [`POST /api/ask`](https://egress-v1.vercel.app). The reader picks a ticker and
  a size; every number after that is computed by code.
- **Cross-checks itself** by pricing the same exit a second time through a
  different SDK, and publishes where the two disagree.

## The Bitget Skills, and what each one returns

Stated rather than listed, because "integrated" and "answering" are different
claims and only one of them is checkable.

| Skill | Where | What it returns today |
|---|---|---|
| `bitget-mcp-server` → `equity_price_quote` | `egress/mcp.py`, on every desk answer | **Answering.** The listed share price behind the token, which is where the basis figure comes from. |
| `bitget-signal` → `news_feed/latest` | `egress/signal.py`, on the Ask path, 6s fuse | **Reachable, carrying nothing.** 44 feeds, 0 articles. The desk prints that rather than assembling a briefing out of an empty feed. |
| **Agent Hub CLI** → `market/orderbook` | `egress/hub.py`, every crawl | **Answering, and used as an adversary.** See below. |

**The news Skill cannot move the number.** The exit cost comes from the venue's
order book; news has no business touching it. The block is built after the cost
is already fixed, and a test asserts the entire answer is byte-identical whether
that service replies, returns nothing, or dies. A news feed wired into a pricing
answer is a liability the moment it is slow or wrong.

**The Agent Hub is not a wrapper around the REST call this project already
makes - it is the adversary to it.** Everything here comes through one HTTP
client, and a bug in that client would look exactly like a property of the
market. That is an uncomfortable position for a project whose argument is that
the venue's own numbers do not always agree with each other. So the same exit is
priced again through a different SDK in a different process, costed by the same
code so any gap is the book rather than the arithmetic. Agreement does not prove
the cost is right - both clients read the same exchange and would inherit the
same error - it rules out our own transport, which was previously unchecked.
[The comparison is published](https://egress-v1.vercel.app/evidence#hub),
disagreements included.

## Run it

Python 3.10 or newer (CI tests 3.10 to 3.13). No runtime dependencies - the standard library does the
HTTP, the gzip and the CSV.

```
python -m egress.crawl --once        one snapshot of the whole universe
python -m egress.crawl --loop        keep going, five minute cadence
python -m egress.crawl --coverage    what the record holds, including gaps
python -m egress.page                rebuild the site into docs/
python -m unittest discover -s tests
```

No API key. No account. Every endpoint the crawler uses is public. The one secret
in the project is the reader key for the desk, and it lives in the serverless
function, never in a page.

## What it found

Median spread on tokenized US stocks, by market phase, against crypto pairs on
the same venue as a control. **The live figures are on
[the evidence page](https://egress-v1.vercel.app/evidence)** and are regenerated
from the record on every crawl - nothing in this README is a measurement,
because a number typed into a document goes stale the moment the record moves
and nobody notices.

What the record shows so far: the spread on a tokenized stock widens by roughly
an order of magnitude once New York closes, while the crypto control on the same
matching engine and the same fee schedule does not move. Same venue, same
engine, same fees - so the effect is not venue-wide.

**How long a name has been listed matters more than anything else measured
here.** The headline medians cover names listed thirty days or more, with
recent listings reported beside them rather than mixed in. That split is not
tidiness: Bitget listed 480 tokenized stocks in a single wave and the median
taken across every quoted name jumped by more than half, with nothing happening
in the market at all. Split apart, recently listed names cost several times more
to leave overnight than established ones - and a new listing is exactly the
position a holder is least likely to know is expensive to leave. Both cohorts
are published, and so is the blended figure, so the composition effect stays
visible instead of being quietly corrected away.

The listed universe is re-read hourly while the crawl runs, and the site says
how old that count is whenever it is worth saying. Listings arrive in bulk; a
count nobody can see the age of is the kind of stale number this project exists
to avoid.

**A few days is not a study.** Every table on the site prints the snapshot count
behind it and the gaps in the record, so you can see how thin it still is.

## Reading more

- **[One research task, frozen](https://egress-v1.vercel.app/evidence#task)** -
  a real run of the desk, captured and written into the page as static HTML so it
  reads with JavaScript off
- **[What is not validated](https://egress-v1.vercel.app/evidence#unvalidated)** -
  the six symbols this method refuses to score, and why
- The [docs page](https://egress-v1.vercel.app/docs) - quickstart, data format,
  endpoint, limitations, glossary
- [`docs/HACKATHON.md`](docs/HACKATHON.md) - each handbook requirement mapped to
  the file that satisfies it
- [`docs/SUBMISSION.md`](docs/SUBMISSION.md) - the six-part description
- [`ARCHITECTURE.md`](ARCHITECTURE.md) - the decisions that matter, and why
- [`PLAN.md`](PLAN.md) - schedule, cut list, what is being tested
- [`MEMORY.md`](MEMORY.md) - verified facts and the traps already hit

## Licence

MIT, see [`LICENSE`](LICENSE).
