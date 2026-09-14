"""The public page: docs/index.html.

Static. No JavaScript, no backend, no CDN, no webfont request. The whole site is
one file a judge can open, read, and check against the repository, which is also
why it survives being opened on a phone on conference wifi.

Every measured number is interpolated from `facts`, never typed. See MEMORY.md
rule 5: a retyped figure goes stale the moment the record moves and nobody
notices for weeks.
"""
from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

from . import config, facts

OUT = config.ROOT / "docs"

# Warm cream ground, charcoal text, burnt orange accent.
CSS = """
:root{
  --paper:#fbf7f1; --paper-2:#f4efe6; --ink:#16150f; --ink-2:#55524a;
  --ink-3:#8a8579; --rule:#ded7c9; --accent:#c8791b; --accent-soft:#f3e3cd;
  --good:#3f6f3a; --bad:#a33b1f;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:"Helvetica Neue",Helvetica,Arial,system-ui,sans-serif;
}
*{margin:0;padding:0;box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);
     line-height:1.5;font-size:16px}
.wrap{max-width:1080px;margin:0 auto;padding-inline:24px}

/* hairline rules carrying a crosshair at each end */
.rule{position:relative;border-top:1px solid var(--rule);height:1px;margin:0}
.rule::before,.rule::after{content:"";position:absolute;top:-4px;width:9px;
  height:9px;border-left:1px solid var(--ink-3);border-top:1px solid var(--ink-3)}
.rule::before{left:-4px}
.rule::after{right:-4px;transform:rotate(90deg)}

header{display:flex;align-items:center;justify-content:space-between;
       padding-block:22px}
.brand{display:flex;align-items:center;gap:12px;font-size:22px;letter-spacing:-.01em}
.brand svg{display:block}
.tag{font-family:var(--mono);font-size:11px;letter-spacing:.16em;
     text-transform:uppercase;color:var(--accent)}

/* corner-bracketed button */
.btn{position:relative;display:inline-block;padding:15px 30px;
     font-family:var(--mono);font-size:13px;letter-spacing:.14em;
     text-transform:uppercase;text-decoration:none;border:0}
.btn.solid{background:var(--accent);color:#fff}
.btn.ghost{background:transparent;color:var(--ink);
           box-shadow:inset 0 0 0 1px var(--rule)}
/* Corner marks on all four corners, drawn as eight hairline gradients so the
   frame stays crisp at any button width. */
.bracket{--c:var(--accent);--s:15px;--t:1px;
  display:inline-flex;padding:9px;
  background:
    linear-gradient(var(--c),var(--c)) 0 0/var(--s) var(--t) no-repeat,
    linear-gradient(var(--c),var(--c)) 0 0/var(--t) var(--s) no-repeat,
    linear-gradient(var(--c),var(--c)) 100% 0/var(--s) var(--t) no-repeat,
    linear-gradient(var(--c),var(--c)) 100% 0/var(--t) var(--s) no-repeat,
    linear-gradient(var(--c),var(--c)) 0 100%/var(--s) var(--t) no-repeat,
    linear-gradient(var(--c),var(--c)) 0 100%/var(--t) var(--s) no-repeat,
    linear-gradient(var(--c),var(--c)) 100% 100%/var(--s) var(--t) no-repeat,
    linear-gradient(var(--c),var(--c)) 100% 100%/var(--t) var(--s) no-repeat}
.btn{display:block}

.hero{padding-block:88px 76px;text-align:center}
.badge{display:inline-flex;align-items:center;gap:11px;background:#fff;
  padding:11px 20px;font-family:var(--mono);font-size:12px;letter-spacing:.15em;
  text-transform:uppercase;color:var(--ink);box-shadow:inset 0 0 0 1px var(--rule)}
.badge i{width:9px;height:9px;background:var(--accent);display:block}
h1{font-size:clamp(40px,7.6vw,82px);line-height:1.03;letter-spacing:-.035em;
   font-weight:600;margin:30px auto 0;max-width:17ch}
h1 em{font-style:normal;color:var(--accent)}
.lede{font-family:var(--mono);font-size:15px;line-height:1.85;color:var(--ink-2);
      max-width:62ch;margin:26px auto 0}
.cta{display:flex;gap:14px;justify-content:center;flex-wrap:wrap;margin-top:34px}

.grid-panel{background:
   radial-gradient(circle at center,var(--rule) 1px,transparent 1px) 0 0/22px 22px,
   linear-gradient(180deg,var(--paper-2),var(--paper));
   padding-block:76px}
section{padding-block:76px}
h2{font-size:clamp(26px,3.6vw,38px);letter-spacing:-.025em;font-weight:600;
   max-width:22ch}
.kicker{font-family:var(--mono);font-size:11px;letter-spacing:.18em;
        text-transform:uppercase;color:var(--accent);margin-bottom:14px}
.say{color:var(--ink-2);max-width:64ch;margin-top:16px;font-size:17px}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
       gap:1px;background:var(--rule);margin-top:40px;
       box-shadow:0 0 0 1px var(--rule)}
.stat{background:var(--paper);padding:26px 22px}
.stat b{display:block;font-size:clamp(28px,4.4vw,42px);letter-spacing:-.03em;
        font-weight:600;line-height:1.05}
.stat span{display:block;font-family:var(--mono);font-size:11px;
  letter-spacing:.13em;text-transform:uppercase;color:var(--ink-3);margin-top:9px}

.tbl{width:100%;border-collapse:collapse;margin-top:34px;font-size:15px}
.tbl th{font-family:var(--mono);font-size:11px;letter-spacing:.13em;
  text-transform:uppercase;color:var(--ink-3);text-align:left;font-weight:400;
  padding:0 14px 12px 0;border-bottom:1px solid var(--rule);white-space:nowrap}
.tbl td{padding:13px 14px 13px 0;border-bottom:1px solid var(--rule);
        vertical-align:top}
.tbl td.n{font-family:var(--mono);font-variant-numeric:tabular-nums;
          white-space:nowrap}
.sym{font-family:var(--mono);font-weight:600}
.pill{font-family:var(--mono);font-size:10px;letter-spacing:.1em;
  text-transform:uppercase;padding:3px 8px;background:var(--accent-soft);
  color:var(--accent)}
.pill.c{background:#e6e2d6;color:var(--ink-2)}
.scroll{overflow-x:auto}
.note{font-family:var(--mono);font-size:12.5px;line-height:1.8;color:var(--ink-3);
      margin-top:20px;max-width:76ch}
.note b{color:var(--ink-2);font-weight:600}
.caveat{border-left:2px solid var(--accent);padding:4px 0 4px 18px;margin-top:26px;
        max-width:72ch;color:var(--ink-2);font-size:15px}
footer{padding-block:44px;font-family:var(--mono);font-size:12px;
       color:var(--ink-3);display:flex;justify-content:space-between;
       gap:18px;flex-wrap:wrap}
footer a{color:var(--ink-2)}
@media (max-width:700px){
  .wrap{padding-inline:18px}
  .hero{padding-block:46px 42px}
  section,.grid-panel{padding-block:52px}
  header{flex-wrap:wrap;gap:8px}
  .tag{font-size:10px;letter-spacing:.11em}
  /* Letterspaced monospace does not wrap on its own and was setting a floor
     width wider than a phone. */
  .badge{font-size:10px;letter-spacing:.1em;padding:10px 14px;
         white-space:normal;line-height:1.6;text-align:left}
  h1{font-size:clamp(30px,8.6vw,46px);max-width:100%}
  .lede{font-size:13px;line-height:1.8;max-width:100%}
  .cta{flex-direction:column;align-items:stretch;gap:12px}
  /* inline-flex leaves the button at content width inside a full-width
     bracket; flex plus flex:1 makes it fill the frame. */
  .bracket{width:100%;display:flex}
  .btn{flex:1;text-align:center;padding-inline:16px}
  .stats{grid-template-columns:1fr 1fr}
  .stat{padding:20px 16px}
  h2{max-width:100%}
  .say{font-size:16px}
}
"""

