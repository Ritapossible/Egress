"""The public site: docs/*.html, one file per menu tab.

Static. No JavaScript outside the desk, no backend, no CDN, no webfont request.
Every page is a file a judge can open from a checkout and check against the
repository, which is also why the whole thing survives being opened on a phone
on conference wifi.

Every measured number is interpolated from `facts`, never typed. See MEMORY.md
rule 5: a retyped figure goes stale the moment the record moves and nobody
notices for weeks.
"""
from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

from . import config, exitcost, facts, validate

OUT = config.ROOT / "docs"
REPO = "https://github.com/Ritapossible/Egress"
BLOB = f"{REPO}/blob/main"

# Warm cream ground, charcoal text, burnt orange accent.
CSS = """:root{
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
.brand{display:flex;align-items:center;gap:12px;font-size:22px;
       letter-spacing:-.01em;color:inherit;text-decoration:none}
.brand svg{display:block}
/* One markup, two shapes: inline links on a wide screen, a native <details>
   disclosure on a narrow one. No script, so the menu opens with JS disabled. */
.menu{position:relative;font-family:var(--mono);font-size:11.5px;
      letter-spacing:.14em;text-transform:uppercase}
.menu summary{display:none}
/* A closed <details> has its content hidden with content-visibility, so
   the desktop inline menu painted out of a zero-width box and off the
   right edge. Engines without ::details-content ignore this and fall
   back to the older display:none behaviour, which lays out correctly. */
.menu::details-content{content-visibility:visible;display:contents}
.menu ul{display:flex;gap:26px;align-items:center;list-style:none}
.menu a{color:var(--ink-2);text-decoration:none;padding-block:4px;
        border-bottom:1px solid transparent;display:block}
.menu a:hover,.menu a:focus{color:var(--accent);border-bottom-color:var(--accent)}
.menu a.here{color:var(--ink);border-bottom-color:var(--accent)}

/* the desk */
.desk{background:#fff;box-shadow:inset 0 0 0 1px var(--rule);padding:30px;
      margin-top:34px}
.desk label{display:block;font-family:var(--mono);font-size:11px;
  letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);
  margin-bottom:10px}
.ask{display:flex;gap:12px;flex-wrap:wrap}
.ask input{flex:1;min-width:240px;font-family:var(--mono);font-size:15px;
  padding:15px 16px;border:0;background:var(--paper);color:var(--ink);
  box-shadow:inset 0 0 0 1px var(--rule)}
.ask input:focus{outline:2px solid var(--accent);outline-offset:1px}
.ask button{font-family:var(--mono);font-size:13px;letter-spacing:.14em;
  text-transform:uppercase;padding:15px 28px;border:0;background:var(--accent);
  color:#fff;cursor:pointer}
.ask button:disabled{opacity:.55;cursor:default}
.eg{margin-top:14px;font-family:var(--mono);font-size:12px;color:var(--ink-3)}
.eg button{background:none;border:0;color:var(--accent);cursor:pointer;
  font:inherit;padding:0;text-decoration:underline;text-underline-offset:3px}
#out{margin-top:26px}
#out:empty{display:none}
.ans{border-left:2px solid var(--accent);padding-left:18px}
/* The answer leads with a judgement. The variables behind it are one tap away
   rather than the first thing a reader has to interpret. */
.verdict{font-size:21px;line-height:1.45;color:var(--ink);letter-spacing:-.01em}
.verdict.bad{color:var(--bad);font-size:17px}
.ctx{margin-top:12px;font-size:15px;line-height:1.65;color:var(--ink-2)}
.advice{margin-top:10px;font-size:15px;line-height:1.65;color:var(--ink-2)}
.warn{margin-top:12px;font-family:var(--mono);font-size:12.5px;line-height:1.7;
      color:var(--bad);padding-left:14px;border-left:2px solid var(--bad)}
.working{margin-top:20px}
.working summary{font-family:var(--mono);font-size:11.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--ink-3);cursor:pointer;padding-block:6px}
.working summary:hover{color:var(--accent)}
.working[open] summary{color:var(--ink-2);margin-bottom:6px}
.sub-head{margin-top:20px;font-family:var(--mono);font-size:11px;
  letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3)}
.ans .big{font-size:19px;line-height:1.55;color:var(--ink)}
/* minmax(0,...) so a long label cannot squeeze the value column into a
   one-word-per-line ribbon, which is what `auto 1fr` did on a phone. */
.ans dl{display:grid;grid-template-columns:minmax(0,11em) minmax(0,1fr);
  gap:7px 16px;margin-top:18px;font-family:var(--mono);font-size:13px}
.ans dt{color:var(--ink-3);text-transform:uppercase;letter-spacing:.1em;
        font-size:11px;padding-top:2px}
.ans dd{color:var(--ink);font-variant-numeric:tabular-nums}
.ans ul{margin:16px 0 0 18px;font-size:13.5px;color:var(--ink-2);line-height:1.75}
.ans .bad{color:var(--bad)}

footer{padding-block:54px 40px}
.foot-top{display:grid;grid-template-columns:1.7fr 1fr 1fr;gap:40px}
.foot-top h3{font-size:11px;font-family:var(--mono);letter-spacing:.16em;
  text-transform:uppercase;color:var(--ink-3);font-weight:400;margin-bottom:14px}
/* The brand, not a section label: same accent as the Ask button. */
.foot-top h3.mark{color:var(--accent)}
.foot-top p{color:var(--ink-2);font-size:14.5px;max-width:48ch;line-height:1.7}
.foot-top a{display:block;color:var(--ink-2);text-decoration:none;
  font-size:14px;margin-bottom:9px}
.foot-top a:hover{color:var(--accent)}
.foot-bot{margin-top:44px;padding-top:24px;border-top:1px solid var(--rule)}
/* The provenance line is the project's whole claim, so it is legible rather
   than set in the same grey as the licence. */
.prov{display:flex;gap:12px;font-family:var(--mono);font-size:12.5px;
      line-height:1.75;color:var(--ink-2);max-width:80ch}
.prov i{flex:none;width:7px;height:7px;margin-top:8px;background:var(--accent)}
.foot-legal{display:flex;flex-wrap:wrap;gap:6px 22px;margin-top:20px;
  font-family:var(--mono);font-size:11.5px;letter-spacing:.04em;color:var(--ink-3)}
.foot-legal a{color:var(--ink-3);text-decoration:none;
  border-bottom:1px solid var(--rule)}
.foot-legal a:hover,.foot-legal a:focus{color:var(--accent);
  border-bottom-color:var(--accent)}

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

.hero{padding-block:82px 72px;text-align:center}
/* The desk is the product, so it is the first thing in the hero. Left-aligned
   inside a centred hero, because a form reads left even when its frame does not. */
.hero .desk{text-align:left;margin-top:38px}
.hero .eg,.hero #out{text-align:left}
/* Left-aligned and held to the desk's width: five lines of centred monospace
   is a wall, not a caption. */
.hero-note{text-align:left;font-family:var(--mono);font-size:12px;
  line-height:1.9;color:var(--ink-3);margin-top:20px;max-width:74ch}
.hero-links{display:flex;flex-wrap:wrap;gap:10px 22px;margin-top:16px;
  text-align:left}
.hero-links a{font-family:var(--mono);font-size:12px;color:var(--ink-2);
  text-decoration:none;border-bottom:1px solid var(--rule);padding-bottom:2px}
.hero-links a:hover,.hero-links a:focus{color:var(--accent);
  border-bottom-color:var(--accent)}
/* The label belongs above the field, not as a flex item beside it. */
.desk label{display:block}
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
   max-width:22ch;margin-top:64px}
/* The first heading in a section is spaced by the section's own padding. */
section>h2:first-child,.kicker+h2{margin-top:0}
/* A section that follows a page head carries less top padding: the head has
   already opened the page. */
.after-head{padding-top:40px}
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

.tbl{width:100%;min-width:560px;border-collapse:collapse;margin-top:34px;
      font-size:15px}
.tbl th{font-family:var(--mono);font-size:11px;letter-spacing:.13em;
  text-transform:uppercase;color:var(--ink-3);text-align:left;font-weight:400;
  padding:0 14px 12px 0;border-bottom:1px solid var(--rule);white-space:nowrap}
.tbl td{padding:13px 14px 13px 0;border-bottom:1px solid var(--rule);
        vertical-align:top}
.tbl td.n{font-family:var(--mono);font-variant-numeric:tabular-nums;
          white-space:nowrap}
.tbl td.dim{color:var(--ink-3);font-size:13.5px}
.sym{font-family:var(--mono);font-weight:600}
.pill{font-family:var(--mono);font-size:10px;letter-spacing:.1em;
  text-transform:uppercase;padding:3px 8px;background:var(--accent-soft);
  color:var(--accent)}
.pill.c{background:#e6e2d6;color:var(--ink-2)}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.scroll::after{content:"scroll ->";display:none;font-family:var(--mono);
  font-size:10.5px;color:var(--ink-3);letter-spacing:.1em;padding-top:8px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
       gap:1px;background:var(--rule);margin-top:40px;
       box-shadow:0 0 0 1px var(--rule)}
.card{background:var(--paper);padding:28px 24px;text-decoration:none;
      display:block;color:inherit}
.card:hover{background:#fff}
.card h3{font-size:19px;letter-spacing:-.015em;margin-bottom:10px;font-weight:600}
.card p{color:var(--ink-2);font-size:14.5px;line-height:1.65}
.card span{display:inline-block;margin-top:14px;font-family:var(--mono);
  font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.lead{font-size:18px;color:var(--ink-2);max-width:66ch;line-height:1.7;
      margin-top:18px}
.page-head{padding-block:64px 8px}
.page-head h1{font-size:clamp(32px,5.2vw,52px);max-width:20ch;margin:14px 0 0;
              text-align:left}
/* A docs contents that wraps rather than stacking eight lines above the
   first paragraph. */
.toc{display:flex;flex-wrap:wrap;gap:8px;margin-top:28px;max-width:72ch}
.toc a{font-family:var(--mono);font-size:11.5px;letter-spacing:.1em;
       text-transform:uppercase;color:var(--ink-2);text-decoration:none;
       padding:8px 14px;background:#fff;box-shadow:inset 0 0 0 1px var(--rule)}
.toc a:hover,.toc a:focus{color:var(--accent);
       box-shadow:inset 0 0 0 1px var(--accent)}
h3.sub{font-size:20px;letter-spacing:-.015em;margin:36px 0 10px}
code{font-family:var(--mono);font-size:.92em;background:var(--paper-2);
     padding:2px 6px}
pre{font-family:var(--mono);font-size:13px;line-height:1.75;background:#fff;
    box-shadow:inset 0 0 0 1px var(--rule);padding:20px;overflow-x:auto;
    margin-top:16px}
pre code{background:none;padding:0}
/* The landing page's one comparison. Two panels, no table: the point is the
   size of the gap, not the precision of either side. */
.compare{display:grid;grid-template-columns:1fr 1fr;gap:1px;margin-top:34px;
  background:var(--rule);box-shadow:0 0 0 1px var(--rule)}
.cmp{background:#fff;padding:30px 28px 26px}
.cmp-when{font-family:var(--mono);font-size:11px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--accent)}
.cmp-when span{color:var(--ink-3);margin-left:8px}
.cmp b{display:block;margin-top:14px;font-size:clamp(38px,5.4vw,60px);
  font-weight:600;letter-spacing:-.035em;line-height:1}
.cmp b i{font-style:normal;font-size:.36em;letter-spacing:.02em;
  margin-left:7px;color:var(--ink-3)}
.cmp-ctrl{margin-top:14px;font-family:var(--mono);font-size:12px;
  color:var(--ink-3)}
.note a{color:var(--ink-2);border-bottom:1px solid var(--rule);
  text-decoration:none}
.note a:hover,.note a:focus{color:var(--accent);border-bottom-color:var(--accent)}
.note{font-family:var(--mono);font-size:12.5px;line-height:1.8;color:var(--ink-3);
      margin-top:20px;max-width:76ch}
.note b{color:var(--ink-2);font-weight:600}
.caveat{border-left:2px solid var(--accent);padding:4px 0 4px 18px;margin-top:26px;
        max-width:72ch;color:var(--ink-2);font-size:15px}
/* Six inline tabs stop fitting well before a phone, so the header
   collapses to a pill a breakpoint earlier than the layout does. */
@media (max-width:900px){
  /* the header becomes a floating pill, and the menu a disclosure */
  header{background:#fff;border-radius:999px;padding:12px 16px;margin-top:14px;
         box-shadow:0 1px 3px rgba(20,18,12,.09),inset 0 0 0 1px var(--rule)}
  .menu summary{display:flex;align-items:center;justify-content:center;
    width:40px;height:40px;border-radius:999px;cursor:pointer;
    box-shadow:inset 0 0 0 1px var(--rule);list-style:none}
  .menu summary::-webkit-details-marker{display:none}
  .menu summary span{display:block;width:16px;height:1.5px;background:var(--ink);
    position:relative}
  .menu summary span::before,.menu summary span::after{content:"";position:absolute;
    left:0;width:16px;height:1.5px;background:var(--ink)}
  .menu summary span::before{top:-5px}
  .menu summary span::after{top:5px}
  .menu[open] summary{background:var(--accent)}
  .menu[open] summary span,.menu[open] summary span::before,
  .menu[open] summary span::after{background:#fff}
  .menu ul{display:none}
  .menu[open] ul{display:block;position:absolute;right:0;top:calc(100% + 12px);
    background:#fff;border-radius:18px;padding:14px 22px;z-index:20;
    box-shadow:0 8px 28px rgba(20,18,12,.12),inset 0 0 0 1px var(--rule)}
  .menu[open] ul li{padding-block:9px}
}

@media (max-width:700px){
  .wrap{padding-inline:18px}
  .scroll::after{display:block}
  .page-head{padding-block:34px 4px}
  .after-head{padding-top:26px}
  h2{margin-top:46px}
  .hero{padding-block:46px 42px}
  section,.grid-panel{padding-block:52px}
  .brand{font-size:18px;gap:9px}
  .desk{padding:20px}
  .ask input{min-width:100%}
  .ask button{width:100%}
  .foot-top{grid-template-columns:1fr;gap:26px}
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
  .compare{grid-template-columns:1fr}
  .cmp{padding:24px 22px}
  .stat{padding:20px 16px}
  h2{max-width:100%}
  .say{font-size:16px}
  /* A label and a figure do not both fit on one phone line. */
  .ans dl{grid-template-columns:1fr;gap:2px}
  .ans dt{padding-top:10px}
  .ans dt:first-child{padding-top:0}
  .verdict{font-size:19px}
}
"""

