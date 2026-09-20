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

  Array.prototype.forEach.call(form.querySelectorAll('[data-example]'), function (b) {
    b.addEventListener('click', function () {
      $('kformula').value = b.getAttribute('data-formula');
      $('kroles').value = b.getAttribute('data-roles');
      $('kexample-note').textContent = b.getAttribute('title') || '';
      translate();
    });
  });

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
