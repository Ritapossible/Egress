# Egress — Bitget AI Base Camp Hackathon S2

**Track 3 · AI Trading Desk / Execution Assistance.**

One page, mapping what the handbook asks for to the file that does it. Every
row names something you can open and check; nothing here is a claim about
intent.

**Live:** <https://egress-v1.vercel.app> · **Source:**
<https://github.com/Ritapossible/Egress>

---

## The thesis in four sentences

Bitget lists 2,127 tokenized US stocks you can enter in one click. The market
that prices the share underneath them is open 32.5 hours of every 168, and when
New York is shut a market maker cannot hedge, so the quote widens and the
holder who needs out pays for it. Egress measures what leaving costs — at your
size, on your timetable — from the venue's own order book, and names the
positions that have no exit at all. It never places an order.

## Bitget Skills, and what each one actually returns

| Skill | Where it runs | What it returned |
|---|---|---|
| `bitget-mcp-server` → `equity_price_quote` | `egress/mcp.py`, called from `desk.answer()` on every request | **Answering.** Supplies the listed share price behind the token, which is where the basis figure comes from. Without it the desk can price an exit but cannot say what the position was worth. |
| `bitget-signal` → `news_feed/latest` | `egress/signal.py`, called from `desk.answer()` on a 6s fuse | **Reachable, carrying nothing.** 44 feeds, 0 articles. The desk prints that rather than assembling a briefing out of an empty feed. |

**bitget-signal is deliberately non-load-bearing, and that is enforced rather
than promised.** The exit cost comes from the venue's own book; news cannot move
it. The block is built after the number is already fixed, the desk wraps the
call so a bug in there cannot 500 a priced answer, and
`SignalIsContextAndNothingElse` in `tests/test_desk.py` asserts the entire
answer is byte-identical whether the service replies, returns nothing, or dies.
A news service wired into a pricing answer is a liability the moment it is slow
or wrong; this one cannot be.

The scheduled probe in `egress/signal.py` runs on a longer 25s fuse, because
telling "the feed had nothing" apart from "we gave up waiting" is worth the wait
when nobody is watching a spinner. On the Ask path it is not.

## Handbook requirement → file

| Requirement | Where | Note |
|---|---|---|
| Accessible demo, no key needed | <https://egress-v1.vercel.app> | The desk answers without a key of yours. `GET /api/ask` reports `reader_configured: true`. |
| One complete research task, question → actionable insight | `evidence.html#task` | Asked against the live API and **frozen into static HTML**, so it reads with JavaScript off. Captured by `tools/freeze_task.py` into `state/research_task.json`; the page renders from that file rather than from retyped prose. |
| LLM in the loop | `egress/llm.py` | Qwen `qwen3.8-max` compiles the question into `{ticker, notional}` and **nothing else**. Every number in the answer comes from the book. |
| Data sources | `egress/market.py`, `egress/crawl.py` | The venue's own spot endpoints. The crawl runs roughly every 20 minutes and commits what it saw. |
| Research quality | `evidence.html`, `validation.html` | Phase medians across the whole quoted universe, plus the names the method **cannot** validate and why. |
| Fail-closed behaviour | `egress/desk.py`, `tests/test_desk.py` | A 503, an empty book or an unlisted ticker each come back as a stated error, never as a silent zero and never as an exception through the handler. |

## What the LLM does, and what it cannot do

`qwen3.8-max`, via `hackathon.bitgetops.com/v1`, at temperature 0.

It reads the question and returns a ticker and a notional. That is the whole
contract. There is no field in its output for a price, a cost, a spread or a
recommendation, and the desk does not read one. Ask it *"what does leaving 40k
of TSLA cost?"* and it compiles `{TSLA, 40000}`; the 22 bp comes from walking
the venue's book.

With no key the reader is unavailable and the desk says so rather than guessing
a ticker.

## Known limits, stated because a judge will find them

- **The liquid names are not validated.** Six symbols — NVDA, TSLA, AAPL, MSFT,
  SYK, PBR — are excluded from `validation.html` because two of the venue's own
  volume feeds disagree about them: candle volume runs roughly 9× to 20× the 24h
  turnover its ticker reports for the same symbol. Which feed is right is not
  settleable from outside, and scoring against a number that may be wrong is
  worse than not scoring. The overnight widening holds **as a quote** across
  every name the crawl sees; it is **not** established **as a fill** on the names
  most people hold. Said on `evidence.html#unvalidated` rather than left to be
  found.
- **bitget-signal has no articles.** Reachable, catalogues answer, live feed
  empty. Shown as empty.
- **Fills are modelled, not executed.** Egress places no orders and holds no
  trading credential.
- **The X post is not up.** Required, and an entry without it is invalid.

## Verify it yourself

```bash
git clone https://github.com/Ritapossible/Egress && cd Egress
python3 -m unittest discover -s tests   # no key, no network
curl -s https://egress-v1.vercel.app/api/ask
curl -s -X POST https://egress-v1.vercel.app/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"q": "what does leaving 40k of TSLA cost?"}'
```

The universe count on any page is `state/universe.json`, rebuilt by the crawl.
`2,127` means rows with `symbolType == "stock"` from
`/api/v3/market/instruments?category=SPOT` — the v2 public symbols endpoint
carries no such field, which is why a count taken there will not match.