DESK_JS = """/* The desk's only script. Progressive: with JS off the form posts nowhere
   and every measured section on the page still renders, because all of it is
   generated at build time. */
(function () {
  var form = document.getElementById('ask');
  var input = document.getElementById('q');
  var button = document.getElementById('go');
  var out = document.getElementById('out');
  if (!form || !input || !out) return;

  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c];
    });
  }

  function row(term, value) {
    return '<dt>' + esc(term) + '</dt><dd>' + esc(value) + '</dd>';
  }

  var inFlight = false;

  function fail(message) {
    out.innerHTML = '<div class="ans"><p class="verdict bad">' + esc(message)
      + '</p></div>';
  }

  function render(data) {
    if (data.error) {
      out.innerHTML = '<div class="ans"><p class="verdict bad">' + esc(data.error)
        + '</p></div>';
      return;
    }
    var q = data.quote || {};
    var spec = data.spec || {};
    var html = '<div class="ans">';

    // The answer, not the variables: a verdict, then what it is measured
    // against, then whether to do anything about it.
    html += '<p class="verdict">' + esc(data.headline || data.reading || '') + '</p>';
    if (data.context) html += '<p class="ctx">' + esc(data.context) + '</p>';
    if (data.depth_note) html += '<p class="warn">' + esc(data.depth_note) + '</p>';
    if (data.advice) html += '<p class="advice">' + esc(data.advice) + '</p>';

    // Everything a reader might want to check, one tap away and never lost.
    html += '<details class="working"><summary>Show the working</summary><dl>';
    html += row('Ticker', (spec.ticker || '-') + ' \u00b7 ' + (data.symbol || '-'));
    html += row('Position size', Number(q.requested_usdt || 0).toLocaleString()
                + ' USDT, valued at the mid');
    if (q.quotable) {
      var floor = (q.exhausted || q.source === 'touch') ? '>' : '';
      html += row('Exit cost, one order',
        floor + Number(q.total_bp).toFixed(2) + ' bp  ('
        + floor + Number(q.total_usdt).toLocaleString(undefined,
            {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' USDT)');
      html += row('  of which slippage', Number(q.slippage_bp).toFixed(2) + ' bp');
      html += row('  of which fee', Number(q.fee_bp).toFixed(2) + ' bp (assumed)');
      html += row('Reference mid', Number(q.reference).toLocaleString());
      html += row('You would receive', Number(q.vwap).toLocaleString() + ' average');
      html += row('Book levels used', q.levels_used);
    }
    var book = Number(q.book_usdt || 0);
    html += row('Bid-side depth', book.toLocaleString() + ' USDT');
    if (data.max_exit_200bp !== undefined) {
      var max = Number(data.max_exit_200bp);
      html += row('Exitable under 200 bp', max.toLocaleString() + ' USDT'
        + (Math.abs(max - book) < 1 ? ' (the whole displayed book)' : ''));
    }
    html += row('Depth source',
      q.source === 'touch' ? 'top of book only' : (q.source || '-'));
    html += row('Market phase', data.phase || '-');
    html += row('Basis', 'estimated from the displayed book, not a fill');
    html += '</dl>';

    // Only show the slicing table when the clips actually differ.
    var plan = (data.plan || []).filter(function (p) {
      return p.quotable && p.slices > 1;      // one order is the headline above
    });
    var varies = plan.some(function (p) {
      return (p.worst_case_bp - p.best_case_bp) >= 0.5;
    });
    if (plan.length && varies) {
      html += '<p class="sub-head">Split into smaller orders</p><dl>';
      plan.forEach(function (p) {
        html += row(p.slices + ' orders',
          Number(p.best_case_bp).toFixed(1) + ' to '
          + Number(p.worst_case_bp).toFixed(1) + ' bp'
          + ' (best case assumes the book refills)');
      });
      html += '</dl>';
    }

    if (data.unverified && data.unverified.length) {
      html += '<p class="sub-head">What this cannot tell you</p><ul>';
      data.unverified.forEach(function (u) { html += '<li>' + esc(u) + '</li>'; });
      html += '</ul>';
    }
    html += '</details>';
    out.innerHTML = html + '</div>';
  }

  function ask(question) {
    // The serverless function is capped; the client gives it a little more than
    // that and then says so, rather than leaving the form disabled forever.
    if (inFlight || !question.trim()) return;
    inFlight = true;
    if (button) button.disabled = true;
    out.innerHTML = '<div class="ans"><p class="big">Reading the question, then '
      + 'the book...</p></div>';

    var control = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = setTimeout(function () {
      if (control) control.abort();
    }, 35000);

    fetch('/api/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({q: question}),
      signal: control ? control.signal : undefined
    }).then(function (r) {
      return r.text().then(function (body) {
        var data;
        try {
          data = JSON.parse(body);
        } catch (e) {
          // A non-JSON body means the platform answered, not the desk.
          throw new Error('the desk returned an unreadable response (HTTP '
                          + r.status + ')');
        }
        if (!r.ok && !data.error) {
          throw new Error('the desk returned HTTP ' + r.status);
        }
        return data;
      });
    }).then(render)
      .catch(function (e) {
        fail(e && e.name === 'AbortError'
          ? 'The desk took too long and the request was cancelled. Try again, '
            + 'or ask about a more liquid name.'
          : 'The desk could not be reached: ' + (e && e.message ? e.message : e));
      })
      .then(function () {
        clearTimeout(timer);
        inFlight = false;
        if (button) button.disabled = false;
      });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    ask(input.value);
  });

  Array.prototype.forEach.call(
    document.querySelectorAll('.eg button[data-q]'), function (b) {
      b.addEventListener('click', function () {
        input.value = b.getAttribute('data-q');
        ask(input.value);
      });
    });
})();
"""

