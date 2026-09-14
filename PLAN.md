# Plan

**Egress — Bitget AI Base Camp Hackathon S2 · Track 3, AI Trading Desk · Execution Assistance**

Deadline **2026-09-21 23:59 UTC+8**. Started 2026-09-14.

## The claim

Bitget lists **1,175 tokenized US stocks**. You can enter any of them in one
click. Egress measures what it costs to leave - at your size, on your timetable -
and names the positions that have no exit at all.

## Why this sub-theme

The handbook defines **Execution Assistance** as *"Large order splitting; order
book depth analysis; slippage pattern adjustment."* That is this project, word for
word. A sweep of the public S2 field on 2026-09-14 found three entries in
Decision Stress Testing and **none** in Execution Assistance.

## What is being tested

**Hypothesis.** rToken spreads widen and top-of-book thins while the US market is
shut - most severely for names with no perp leg to hedge, because a maker who
cannot hedge will not quote tight.

**Control.** The 584 crypto pairs on the same venue. If their spreads move the
same way, the effect is venue-wide and the hypothesis is dead.

**This is a hypothesis, not a finding.** If it fails, that is the result and it
gets published as one. The project is useful either way: the exit-cost estimator
and the tail map stand on their own.

## Schedule

| Day | Deliverable | Status |
|---|---|---|
| **Sun 14** | Crawler shipped and collecting. Universe classified. Store + manifest + tests | **done** |
| Mon 15 | Exit-cost estimator: walk the book, slice an order, cost a schedule | **done early** |
| Tue 16 | Validation: predicted cost vs what actually printed. Publish the error distribution | |
| Wed 17 | Phase analysis: open vs overnight vs weekend, stocks vs the crypto control | |
| Thu 18 | The desk - natural-language question in, liquidation plan out | |
| Fri 19 | One research task end-to-end, recorded. Page. X post | |
| Sat 20 | Buffer. Submit | |

**Cut list, in order:** multi-position portfolios · the full-universe map (keep
one screenshot) · the phase finding if the data is thin · deep-book history.
**Never cut:** the liquidation plan, or the line naming what could not be verified.

## Required materials

| Requirement | State |
|---|---|
| Accessible demo | not started |
| One complete research task, question to actionable insight | not started |
| Compliant X post (`#BitgetHackathon`, `@Bitget_AI`) | not posted - **an entry without this is invalid** |
| Six-part description | not written |

## Rules that bind this project

- **Max two themes per team.** Ballast holds one. Egress is the second and last.
- The two must be **independent projects**. Egress is execution feasibility across
  1,175 names for a human-led desk; Ballast is price risk on 12 hedgeable names
  for an autonomous agent. The thesis here leads on the tail, not the clock.
- Judging is **pure subjective**: feature depth (data sources and skill
  integration count *and effectiveness*), research quality, LUI fluency,
  personalized thesis.

## Non-goals

- No orders, no account access, no credentials. Every endpoint used is public.
- No probability model of returns. This measures the cost of leaving, not whether
  to.
- No claim that a quote is a fill. Displayed size can be phantom; walking a book
  understates impact. Every number ships labelled `estimated`, never `observed`.
