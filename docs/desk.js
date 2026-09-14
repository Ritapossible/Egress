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
    if (q.total_bp === q.total_bp) {
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
          Number(p.best_case_bp).toFixed(0) + ' to '
          + Number(p.worst_case_bp).toFixed(0) + ' bp');
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

  function ask(question) {
    if (!question.trim()) return;
    button.disabled = true;
    out.innerHTML = '<div class="ans"><p class="big">Reading the question, then '
      + 'the book...</p></div>';
    fetch('/api/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({q: question})
    }).then(function (r) { return r.json(); })
      .then(render)
      .catch(function (e) {
        out.innerHTML = '<div class="ans"><p class="big bad">The desk could not '
          + 'be reached: ' + esc(e.message || e) + '</p></div>';
      })
      .then(function () { button.disabled = false; });
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