MARK = ('<svg width="26" height="26" viewBox="0 0 26 26" fill="none" '
        'aria-hidden="true">'
        '<rect x="1.5" y="1.5" width="23" height="23" stroke="#16150f"/>'
        '<path d="M7 13h12M14 8l5 5-5 5" stroke="#c8791b" stroke-width="2"/>'
        '</svg>')


# ---------------------------------------------------------------- formatting

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
        cost = ("unquotable" if not exitcost.quotable(row.get("total_bp"))
                else f"{'&gt;' if row.get('floor') else ''}{row['total_bp']:,.0f} bp")
        src = "top of book only" if row["source"] == "touch" else row["source"]
        out.append(
            f"<tr><td class='sym'>{html.escape(row['symbol'])}</td>"
            f"<td>{pill}</td>"
            f"<td class='n'>{cost}</td>"
            f"<td class='n'>{_usdt(row['book_usdt'])}</td>"
            f"<td class='n'>{html.escape(src)}</td></tr>")
    return "\n".join(out)


def _validation(v: dict) -> tuple[str, str]:
    """(one sentence, the block) - or an honest account of why there is neither."""
    if not v or not v.get("symbols"):
        return ("It has not been run yet.", "")
    excluded = v.get("excluded", 0)
    kinds = ", ".join(v.get("excluded_kinds") or []) or "some"

    say = ""
    if v.get("median_ratio") is not None:
        say = (f"Across {v['bars']:,} bars the median was "
               f"<strong>{v['median_ratio']:,.0f}x</strong> - far more traded than "
               f"was ever displayed, so the book refills and the estimator is "
               f"conservative.")
    rows = "\n".join(
        f"<tr><td class='sym'>{html.escape(e['symbol'])}</td>"
        f"<td class='n'>{e['feed_ratio']:,.1f}x</td>"
        f"<td class='dim'>{html.escape(e['reason'])}</td></tr>"
        for e in (v.get("excluded_detail") or []) if e.get("feed_ratio"))

    block = f"""
    <p class="note"><b>Most of this universe could not be validated, and that is
    the result.</b> Before comparing anything, the check sums twenty-four hourly
    bars for a symbol and holds the total against that symbol's own rolling 24h
    turnover. On crypto the two land within 2% of each other. On tokenized stocks
    they diverge by a factor that differs per symbol - base volume and quote
    volume diverge by the same factor, so it is not a units error, and it is not
    constant, so it is not a fixed multiplier. Which feed is right cannot be
    settled from outside, so {excluded} {kinds} symbols were excluded rather than
    averaged over.</p>

    <div class="scroll">
    <table class="tbl">
      <thead><tr><th>Excluded symbol</th><th>Candle vs ticker</th>
      <th>Why</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </div>

    <p class="note"><b>A ratio above 1 has one explanation; below 1 has two.</b>
    More printing than was displayed can only mean the book refilled. Displayed
    size going unconsumed could mean it was withdrawn before anyone hit it, or
    that nobody wanted it. Idle and phantom liquidity look identical from outside,
    and this data cannot separate them.</p>"""
    return say, block


