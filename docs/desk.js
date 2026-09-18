/* The desk's only script. Progressive: with JS off the form posts nowhere
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
    // A name the site publicly calls unreliable says so where it is priced.
    if (data.feed_note) html += '<p class="ctx">' + esc(data.feed_note) + '</p>';
    if (data.depth_note) html += '<p class="warn">' + esc(data.depth_note) + '</p>';
    if (data.advice) html += '<p class="advice">' + esc(data.advice) + '</p>';

    // Everything a reader might want to check, one tap away and never lost.
    html += '<details class="working"><summary>Show the working</summary><dl>';
    html += row('Ticker', (spec.ticker || '-') + ' · ' + (data.symbol || '-'));
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
    // The comparison's own working. A reader who is told the spread is "wider
    // than usual for this name" is owed the two numbers that produced it.
    var v = data.verdict || {};
    if (v.quote_spread_bp !== null && v.quote_spread_bp !== undefined) {
      html += row('Quote spread now', Number(v.quote_spread_bp).toFixed(2) + ' bp');
    }
    if (v.p50_bp) {
      html += row('This name, ' + (v.phase || '') + ' median',
        Number(v.p50_bp).toFixed(2) + ' bp over ' + v.snapshots + ' readings');
      html += row('This name, ' + (v.phase || '') + ' p90',
        Number(v.p90_bp).toFixed(2) + ' bp');
    }
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

    // Two lists, not one. What no tool can see all pushes the cost the same
    // way; what you can substitute is a different claim and says so.
    var limits = q.limits || {};
    var unseen = limits.cannot_see || data.unverified || [];
    if (unseen.length) {
      html += '<p class="sub-head">What this cannot see'
        + '<em> - all of it makes the real cost higher, never lower</em></p><ul>';
      unseen.forEach(function (u) { html += '<li>' + esc(u) + '</li>'; });
      html += '</ul>';
    }
    if ((limits.can_correct || []).length) {
      html += '<p class="sub-head">What you can correct for</p><ul>';
      limits.can_correct.forEach(function (u) {
        html += '<li>' + esc(u) + '</li>';
      });
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
