# Egress

**Bitget lists 1,175 tokenized US stocks. You can enter any of them in one click.
Egress measures what it costs to leave.**

Built for the Bitget AI Base Camp Hackathon S2 — AI Trading Desk, Execution Assistance.

---

Every other tool for tokenized equities is built for the same ten names. The risk
lives in the other 1,165: listed in one click, and in practice unexitable. You
find out at the moment you need out.

Egress crawls the whole listed universe every five minutes and answers a question
nobody else is asking — *at my size, what does leaving actually cost, and when is
it cheapest?*

## Status

Day 1 of 7. The crawler is collecting; the estimator and the desk are not built.

```
python -m egress.crawl --once        one snapshot
python -m egress.crawl --loop        keep going (5 min cadence)
python -m egress.crawl --coverage    what the record holds, including gaps
python -m unittest discover -s tests
```

No API key. No account. Every endpoint used is public.

## The first measurement

One snapshot, 2026-09-14, US market closed:

| | median spread | p90 |
|---|---|---|
| Tokenized stocks (1,170) | **151.3 bp** | 1,485.8 bp |
| Crypto control (585) | **10.8 bp** | 31.9 bp |

Same venue, same matching engine, same fees. **One observation is not a finding** —
which is what the week of crawling is for, and why the crypto pairs are stored
alongside the stocks as a control.

## Reading more

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — the five decisions that matter, and why
- [`PLAN.md`](PLAN.md) — schedule, cut list, what is being tested
- [`MEMORY.md`](MEMORY.md) — verified facts and the traps already hit

## Licence

MIT — see [`LICENSE`](LICENSE).