# ------------------------------------------------------------------ the shell

# (file, menu label, <title>, meta description builder)
NAV = (
    ("index.html", "Desk"),
    ("evidence.html", "Evidence"),
    ("validation.html", "Validation"),
    ("method.html", "Method"),
    ("docs.html", "Docs"),
)


def _menu(here: str) -> str:
    mark = ' class="here" aria-current="page"'
    items = "\n".join(
        f'      <li><a href="{file}"{mark if file == here else ""}'
        f">{label}</a></li>"
        for file, label in NAV)
    return f"""<nav aria-label="Pages">
    <details class="menu">
      <summary aria-label="Menu"><span></span></summary>
      <ul>
{items}
      <li><a href="{REPO}">Source</a></li>
      </ul>
    </details>
  </nav>"""


def _footer(f: dict) -> str:
    cover = f["coverage"]
    gen = dt.datetime.fromisoformat(f["generated"])
    pages = "\n".join(f'        <a href="{file}">{label}</a>'
                      for file, label in NAV)
    return f"""  <footer>
    <div class="foot-top">
      <div>
        <h3 class="mark">Egress</h3>
        <p>Exit liquidity for tokenized US equities. Egress reads every listed
        instrument on Bitget every five minutes and measures what it costs to
        leave a position, at a stated size, from the book that exists.</p>
      </div>
      <div>
        <h3>Pages</h3>
{pages}
      </div>
      <div>
        <h3>Project</h3>
        <a href="{REPO}">Source and method</a>
        <a href="{BLOB}/ARCHITECTURE.md">Architecture</a>
        <a href="{BLOB}/PLAN.md">What is measured</a>
      </div>
    </div>
    <div class="foot-bot">
      <p class="prov"><i></i>Generated {gen:%Y-%m-%d %H:%M} UTC from
      {cover['snapshots']:,} recorded snapshots. Every figure on this site is read
      from that record at build time. None is typed, and none is cached longer
      than the crawl that produced it.</p>
      <div class="foot-legal">
        <span>&copy; {gen:%Y} Egress</span>
        <span>Research only. Not advice, not an offer, not a quote.</span>
        <a href="{BLOB}/LICENSE">MIT licensed</a>
        <a href="{REPO}">Source</a>
      </div>
    </div>
  </footer>"""


ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
        "viewBox='0 0 26 26'%3E%3Crect width='26' height='26' fill='%23fbf7f1'"
        "/%3E%3Cpath d='M6 13h13M14 8l5 5-5 5' stroke='%23c8791b' "
        "stroke-width='2.4' fill='none'/%3E%3C/svg%3E")


