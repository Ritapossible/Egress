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

  function render(data) {
    if (data.error) {
      out.innerHTML = '<div class="ans"><p class="big bad">' + esc(data.error)
        + '</p></div>';
      return;
    }
    var q = data.quote || {};
    var html = '<div class="ans"><p class="big">' + esc(data.reading || '')
      + '</p><dl>';
    html += row('Symbol', data.symbol || '-');
    html += row('Position', Number(q.requested_usdt || 0).toLocaleString() + ' USDT');
    if (q.quotable) {
      var floor = (q.exhausted || q.source === 'touch') ? '>' : '';
      html += row('One clip', floor + Number(q.total_bp).toFixed(0) + ' bp');
      html += row('In USDT', floor + Number(q.total_usdt).toLocaleString());
    }
    html += row('Book on that side', Number(q.book_usdt || 0).toLocaleString() + ' USDT');
    if (data.max_exit_200bp !== undefined) {
      html += row('Most you can exit under 200 bp',
                  Number(data.max_exit_200bp).toLocaleString() + ' USDT');
    }
    html += row('Depth source', q.source === 'touch' ? 'top of book only' : (q.source || '-'));
    html += row('Market phase', data.phase || '-');
    html += '</dl>';

    if (data.plan && data.plan.length) {
      html += '<dl>';
      data.plan.forEach(function (p) {
        html += row(p.slices + (p.slices === 1 ? ' clip' : ' clips'),
          p.quotable ? (Number(p.best_case_bp).toFixed(0) + ' to '
                        + Number(p.worst_case_bp).toFixed(0) + ' bp')
                     : 'unquotable');
      });
      html += '</dl>';
    }

    if (data.unverified && data.unverified.length) {
      html += '<ul>';
      data.unverified.forEach(function (u) { html += '<li>' + esc(u) + '</li>'; });
      html += '</ul>';
    }
    out.innerHTML = html + '</div>';
  }

  var inFlight = false;

  function fail(message) {
    out.innerHTML = '<div class="ans"><p class="big bad">' + esc(message)
      + '</p></div>';
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
