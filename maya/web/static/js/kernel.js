/*
 * kernel.js — the compute-kernel wizard (§8.1, §28.6).
 *
 * The page sends written mathematics to /ui/kernel and shows three things back: the LaTeX
 * MAYA renders from the tree it parsed, the typed IR a model version would store, and one
 * self-contained Python function that computes it. All three come from one call, because
 * they are three renderings of one translation and must never disagree.
 *
 * Nothing here parses mathematics in the browser. A formula the server cannot read is
 * refused by the server, with its reason, which is the same refusal `models.create` would
 * give — the point of the wizard is to meet it here instead of there.
 *
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';

  var form = document.getElementById('kernel-form');
  if (!form) { return; }

  function $(id) { return document.getElementById(id); }

  function show(el, on) { el.classList.toggle('d-none', !on); }

  function math(tex) {
    if (!window.katex) { return '<code>' + tex + '</code>'; }
    try {
      return window.katex.renderToString(tex, { displayMode: true, throwOnError: false });
    } catch (e) {
      return '<code>' + tex + '</code>';
    }
  }

  function text(el, value) { el.textContent = value; }

  function fill(out) {
    // The rendered mathematics comes back as one `\begin{aligned}` block when there are
    // intermediates, so it is handed to KaTeX whole rather than line by line.
    $('kmath').innerHTML = out.latex ? math(out.latex) : '';
    text($('koutput'), out.output.name + ' : ' + out.output.type);
    text($('klets'), out.lets.length ? out.lets.join(' → ') : 'none — the output is one expression');
    text($('khash'), out.ir_hash);
    $('kinputs').innerHTML = out.inputs.map(function (i) {
      return '<dt class="mono">' + i.name + '</dt><dd>' + (i.role || 'feature') +
        ' \u00b7 <span class="mono">' + (i.type || 'float64') + '</span></dd>';
    }).join('');
    text($('kir'), JSON.stringify(out.ir, null, 2));
    text($('kpy'), out.python);
    $('kcarry-formula').value = $('kformula').value;
    $('kcarry-roles').value = $('kroles').value;
  }

  function translate(ev) {
    if (ev) { ev.preventDefault(); }
    var body = new FormData();
    body.append('formula', $('kformula').value);
    body.append('roles', $('kroles').value);
    body.append('name', $('kname').value || 'compute');
    body.append('csrf_token', form.querySelector('[name=csrf_token]').value);
    var button = $('ktranslate');
    button.disabled = true;
    show($('khint'), false);
    fetch('/ui/kernel', { method: 'POST', body: body, credentials: 'same-origin' })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok) {
          // The server's own words. A parse failure names the line it choked on and a bad
          // IR names every rule it broke, and either is more use than "could not translate".
          var detail = (res.body.context && res.body.context.errors) || [];
          $('kerror').innerHTML = '<strong>' + (res.body.error || 'Could not translate that.') +
            '</strong>' + (detail.length ? '<ul class="mb-0 mt-1"><li>' +
              detail.join('</li><li>') + '</li></ul>' : '');
          show($('kerror'), true);
          show($('kresult'), false);
          return;
        }
        show($('kerror'), false);
        fill(res.body);
        show($('kresult'), true);
      })
      .catch(function () {
        $('kerror').textContent = 'The translation did not reach the server. Try again.';
        show($('kerror'), true);
      })
      .then(function () { button.disabled = false; });
  }

  form.addEventListener('submit', translate);

  // ---- the template library ---------------------------------------------------------
  var items = Array.prototype.slice.call(form.querySelectorAll('.kt-item'));
  var groups = Array.prototype.slice.call(form.querySelectorAll('.kt-group'));

  items.forEach(function (b) {
    b.addEventListener('click', function () {
      items.forEach(function (o) { o.setAttribute('aria-selected', 'false'); });
      b.setAttribute('aria-selected', 'true');
      $('kformula').value = b.getAttribute('data-formula');
      $('kroles').value = b.getAttribute('data-roles');
      $('kexample-note').textContent = b.getAttribute('data-note') || '';
      translate();
    });
  });

  // Search over the title, the group, the key and a list of the words practitioners use
  // that are not in the title -- somebody looking for a swaption should find Black-76, and
  // somebody typing "cva" should not be told there is nothing here rather than being shown
  // the hazard rate. Every term has to match, so two words narrow rather than widen.
  function filterTemplates() {
    var q = ($('ktsearch').value || '').toLowerCase().trim();
    var terms = q ? q.split(/\s+/) : [];
    var shown = 0;
    items.forEach(function (b) {
      var hay = b.getAttribute('data-hay') || '';
      var hit = terms.every(function (t) { return hay.indexOf(t) > -1; });
      b.hidden = !hit;
      if (hit) { shown += 1; }
    });
    groups.forEach(function (g) {
      var any = Array.prototype.some.call(g.querySelectorAll('.kt-item'), function (b) {
        return !b.hidden;
      });
      g.hidden = !any;
    });
    var count = $('ktcount');
    if (count) {
      count.textContent = !terms.length
        ? ''
        : (shown === 0
          ? 'Nothing matches ' + q + '. The library is a starting point, not a limit \u2014 write the mathematics straight into the box above.'
          : shown + ' of ' + items.length + ' shown.');
    }
  }

  var search = $('ktsearch');
  if (search) {
    search.addEventListener('input', filterTemplates);
    // Enter on a single remaining match loads it, which is what somebody who has just
    // typed four letters to find one formula expects to happen next.
    search.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter') { return; }
      ev.preventDefault();
      var visible = items.filter(function (b) { return !b.hidden; });
      if (visible.length === 1) { visible[0].click(); }
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll('[data-copy]'), function (b) {
    b.addEventListener('click', function () {
      var src = $(b.getAttribute('data-copy'));
      if (!src || !navigator.clipboard) { return; }
      navigator.clipboard.writeText(src.textContent).then(function () {
        var was = b.textContent;
        b.textContent = 'Copied';
        window.setTimeout(function () { b.textContent = was; }, 1200);
      });
    });
  });
}());
