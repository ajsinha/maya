/*
 * app.js — MAYA's page behaviours. The CSP is `script-src 'self'`, so there is no
 * inline script anywhere: pages declare behaviour with data-* attributes.
 *   [data-latex]            render a LaTeX string with KaTeX (display mode)
 *   textarea[data-json]     validate JSON as you type
 *   form[data-confirm]      confirm before submitting
 *   [data-job-id]           poll /ui/jobs/<id> and show progress (aria-live)
 *   [data-add-row=<tpl>]    append a clone of <template id=tpl> to its target
 *   .remove-row             remove the enclosing [data-row]
 *   [data-toggle-show]      show the element whose id matches the selected value
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';
  var csrf = document.body.getAttribute('data-csrf') || '';
  window.MayaCsrf = csrf;

  // Four themes: crimson (stored as "light", so preferences saved before there were four
  // still mean what they meant), dark, blue and green. Only dark is dark to Bootstrap; the
  // other three are light schemes with a different accent.
  var THEMES = ['light', 'dark', 'blue', 'green'];

  function applyTheme(t) {
    var root = document.documentElement;
    if (!t || THEMES.indexOf(t) < 0) { return; }
    root.setAttribute('data-theme', t);
    root.setAttribute('data-bs-theme', t === 'dark' ? 'dark' : 'light');
    document.querySelectorAll('[data-theme-choice]').forEach(function (b) {
      b.setAttribute('aria-checked', b.getAttribute('data-theme-choice') === t ? 'true' : 'false');
    });
  }

  function chooseTheme(t) {
    applyTheme(t);
    try { localStorage.setItem('maya.theme', t); } catch (e) { /* storage blocked */ }
  }

  try { applyTheme(localStorage.getItem('maya.theme')); } catch (e) { /* storage blocked */ }
  document.querySelectorAll('[data-theme-choice]').forEach(function (b) {
    b.addEventListener('click', function (ev) {
      ev.preventDefault();
      chooseTheme(b.getAttribute('data-theme-choice'));
    });
  });

  // Mega menu: on a wide screen a panel opens on hover as well as on click/keyboard.
  var wide = window.matchMedia('(min-width: 992px)');
  document.querySelectorAll('.maya-nav .mega').forEach(function (li) {
    var toggle = li.querySelector('[data-bs-toggle="dropdown"]');
    var timer = null;
    if (!toggle || !window.bootstrap) return;
    var dd = window.bootstrap.Dropdown.getOrCreateInstance(toggle);
    li.addEventListener('mouseenter', function () {
      if (!wide.matches) return;
      clearTimeout(timer);
      document.querySelectorAll('.maya-nav .mega .dropdown-toggle.show').forEach(function (t) {
        if (t !== toggle) window.bootstrap.Dropdown.getOrCreateInstance(t).hide();
      });
      timer = setTimeout(function () { dd.show(); }, 90);
    });
    li.addEventListener('mouseleave', function () {
      if (!wide.matches) return;
      clearTimeout(timer);
      timer = setTimeout(function () { dd.hide(); }, 180);
    });
  });

  // Help examples: copy the code block beside the button.
  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var code = btn.closest('figure').querySelector('pre');
      var done = function () { btn.innerHTML = '<i class="bi bi-check2"></i> Copied'; setTimeout(function () {
        btn.innerHTML = '<i class="bi bi-clipboard"></i> Copy'; }, 1500); };
      if (navigator.clipboard) { navigator.clipboard.writeText(code.innerText).then(done, function () {}); }
    });
  });

  // Help index: live search over the topic cards (no inline script: the CSP forbids it).
  (function () {
    var box = document.getElementById('help-q');
    var items = [].slice.call(document.querySelectorAll('.help-item'));
    var cats = [].slice.call(document.querySelectorAll('.help-cat'));
    var none = document.getElementById('help-none');
    if (!box) return;
    box.addEventListener('input', function () {
      var q = box.value.trim().toLowerCase(), any = false;
      items.forEach(function (it) {
        var hit = !q || (it.getAttribute('data-search') || '').indexOf(q) !== -1;
        it.hidden = !hit; if (hit) any = true;
      });
      cats.forEach(function (cat) {
        var visible = [].some.call(cat.querySelectorAll('.help-item'), function (i) { return !i.hidden; });
        cat.hidden = !visible; if (q) cat.open = true;
      });
      none.hidden = any;
    });
    document.querySelectorAll('.cat-chips .chip').forEach(function (chip) {
      chip.addEventListener('click', function () {
        var el = document.querySelector(chip.getAttribute('href')); if (el) el.open = true;
      });
    });
  })();

  document.addEventListener('keydown', function (ev) {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') {
      var s = document.getElementById('global-search');
      if (s) { ev.preventDefault(); s.focus(); s.select(); }
    }
  });

  function renderLatex(root) {
    if (!window.katex) { return; }
    (root || document).querySelectorAll('[data-latex]').forEach(function (el) {
      var tex = el.getAttribute('data-latex');
      if (!tex) { return; }
      try {
        window.katex.render(tex, el, { displayMode: el.getAttribute('data-inline') === null,
                                       throwOnError: false });
      } catch (e) { el.textContent = tex; }
    });
  }
  window.MayaLatex = renderLatex;
  renderLatex(document);

  document.querySelectorAll('textarea[data-json]').forEach(function (ta) {
    var note = document.createElement('div');
    note.className = 'small-muted mt-1';
    note.setAttribute('aria-live', 'polite');
    ta.parentNode.insertBefore(note, ta.nextSibling);
    function check() {
      if (!ta.value.trim()) { note.textContent = ''; ta.classList.remove('is-invalid'); return; }
      try { JSON.parse(ta.value); note.textContent = 'Valid JSON'; ta.classList.remove('is-invalid'); }
      catch (e) { note.textContent = 'Invalid JSON: ' + e.message; ta.classList.add('is-invalid'); }
    }
    ta.addEventListener('input', check);
    check();
  });

  document.querySelectorAll('form[data-confirm]').forEach(function (f) {
    f.addEventListener('submit', function (ev) {
      if (!window.confirm(f.getAttribute('data-confirm'))) { ev.preventDefault(); }
    });
  });

  function pollJob(el) {
    var id = el.getAttribute('data-job-id');
    var bar = el.querySelector('.progress-bar');
    var msg = el.querySelector('.job-msg');
    function tick() {
      fetch('/ui/jobs/' + encodeURIComponent(id), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          if (j.error) { msg.textContent = j.error; return; }
          if (bar) { bar.style.width = (j.progress || 0) + '%'; bar.textContent = (j.progress || 0) + '%'; }
          msg.textContent = j.state + (j.message ? ' — ' + j.message : '') + (j.error_text ? ' — ' + j.error_text : '');
          if (['succeeded', 'failed', 'cancelled', 'dead_letter'].indexOf(j.state) < 0) {
            setTimeout(tick, 700);
          } else {
            // drop ?job= so the reloaded page does not show (and reload for) the same job again
            var url = new URL(location.href);
            url.searchParams.delete('job');
            if (el.hasAttribute('data-reload') && j.state === 'succeeded') {
              setTimeout(function () { location.replace(url.toString()); }, 600);
            } else {
              history.replaceState(null, '', url.toString());
            }
          }
        })
        .catch(function () { setTimeout(tick, 2000); });
    }
    tick();
  }
  document.querySelectorAll('[data-job-id]').forEach(pollJob);

  // "About this page": collapsed once, it stays collapsed for this browser
  (function () {
    var box = document.getElementById('page-help');
    if (!box) { return; }
    try { if (window.localStorage.getItem('maya.pageHelp') === 'closed') { box.open = false; } } catch (e) { /* private window */ }
    box.addEventListener('toggle', function () {
      try { window.localStorage.setItem('maya.pageHelp', box.open ? 'open' : 'closed'); } catch (e) { /* private window */ }
    });
  }());

  document.addEventListener('click', function (ev) {
    var add = ev.target.closest('[data-add-row]');
    if (add) {
      var tpl = document.getElementById(add.getAttribute('data-add-row'));
      var target = document.getElementById(add.getAttribute('data-target'));
      if (tpl && target) { target.appendChild(tpl.content.cloneNode(true)); }
      return;
    }
    var rm = ev.target.closest('.remove-row');
    if (rm) {
      var row = rm.closest('[data-row]');
      if (row) { row.remove(); }
    }
  });

  document.querySelectorAll('select[data-toggle-show]').forEach(function (sel) {
    var group = sel.getAttribute('data-toggle-show');
    function sync() {
      document.querySelectorAll('[data-show-group="' + group + '"]').forEach(function (el) {
        var values = (el.getAttribute('data-show-when') || '').split(',');
        el.hidden = values.indexOf(sel.value) < 0;
      });
    }
    sel.addEventListener('change', sync);
    sync();
  });
})();