def shell(*, title: str, description: str, here: str, body: str, f: dict,
          script: bool = False) -> str:
    """One chrome for every page. The only thing that varies is the body."""
    tag = '\n<script src="desk.js"></script>' if script else ""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="icon" href="{ICON}">
<meta name="description" content="{description}">
<style>{CSS}</style>
</head><body>

<div class="wrap" id="top">
  <header>
    <a class="brand" href="index.html">{MARK}<span>egress</span></a>
    {_menu(here)}
  </header>
</div>
<div class="wrap"><div class="rule"></div></div>
{body}
<div class="wrap"><div class="rule"></div>
{_footer(f)}
</div>{tag}
</body></html>
"""


# ------------------------------------------------------------------- the desk

HERO_DESK = """
    <div class="desk">
      <label for="q">Ask what leaving costs</label>
      <form class="ask" id="ask" action="/api/ask" method="post">
        <input id="q" name="q" type="text" autocomplete="off"
               placeholder="What does leaving 40,000 USDT of TSLA cost?">
        <button type="submit" id="go">Ask</button>
      </form>
      <p class="eg">Try:
        <button type="button" data-q="What does leaving 40,000 USDT of TSLA cost?">a
        large TSLA position</button> &middot;
        <button type="button" data-q="I hold 5000 USDT of NVDA and need out today.">a
        small NVDA one</button> &middot;
        <button type="button" data-q="Cost to exit 25,000 USDT of SYK?">a
        thin name</button>
      </p>
      <div id="out" role="status" aria-live="polite"></div>
    </div>

    <p class="hero-note">The reader turns your question into a symbol and a size.
    Every number after that is walked off the live book by code, so a wrong
    answer shows up as a visibly wrong reading rather than an invented figure.
    The desk needs JavaScript and a configured reader - nothing else on this
    site does.</p>
    <p class="hero-links"><a href="method.html">How the number is computed</a>
    <a href="evidence.html">What it is built on</a>
    <a href="validation.html">Whether the quotes are real</a></p>
"""


# ------------------------------------------------------------------- the pages

def _finding(f: dict) -> str:
    """The one comparison the landing page exists to make.

    Returns "" rather than a half-filled panel when the record does not yet
    carry both an open and a closed phase: an empty figure is worse than none.
    """
    phases = {row["phase"]: row for row in f["phases"]}
    closed = phases.get("overnight") or phases.get("weekend") or {}
    openp = phases.get("open") or {}
    if not (closed.get("stock") and openp.get("stock")):
        return ""

    ratio = closed["stock"] / openp["stock"]
    panels = []
    for row, label, note in (
            (closed, closed["phase"], "US market shut"),
            (openp, "open", "US market open")):
        ctrl = (f"crypto control {row['crypto']:,.0f} bp"
                if row.get("crypto") else "crypto control unquoted")
        panels.append(
            f"""      <div class="cmp">
        <p class="cmp-when">{html.escape(label)} <span>{note}</span></p>
        <b>{row['stock']:,.0f}<i>bp</i></b>
        <p class="cmp-ctrl">{ctrl}</p>
      </div>""")

    return f"""
<div class="wrap">
  <section>
    <p class="kicker">The finding</p>
    <h2>The same token costs {ratio:,.0f}x more to leave at night</h2>
    <p class="say">Median spread across every quoted tokenized stock, by market
    phase. The crypto pairs beside each figure trade on the same venue, through
    the same matching engine, under the same fee schedule - and they do not
    move.</p>

    <div class="compare">
{chr(10).join(panels)}
    </div>

    <p class="note"><b>That gap is the product.</b> A holder who needs out
    overnight pays it, and nothing on the venue tells them so beforehand.
    Measured across {f['coverage']['snapshots']:,} snapshots of the whole
    listed universe. <a href="evidence.html">See the measurement</a>.</p>
  </section>
</div>
"""


def index_body(f: dict) -> str:
    counts = f["universe"]
    stocks = counts.get("stock", 0)
    cover = f["coverage"]

    return f"""
<div class="wrap">
  <div class="hero">
    <span class="badge"><i></i>Exit liquidity for tokenized stocks</span>
    <h1>One click in. <em>Not</em> one click out.</h1>
    <p class="lede">Bitget lists {stocks:,} tokenized US stocks. Egress measures
    what it actually costs to leave one - at your size, from the order book that
    exists right now, not from an average. Ask it.</p>
{HERO_DESK}  </div>
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
{_finding(f)}"""


def evidence_body(f: dict) -> str:
    phases = {row["phase"]: row for row in f["phases"]}
    closed = phases.get("overnight") or phases.get("weekend") or {}
    openp = phases.get("open") or {}
    swing = ""
    if closed.get("stock") and openp.get("stock"):
        swing = (f" Median spread across every quoted name: "
                 f"{closed['stock']:,.0f} bp while the US market is shut, "
                 f"{openp['stock']:,.0f} bp while it is open.")

    return f"""