MARK = ('<svg width="26" height="26" viewBox="0 0 26 26" fill="none" '
        'aria-hidden="true">'
        '<rect x="1.5" y="1.5" width="23" height="23" stroke="#16150f"/>'
        '<path d="M7 13h12M14 8l5 5-5 5" stroke="#c8791b" stroke-width="2"/>'
        '</svg>')


def _bp(value) -> str:
    return "-" if value is None else f"{value:,.1f} bp"


def _usdt(value) -> str:
    return "-" if value is None else f"{value:,.0f}"


def _phase_rows(phases: list[dict]) -> str:
    out = []
    for row in phases:
        ratio = f"{row['ratio']:.1f}x" if row.get("ratio") else "-"
        out.append(
            f"<tr><td class='sym'>{html.escape(row['phase'])}</td>"
            f"<td class='n'>{_bp(row['stock'])}</td>"
            f"<td class='n'>{_bp(row['crypto'])}</td>"
            f"<td class='n'>{ratio}</td>"
            f"<td class='n'>{row['snapshots']}</td></tr>")
    return "\n".join(out)


def _example_rows(examples: list[dict]) -> str:
    out = []
    for row in examples:
        kind = row.get("kind", "unknown")
        pill = f"<span class='pill{' c' if kind == 'crypto' else ''}'>{kind}</span>"
        if "error" in row:
            out.append(f"<tr><td class='sym'>{html.escape(row['symbol'])}</td>"
                       f"<td>{pill}</td><td class='n' colspan='3'>"
                       f"{html.escape(row['error'])}</td></tr>")
            continue
        cost = ("unquotable" if row["total_bp"] != row["total_bp"]
                else f"{'&gt;' if row.get('floor') else ''}{row['total_bp']:,.0f} bp")
        src = "top of book only" if row["source"] == "touch" else row["source"]
        out.append(
            f"<tr><td class='sym'>{html.escape(row['symbol'])}</td>"
            f"<td>{pill}</td>"
            f"<td class='n'>{cost}</td>"
            f"<td class='n'>{_usdt(row['book_usdt'])}</td>"
            f"<td class='n'>{html.escape(src)}</td></tr>")
    return "\n".join(out)


