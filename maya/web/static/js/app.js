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

  function applyTheme(t) {
    var root = document.documentElement;
    if (t) { root.setAttribute('data-theme', t); root.setAttribute('data-bs-theme', t); }
  }
  try { applyTheme(localStorage.getItem('maya.theme')); } catch (e) { /* storage blocked */ }
  var toggle = document.getElementById('theme-toggle');
  if (toggle) {
    toggle.addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme') ||
        (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      var next = cur === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      try { localStorage.setItem('maya.theme', next); } catch (e) { /* ignore */ }
    });
  }

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
          } else if (el.hasAttribute('data-reload')) {
            setTimeout(function () { location.reload(); }, 600);
          }
        })
        .catch(function () { setTimeout(tick, 2000); });
    }
    tick();
  }
  document.querySelectorAll('[data-job-id]').forEach(pollJob);

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