<div class="wrap">
  <div class="page-head">
    <p class="kicker">The measurement</p>
    <h1>The same book, priced twice</h1>
    <p class="lead">A tokenized stock trades around the clock. The market that
    prices the share underneath it does not. When New York is shut, a market
    maker cannot hedge, so the quote widens - and the holder who needs out pays
    for it.{swing}</p>
  </div>
</div>

<div class="wrap">
  <section class="after-head">
    <h2>Spread by market phase</h2>
    <p class="say">Every row is a median across every quoted symbol of that type
    in every snapshot taken during that phase. Phase is decided from the venue
    timestamp, not from the clock on the machine that ran the crawl.</p>

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
    site would be wrong.</p>

    <div class="caveat">This is a record in progress, not a finished study. The
    snapshot count behind each row is printed above so you can see how thin it
    still is. Nothing here is a claim about the future.</div>

    <h3 class="sub">What a row does not say</h3>
    <p class="say">A median spread is not a cost. It is the price of the first
    share, not of the position. What the position costs depends on size, and
    that is <a href="method.html">the method page</a>. Whether the quote behind
    the spread is real at all is <a href="validation.html">the validation
    page</a>.</p>
  </section>
</div>
"""


def validation_body(f: dict) -> str:
    say, block = _validation(f.get("validation") or {})
    return f"""
<div class="wrap">
  <div class="page-head">
    <p class="kicker">Validation</p>
    <h1>Checking the quotes against the prints</h1>
    <p class="lead">A quote is a promise. The check is to hold the size resting
    at the touch against the volume that actually printed in the five minutes
    after it. {say}</p>
  </div>
</div>

<div class="wrap">
  <section class="after-head">
    {block}

    <h3 class="sub">The gate, and why it exists</h3>
    <p class="say">A symbol is only compared once its own two volume feeds agree
    with each other. Anything outside a {validate.AGREE_LOW:.2f} to {validate.AGREE_HIGH:.2f} band is excluded and named
    above rather than folded into an average. Publishing a ratio computed from a
    feed already shown to be unreliable would be worse than publishing
    nothing.</p>
  </section>
</div>
"""


def method_body(f: dict) -> str:
    notional = f["notional_usdt"]
    return f"""
<div class="wrap">
  <div class="page-head">
    <p class="kicker">Method</p>
    <h1>How a cost is computed</h1>
    <p class="lead">Walk the book from the mid, take the fill you would actually
    get, add the taker fee. Where the displayed book runs out before the position
    does, the number is a floor and is shown with a
    <span class="sym">&gt;</span>.</p>
  </div>
</div>

<div class="wrap">
  <section class="after-head">
    <h2>The four steps</h2>
    <div class="cards">
      <div class="card">
        <h3>1. Reference</h3>
        <p>The mid, not the best bid. Crossing the spread is money the seller
        actually pays, so charging it to the exit is the honest accounting.</p>
      </div>
      <div class="card">
        <h3>2. Walk</h3>
        <p>Consume the bid side level by level until the stated notional is
        filled. The average fill price against the mid is the impact.</p>
      </div>
      <div class="card">
        <h3>3. Fee</h3>
        <p>A flat {exitcost.TAKER_FEE_BP:g} bp taker fee is added. It is the published schedule, not a measurement,
        and it is the only typed number on this site.</p>
      </div>
      <div class="card">
        <h3>4. Floor or estimate</h3>
        <p>If the displayed book runs out first, the answer is a lower bound,
        marked, never rounded up into a figure that looks exact.</p>
      </div>
    </div>

    <h2>What leaving {notional:,.0f} USDT costs right now</h2>
    <p class="say">Read at build time from the live book, for a spread of names
    thick and thin, with a crypto pair alongside for scale.</p>

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

    <h3 class="sub">Slicing is given as a bound, not a number</h3>
    <p class="say">Splitting an exit into parts helps only if the book refills
    between them, and how fast it refills cannot be read off a single snapshot.
    So the desk returns a best case, which assumes full replenishment, and a
    worst case, which assumes none. The truth is somewhere inside, and the
    bound is stated rather than a midpoint invented.</p>
  </section>
</div>
"""


# -------------------------------------------------------------------- the docs

DOC_SECTIONS = (
    ("overview", "Overview"),
    ("quickstart", "Quickstart"),
    ("architecture", "Architecture"),
    ("data", "Data reference"),
    ("api", "HTTP API"),
    ("cli", "Command line"),
    ("limits", "Limitations"),
    ("glossary", "Glossary"),
)


def docs_body(f: dict) -> str:
    counts = f["universe"]
    cover = f["coverage"]
    listed = f.get("listed_total") or sum(counts.values())
    cols = "\n".join(
        f"<tr><td class='sym'>{name}</td><td class='dim'>{desc}</td></tr>"
        for name, desc in (
            ("snap_ts", "Epoch milliseconds the snapshot was started, "
                        "stamped once for every row in it."),
            ("symbol", "Venue symbol, for example RTSLAUSDT or BTCUSDT."),
            ("bid", "Best bid at the moment of the read."),
            ("ask", "Best ask at the moment of the read."),
            ("bid_size", "Size resting at the best bid, in base units."),
            ("ask_size", "Size resting at the best ask, in base units."),
            ("last", "Last traded price reported by the ticker feed."),
            ("turnover24h", "Rolling 24h quote turnover for the symbol."),
            ("venue_ts", "The venue's own timestamp for the quote, which is "
                         "what phase is decided from."),
        ))
    toc = "\n".join(f'    <a href="#{slug}">{label}</a>'
                    for slug, label in DOC_SECTIONS)

    return f"""
<div class="wrap">
  <div class="page-head">
    <p class="kicker">Documentation</p>
    <h1>Egress, end to end</h1>
    <p class="lead">What it measures, how to run it yourself, what the record
    looks like on disk, and what it cannot tell you. Written so that someone who
    has never seen the repository can reproduce a number on this site.</p>
    <div class="toc">
{toc}
    </div>
  </div>
</div>