def render(f: dict | None = None) -> str:
    f = f or facts.build()
    counts = f["universe"]
    stocks = counts.get("stock", 0)
    phases = {row["phase"]: row for row in f["phases"]}
    closed = phases.get("overnight") or phases.get("weekend") or {}
    openp = phases.get("open") or {}
    cover = f["coverage"]
    gen = dt.datetime.fromisoformat(f["generated"])
    notional = f["notional_usdt"]

    swing = ""
    if closed.get("stock") and openp.get("stock"):
        swing = (f"{closed['stock']:,.0f} bp while the US market is shut, "
                 f"{openp['stock']:,.0f} bp while it is open")

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Egress - what it costs to leave</title>
<meta name="description" content="Exit liquidity for {stocks:,} tokenized US
stocks on Bitget, measured from the book that exists.">
<style>{CSS}</style>
</head><body>

<div class="wrap">
  <header>
    <div class="brand">{MARK}<span>egress</span></div>
    <span class="tag">Bitget AI Base Camp S2</span>
  </header>
</div>
<div class="wrap"><div class="rule"></div></div>

<div class="wrap">
  <div class="hero">
    <span class="badge"><i></i>Exit liquidity for tokenized stocks</span>
    <h1>One click in. <em>Not</em> one click out.</h1>
    <p class="lede">Bitget lists {stocks:,} tokenized US stocks. Egress measures
    what it actually costs to leave one - at your size, from the order book that
    exists right now, not from an average. It reads the whole listed universe
    every five minutes and keeps the record.</p>
    <div class="cta">
      <span class="bracket"><a class="btn solid" href="#evidence">See the
      evidence</a></span>
      <span class="bracket"><a class="btn ghost" href="#method">How it
      works</a></span>
    </div>
  </div>
