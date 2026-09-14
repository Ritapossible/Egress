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
- **Answers** a plain-English question at the desk. The reader picks a ticker and
  a size; every number after that is computed by code.

## Run it

Python 3.11 or newer. No runtime dependencies - the standard library does the
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

## The first measurement

One snapshot, 2026-09-14, US market closed. A dated observation, not a finding:

| | median spread | p90 |
|---|---|---|
| Tokenized stocks (1,170) | **151.3 bp** | 1,485.8 bp |
| Crypto control (585) | **10.8 bp** | 31.9 bp |

Same venue, same matching engine, same fees. **One observation is not a finding**,
which is what the week of crawling is for, and why the crypto pairs are stored
alongside the stocks as a control. Every figure on the live site is regenerated
from the record on each crawl; none is typed.

## Reading more

- The [docs page](https://egress-v1.vercel.app/docs) - quickstart, data format,
  endpoint, limitations, glossary
- [`ARCHITECTURE.md`](ARCHITECTURE.md) - the decisions that matter, and why
- [`PLAN.md`](PLAN.md) - schedule, cut list, what is being tested
- [`MEMORY.md`](MEMORY.md) - verified facts and the traps already hit

## Licence

MIT, see [`LICENSE`](LICENSE).