<div class="wrap">
  <section class="after-head">

    <h2 id="overview">Overview</h2>
    <p class="say">Egress answers one question: what does it cost to leave a
    tokenized US stock position, at a stated size, right now. Entering is easy
    and every venue advertises it. Leaving is the half nobody prices, and on a
    tokenized equity it is the half that moves, because the share underneath
    stops trading at the New York close while the token does not.</p>
    <p class="say">The project is two halves that never touch. A crawler reads
    every listed instrument on a fixed interval and appends what it saw to an
    append-only record. Everything else - the phase table, the validation, the
    estimator, this site - reads that record afterwards. Collection never
    imports interpretation, so a change in how a number is read can never
    change what was recorded.</p>
    <p class="note"><b>No credentials anywhere.</b> Every venue endpoint used is
    public. The crawler runs unattended on a shared runner with nothing to leak.
    The only secret in the project is the reader key for the desk, and it lives
    in the serverless function, never in a page.</p>

    <h2 id="quickstart">Quickstart</h2>
    <p class="say">Python 3.10 or newer, tested on 3.10 through 3.13. No
    runtime dependencies at all - the standard library does the HTTP, the gzip
    and the CSV. Ruff and mypy are dev tools, not requirements.</p>
    <pre><code>git clone {REPO}.git
cd Egress

# one pass over the whole listed universe, written to state/
python -m egress.crawl --once

# what the record holds so far
python -m egress.crawl --coverage

# what leaving 25,000 USDT of TSLA costs, from the live book
python -c "from egress import exitcost; print(exitcost.for_symbol('RTSLAUSDT', 25000))"

