# X post — required, and an entry without it is invalid

Must contain **`#BitgetHackathon`** and **`@Bitget_AI`**. Post from the account
entering the hackathon, then paste the URL into `docs/SUBMISSION.md`.

Every number below is from `state/` as measured 2026-09-22 and is on the live
site. **Re-check before posting** — the crawl moves them every twenty minutes,
and a post is the one artifact that cannot be edited after the fact.

Current values to verify against <https://egress-v1.vercel.app/evidence>:

| Claim in the drafts | Where it comes from |
|---|---|
| 2,127 tokenized US stocks | `state/universe.json`, `symbolType == "stock"` |
| 1,967 snapshots | `facts.coverage.snapshots` |
| 6.1 bp open → 54.5 bp overnight (8.9×) | phase table, stocks listed 30d+ |
| 644 bp overnight | phase table, stocks listed <30d |
| crypto 12.0 → 11.8 (0.98×) | phase table, crypto control |

---

## Option C — shortest, leads with the question (258 chars) ← recommended

```
What does it cost to LEAVE a tokenized stock at 3am?

Measured: 8.9x the daytime spread. Crypto on the same venue doesn't move at all.

Egress answers in English, walking the real book. No order ever placed.

egress-v1.vercel.app

#BitgetHackathon @Bitget_AI
```

Why this one: the control ("crypto doesn't move at all") is the strongest
sentence in the project and it survives compression. It is the line that turns
a spread observation into a finding.

## Option B — the 3am framing (295 chars)

```
You bought a tokenized stock at 2pm. It's 3am and you want out.

The spread you entered on was 6.1 bp. Right now it's 54.5 bp. If the name listed this month, 644 bp.

Egress walks the real order book and tells you the number before you need it.

egress-v1.vercel.app

#BitgetHackathon @Bitget_AI
```

## Option A — leads with the venue (329 chars)

```
Bitget lists 2,127 tokenized US stocks. One click to buy.

Nobody tells you what it costs to leave.

1,967 snapshots: overnight spreads widen 8.9x vs market hours. Crypto, same venue, same engine: 0.98x.

So it's not the venue. It's the closed market underneath.

Ask in English: egress-v1.vercel.app

#BitgetHackathon @Bitget_AI
```

---

## If a thread is allowed

1. Option C as the opener.
2. *"Why the crypto control matters: same venue, same matching engine, same wire.
   If the widening were our crawler or the clock, crypto would widen too. It
   doesn't — 12.0 bp open, 11.8 bp overnight. The widening is specific to
   instruments whose reference market is shut."*
3. *"What it won't do: place an order, or pretend. When the book can't fill your
   size it quotes a floor marked `>` instead of a number. Two Bitget Skills are
   on the answer path and the news one is wired so it cannot move the price —
   there's a test for that."*
4. *"One frozen run, readable with JavaScript off:
   egress-v1.vercel.app/evidence#task"*

## Do not claim

- Any return, P&L or profit. Egress measures a cost and does not trade.
- That the overnight finding is validated **as a fill** — it holds as a quote.
  Six liquid symbols are excluded because the venue's own volume feeds disagree
  about them by 8×–20×.
- A universe count without the definition behind it, if anyone asks.
