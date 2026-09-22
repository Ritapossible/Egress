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

## Option D — long form: problem, solution, design (~1,080 chars) ← recommended

Bitget's requirement is that the post *introduces the product*, so this one is
built to do that rather than to fit 280 characters. Problem first, because the
question is the hook; then what it is; then the one design decision worth
defending.

```
Bitget lists 2,127 tokenized US stocks. You can buy one in a single click.

Nothing tells you what it costs to LEAVE.

So I measured it. 1,967 snapshots, 4.4M rows, the whole listed universe every 5 minutes:

▸ Established names: 6.1 bp spread while New York is open → 54.5 bp overnight. 8.9x.
▸ Listed under 30 days: 644 bp overnight.
▸ Crypto on the same venue: 12.0 → 11.8. It doesn't move.

That control is the whole finding. Same exchange, same matching engine, same fees — so the widening isn't the venue. It's the closed market underneath.

Egress is a desk that answers this in English.

"what does leaving 40k of TSLA cost?" → it walks the real order book, level by level, and tells you.

The design choice I'd defend hardest:

The LLM only reads the question. Qwen turns that sentence into {TSLA, 40000} and stops. It has no field for a price, a cost or a recommendation. Every number comes from the book.

Models are great at language and bad at arithmetic over an order book. A plausible-looking wrong number costs someone real money.

When the book can't fill your size, it says so and quotes a floor — instead of inventing a price.

egress-v1.vercel.app

#BitgetHackathon @Bitget_AI
```

### Optional reply, for the engineering depth

```
Three Bitget Skills, and one of them is wired to argue with me:

▸ bitget-mcp-server → the listed share price behind the token
▸ bitget-signal → news, on a 6s fuse, and it CANNOT move the number. A test asserts the answer is byte-identical whether it replies, returns nothing, or dies.
▸ Agent Hub CLI → prices the same exit through a different SDK

That last one caught something. 6 of 7 symbols agree to the basis point. But two names return no two-sided book from the Hub at all — the same two my own validation had to exclude. Second client, same thinness, found independently.

It does NOT prove my numbers are right. Both clients read the same exchange and would inherit the same error. It rules out my own HTTP layer, which was previously unchecked.

Also published: the 6 symbols I can't validate, and why.
```

---

## Option C — shortest, leads with the question (258 chars)

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
