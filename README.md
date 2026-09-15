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

What the record shows so far: the spread on a tokenized stock widens by more
than an order of magnitude once New York closes, while the crypto control on the
same matching engine and the same fee schedule does not move. Same venue, same
engine, same fees - so the effect is not venue-wide.

**A few days is not a study.** Every table on the site prints the snapshot count
behind it and the gaps in the record, so you can see how thin it still is.

## Reading more

- The [docs page](https://egress-v1.vercel.app/docs) - quickstart, data format,
  endpoint, limitations, glossary
- [`ARCHITECTURE.md`](ARCHITECTURE.md) - the decisions that matter, and why
- [`PLAN.md`](PLAN.md) - schedule, cut list, what is being tested
- [`MEMORY.md`](MEMORY.md) - verified facts and the traps already hit

## Licence

MIT, see [`LICENSE`](LICENSE).