# rebuild this site into docs/
python -m egress.page</code></pre>
    <p class="say">A continuous record is a long loop rather than a long
    process: <code>python -m egress.crawl --loop --hours 6</code> takes a
    snapshot every {config.DEFAULT_INTERVAL_S // 60} minutes for six hours and
    exits cleanly, which is what the scheduled job on the repository runs.</p>

    <h2 id="architecture">Architecture</h2>
    <p class="say">Twelve modules, each with one job, listed in the order data
    moves through them.</p>
    <div class="scroll">
    <table class="tbl">
      <thead><tr><th>Module</th><th>What it does</th></tr></thead>
      <tbody>
        <tr><td class="sym">config</td><td class="dim">Paths, endpoints and the
          few constants. No key appears here or anywhere else.</td></tr>
        <tr><td class="sym">market</td><td class="dim">The only module that
          speaks HTTP. A venue that will not answer raises a typed
          MarketUnavailable, never a bare exception.</td></tr>
        <tr><td class="sym">universe</td><td class="dim">Classifies every listed
          instrument by the venue's own symbolType field. Guessing from the
          symbol name is wrong for dozens of symbols.</td></tr>
        <tr><td class="sym">sessions</td><td class="dim">Turns a timestamp into
          open, overnight, weekend or holiday. Pure arithmetic, no
          network.</td></tr>
        <tr><td class="sym">store</td><td class="dim">The append-only record.
          Rows are written first and the snapshot is entered in the manifest
          second, so a run killed halfway leaves data no reader will
          trust.</td></tr>
        <tr><td class="sym">crawl</td><td class="dim">The loop. Reads the
          universe, writes a snapshot, sleeps. It never imports sessions or
          exitcost: collection is separate from interpretation.</td></tr>
        <tr><td class="sym">exitcost</td><td class="dim">Walks the book from the
          mid and returns what an exit costs, with a floor where the book ran
          out and a bound where slicing is involved.</td></tr>
        <tr><td class="sym">validate</td><td class="dim">Holds displayed size
          against printed volume, and refuses to compare a symbol whose own two
          volume feeds disagree.</td></tr>
        <tr><td class="sym">llm</td><td class="dim">The reader. Plain English in,
          a ticker and a size out - never a price, never a cost. Its output is
          validated against a shape and clamped before anything uses it.</td></tr>
        <tr><td class="sym">desk</td><td class="dim">The question answerer. The
          reader chooses a ticker and a size; every number after that is
          computed. One venue round trip per question, so the quote, the plan
          and the max-exit search describe one same book.</td></tr>
        <tr><td class="sym">facts</td><td class="dim">Reads the whole record and
          assembles the fact set every page renders from. Nothing here fetches;
          it only interprets what the crawler stored.</td></tr>
        <tr><td class="sym">page</td><td class="dim">Generates this site. Every
          measured number is interpolated from facts, never typed, so a figure
          cannot go stale without the record going stale with it.</td></tr>
      </tbody>
    </table>
    </div>
    <p class="note"><b>The reader compiles, the code computes.</b> The language
    model is only ever asked for a symbol and a notional. It is never asked for
    a price, a spread or a cost, and it cannot select a ticker that is not
    listed on the venue right now - resolution is a lookup against the live
    instrument list, so an invented ticker fails loudly instead of being
    priced.</p>

    <h2 id="data">Data reference</h2>
    <p class="say">The record lives in <code>state/</code>. Each snapshot is one
    gzipped CSV under <code>state/snapshots/</code>, and
    <code>state/manifest.jsonl</code> holds one JSON line per completed
    snapshot. A snapshot absent from the manifest is skipped on read even if its
    file exists.</p>
    <div class="scroll">
    <table class="tbl">
      <thead><tr><th>Column</th><th>Meaning</th></tr></thead>
      <tbody>{cols}</tbody>
    </table>
    </div>
    <p class="say">Current record: {cover['snapshots']:,} snapshots,
    {cover['rows']:,} rows, {len(cover['gaps'])}
    {'gap' if len(cover['gaps']) == 1 else 'gaps'} in coverage, across
    {listed:,} listed instruments ({counts.get('stock', 0):,} tokenized stocks,
    {counts.get('crypto', 0):,} crypto pairs).</p>
    <p class="note"><b>Silence is not zero.</b> A symbol missing from a snapshot
    means the venue did not report it, not that its spread was nothing. Missing
    rows are absent from every median rather than counted as a value.</p>

    <h2 id="api">HTTP API</h2>
    <p class="say">One endpoint, used by the desk on the front page. It exists
    because a reader key cannot live in a browser.</p>
    <pre><code>POST /api/ask
Content-Type: application/json

  "q": "What does leaving 40,000 USDT of TSLA cost?"</code></pre>
    <p class="say">The response states a symbol, the compiled size, the quote
    walked off the live book, a slicing bound, and a plain-English reading. Every
    failure is a stated answer rather than an exception: an unreadable question,
    a ticker that is not listed, or a venue that will not answer each come back
    as a sentence saying so. Bodies over 4 KB are refused.</p>
    <p class="note"><b>Estimated, never observed.</b> Every figure the endpoint
    returns is marked <code>estimated</code>. It is what the displayed book says
    an exit would cost, not a fill anyone received.</p>

    <h2 id="cli">Command line</h2>
    <div class="scroll">
    <table class="tbl">
      <thead><tr><th>Command</th><th>What it does</th></tr></thead>
      <tbody>
        <tr><td class="sym">crawl --once</td><td class="dim">One snapshot of the
          whole listed universe.</td></tr>
        <tr><td class="sym">crawl --loop --hours N</td><td class="dim">Snapshot
          every five minutes for N hours, then exit.</td></tr>
        <tr><td class="sym">crawl --interval S</td><td class="dim">Override the
          interval, in seconds.</td></tr>
        <tr><td class="sym">crawl --universe</td><td class="dim">Refresh the
          instrument list and print the counts by type.</td></tr>
        <tr><td class="sym">crawl --coverage</td><td class="dim">What the record
          holds, and where the gaps are.</td></tr>
        <tr><td class="sym">python -m egress.page</td><td class="dim">Rebuild
          every page in docs/ from the record.</td></tr>
      </tbody>
    </table>
    </div>

    <h2 id="limits">Limitations</h2>
    <p class="say">Stated here rather than buried, because a research tool that
    hides its limits is a marketing tool.</p>
    <ul class="say">
      <li><b>A quote is not a fill.</b> Displayed size can be withdrawn before
      anyone reaches it, and a real order moves the book it was measured
      against. Every cost here is an estimate of the displayed book.</li>
      <li><b>The record is short.</b> The snapshot count behind every table is
      printed next to it. Nothing here is a claim about the future, and a
      handful of days is not a study.</li>
      <li><b>Replenishment is unobservable from a snapshot.</b> That is why
      slicing is answered as a best and a worst case rather than a
      number.</li>
      <li><b>Two of the venue's volume feeds disagree on tokenized stocks.</b>
      Which one is right cannot be settled from outside, so those symbols are
      excluded from validation and named on the validation page.</li>
      <li><b>Idle and phantom liquidity look identical.</b> Displayed size going
      unconsumed could mean it was withdrawn or that nobody wanted it. This data
      cannot separate them.</li>
      <li><b>Research only.</b> Not advice, not an offer, not a quote.</li>
    </ul>

    <h2 id="glossary">Glossary</h2>
    <div class="scroll">
    <table class="tbl">
      <thead><tr><th>Term</th><th>Meaning here</th></tr></thead>
      <tbody>
        <tr><td class="sym">bp</td><td class="dim">Basis point, one hundredth of
          a percent. 100 bp is 1%.</td></tr>
        <tr><td class="sym">mid</td><td class="dim">Midpoint of the best bid and
          best ask. The reference every cost on this site is measured
          from.</td></tr>
        <tr><td class="sym">touch</td><td class="dim">The top of the book - the
          best bid and best ask and the size resting on each.</td></tr>
        <tr><td class="sym">floor</td><td class="dim">A cost marked
          <span class="sym">&gt;</span>: the displayed book ran out before the
          position did, so the true cost is at least this.</td></tr>
        <tr><td class="sym">phase</td><td class="dim">open, overnight, weekend or
          holiday, decided from the venue's own timestamp against US equity
          market hours.</td></tr>
        <tr><td class="sym">control</td><td class="dim">The crypto pairs. Same
          venue, same engine, same fees, no reason to care whether New York is
          open.</td></tr>
        <tr><td class="sym">tokenized stock</td><td class="dim">An instrument the
          venue reports with symbolType <code>stock</code>, tracking a US listed
          share.</td></tr>
      </tbody>
    </table>
    </div>

    <div class="caveat">Every number on this site is regenerated from the record
    each time the crawler commits. If a figure here disagrees with the
    repository, the repository is right and this page is stale - check the
    generation stamp in the footer.</div>
  </section>
</div>
"""


# ------------------------------------------------------------------ rendering

PAGES = (
    ("index.html", "Egress - what it costs to leave", index_body, True,
     "Exit liquidity for tokenized US stocks on Bitget, measured from the book "
     "that exists, at the size you actually hold."),
    ("evidence.html", "Evidence - Egress", evidence_body, False,
     "Spread on tokenized US stocks by market phase, against a crypto control "
     "group on the same venue."),
    ("validation.html", "Validation - Egress", validation_body, False,
     "Whether a displayed quote is worth anything: resting size held against "
     "the volume that actually printed."),
    ("method.html", "Method - Egress", method_body, False,
     "How an exit cost is computed: the mid as reference, the walk, the taker "
     "fee, and where an estimate becomes a floor."),
    ("docs.html", "Docs - Egress", docs_body, False,
     "Run the crawler, read the record format, call the endpoint, and see "
     "every limitation stated in one place."),
)


def render(name: str = "index.html", f: dict | None = None) -> str:
    """One page of the site, by filename."""
    f = f or facts.build()
    for file, title, body, script, description in PAGES:
        if file == name:
            return shell(title=title, description=description, here=file,
                         body=body(f), f=f, script=script)
    raise KeyError(name)


def write(out: Path | None = None) -> Path:
    out = out or OUT
    out.mkdir(parents=True, exist_ok=True)
    f = facts.build()
    # The desk compares one answer against the record; write the comparison out
    # here so a question costs a small file read rather than a full record read.
    facts.save_benchmark(snapshots=f["snapshots"])
    for file, *_ in PAGES:
        (out / file).write_text(render(file, f), encoding="utf-8")
    # External rather than inline so the CSP can stay script-src 'self' with no
    # unsafe-inline for scripts.
    (out / "desk.js").write_text(DESK_JS, encoding="utf-8")
    return out / "index.html"


if __name__ == "__main__":
    path = write()
    print(f"wrote {len(PAGES)} pages into {path.parent}")