</div>

<div class="grid-panel">
  <div class="wrap">
    <div class="stats">
      <div class="stat"><b>{stocks:,}</b><span>Tokenized stocks listed</span></div>
      <div class="stat"><b>{counts.get('crypto', 0):,}</b>
        <span>Crypto pairs as control</span></div>
      <div class="stat"><b>{cover['snapshots']:,}</b>
        <span>Snapshots recorded</span></div>
      <div class="stat"><b>{len(cover['gaps'])}</b>
        <span>{'Gap' if len(cover['gaps']) == 1 else 'Gaps'} in the record</span></div>
    </div>
  </div>
</div>

<div class="wrap">
  <section id="evidence">
    <p class="kicker">The measurement</p>
    <h2>The same book, priced twice</h2>
    <p class="say">A tokenized stock trades around the clock. The market that
    prices the share underneath it does not. When New York is shut, a market
    maker cannot hedge, so the quote widens - and the holder who needs out pays
    for it.{(" Median spread across every quoted name: " + swing + ".")
      if swing else ""}</p>

    <div class="scroll">
    <table class="tbl">
      <thead><tr><th>Market phase</th><th>Tokenized stock</th>
      <th>Crypto control</th><th>Ratio</th><th>Snapshots</th></tr></thead>
      <tbody>{_phase_rows(f['phases'])}</tbody>
    </table>
    </div>

    <p class="note"><b>Why the control column matters.</b> The crypto pairs trade
    on the same venue, through the same matching engine, under the same fee
    schedule. Their liquidity has no reason to care whether the NYSE is open. If
    both columns moved together the effect would be venue-wide and this whole
    page would be wrong.</p>

    <div class="caveat">This is a record in progress, not a finished study. The
    snapshot count behind each row is printed above so you can see how thin it
    still is. Nothing here is a claim about the future.</div>
  </section>
</div>
<div class="wrap"><div class="rule"></div></div>

<div class="wrap">
  <section id="method">
    <p class="kicker">Worked example</p>
    <h2>What leaving {notional:,.0f} USDT costs right now</h2>
    <p class="say">Walk the book from the mid, take the fill you would actually
    get, add the taker fee. Where the displayed book runs out before the position
    does, the number is a floor and is shown with a <span class="sym">&gt;</span>.</p>

    <div class="scroll">
    <table class="tbl">
      <thead><tr><th>Symbol</th><th>Type</th><th>Exit cost</th>
      <th>Book, USDT</th><th>Source</th></tr></thead>
      <tbody>{_example_rows(f['examples'])}</tbody>
    </table>
    </div>

    <p class="note"><b>Every figure here is estimated, never observed.</b> A
    displayed quote is not a fill: size can be withdrawn, and a real order moves
    the book it is measured against. The reference is the mid rather than the
    best bid, because crossing the spread is money the seller actually pays.
    Where a symbol returns no depth but a live quote, the cost is computed from
    the top of book alone and everything below it is unknown, not absent.</p>
  </section>
</div>

<div class="wrap"><div class="rule"></div>
  <footer>
    <span>Generated {gen:%Y-%m-%d %H:%M} UTC from the recorded crawl.
    No figure on this page is typed by hand.</span>
    <span><a href="https://github.com/Ritapossible/Egress">Source</a> &middot;
    MIT</span>
  </footer>
</div>

</body></html>
"""


def write(out: Path | None = None) -> Path:
    out = out or OUT
    out.mkdir(parents=True, exist_ok=True)
    path = out / "index.html"
    path.write_text(render(), encoding="utf-8")
    return path


if __name__ == "__main__":
    print(f"wrote {write()}")
