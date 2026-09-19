/*
 * policy.js — the workflow policy editor (spec §10.6) as structured controls,
 * plus the state diagram drawn with its live population.
 * The policy record is edited here, validated server-side ("validate and
 * preview impact") and saved as a new draft version; nobody edits YAML.
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';
  var dataEl = document.getElementById('policy-data');
  if (!dataEl) { return; }
  var data = JSON.parse(dataEl.textContent);
  var policy = JSON.parse(JSON.stringify(data.policy || {}));
  policy.states = policy.states || ['draft'];
  policy.transitions = policy.transitions || {};
  var root = document.getElementById('policy-editor');
  var result = document.getElementById('policy-result');
  var CAPS = ['', 'C', 'R', 'U', 'A', 'P', 'G', 'Q'];

  function h(tag, attrs, kids) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') { el.textContent = attrs[k]; }
      else if (k === 'class') { el.className = attrs[k]; }
      else { el.setAttribute(k, attrs[k]); }
    });
    (kids || []).forEach(function (c) { if (c) { el.appendChild(c); } });
    return el;
  }
  function multiSelect(options, selected, label) {
    var sel = h('select', { 'class': 'form-select form-select-sm', multiple: 'multiple', size: String(Math.min(5, options.length || 1)), 'aria-label': label });
    options.forEach(function (o) {
      var opt = h('option', { value: o, text: o });
      if ((selected || []).indexOf(o) >= 0) { opt.selected = true; }
      sel.appendChild(opt);
    });
    return sel;
  }
  function single(options, value, label) {
    var sel = h('select', { 'class': 'form-select form-select-sm', 'aria-label': label });
    options.forEach(function (o) {
      var opt = h('option', { value: o, text: o || '—' });
      if (o === value) { opt.selected = true; }
      sel.appendChild(opt);
    });
    return sel;
  }
  function values(sel) { return Array.prototype.filter.call(sel.options, function (o) { return o.selected; }).map(function (o) { return o.value; }); }

  function renderStates() {
    var box = h('div', { 'class': 'card card-body mb-2' }, [h('h3', { text: 'States' })]);
    var chips = h('div', { 'class': 'd-flex flex-wrap gap-1 mb-2' });
    policy.states.forEach(function (s) {
      var chip = h('span', { 'class': 'pill' }, [document.createTextNode(s + ' (' + (data.population[s] || 0) + ')')]);
      if (s !== 'draft') {
        var x = h('button', { type: 'button', 'class': 'btn btn-sm p-0 ms-1', 'aria-label': 'Remove state ' + s, text: '×' });
        x.addEventListener('click', function () { policy.states = policy.states.filter(function (t) { return t !== s; }); draw(); });
        chip.appendChild(x);
      }
      chips.appendChild(chip);
    });
    var input = h('input', { 'class': 'form-control form-control-sm', placeholder: 'new state', 'aria-label': 'New state name', style: 'max-width:200px' });
    var add = h('button', { type: 'button', 'class': 'btn btn-sm btn-outline-secondary', text: '+ state' });
    add.addEventListener('click', function () {
      var v = input.value.trim();
      if (v && policy.states.indexOf(v) < 0) { policy.states.push(v); draw(); }
    });
    box.appendChild(chips);
    box.appendChild(h('div', { 'class': 'd-flex gap-1' }, [input, add]));
    return box;
  }

  function approvalRow(a, list) {
    var role = single([''].concat(data.roles), a.role || '', 'Approval role');
    var count = h('input', { type: 'number', min: '1', value: String(a.count || 1), 'class': 'form-control form-control-sm', style: 'max-width:70px', 'aria-label': 'Approvals needed' });
    var when = h('input', { value: a.when || '', placeholder: 'when (e.g. prod)', 'class': 'form-control form-control-sm', style: 'max-width:140px', 'aria-label': 'Condition' });
    var rm = h('button', { type: 'button', 'class': 'btn btn-sm btn-outline-secondary', text: '×', 'aria-label': 'Remove approval' });
    var row = h('div', { 'class': 'd-flex gap-1 mb-1', 'data-approval': '1' }, [role, count, when, rm]);
    rm.addEventListener('click', function () { row.remove(); });
    list.appendChild(row);
  }

  function transitionCard(name, t) {
    var card = h('div', { 'class': 'card card-body mb-2', 'data-transition': '1' });
    var nm = h('input', { value: name, 'class': 'form-control form-control-sm fw-bold', 'aria-label': 'Transition name', style: 'max-width:220px' });
    var sources = Array.isArray(t.from) ? t.from : (t.from ? [t.from] : []);
    var from = multiSelect(policy.states, sources, 'From states');
    var to = single(policy.states, t.to, 'To state');
    var cap = single(CAPS, t.capability || '', 'Capability letter');
    var roles = multiSelect(data.roles, t.roles || [], 'Roles allowed');
    var checks = multiSelect(data.checks, t.checks || [], 'Checks');
    var approvals = h('div');
    (t.approvals || []).forEach(function (a) { approvalRow(a, approvals); });
    var addA = h('button', { type: 'button', 'class': 'btn btn-sm btn-outline-secondary', text: '+ approval' });
    addA.addEventListener('click', function () { approvalRow({}, approvals); });
    var rm = h('button', { type: 'button', 'class': 'btn btn-sm btn-outline-secondary ms-auto', text: 'Remove transition' });
    rm.addEventListener('click', function () { card.remove(); });
    function col(label, el, width) { return h('div', { 'class': 'col-md-' + width }, [h('div', { 'class': 'form-label', text: label }), el]); }
    card.appendChild(h('div', { 'class': 'd-flex align-items-center mb-2' }, [nm, rm]));
    card.appendChild(h('div', { 'class': 'row g-2' }, [
      col('From', from, 2), col('To', to, 2), col('Capability', cap, 1), col('Only roles', roles, 2),
      col('Checks', checks, 3), col('Approvals (role × count)', h('div', {}, [approvals, addA]), 2)]));
    card.__read = function () {
      var out = { from: values(from), to: to.value };
      if (cap.value) { out.capability = cap.value; }
      var r = values(roles); if (r.length) { out.roles = r; }
      var c = values(checks); if (c.length) { out.checks = c; }
      var appr = [];
      approvals.querySelectorAll('[data-approval]').forEach(function (row) {
        var f = row.querySelectorAll('select,input');
        if (f[0].value) {
          var a = { role: f[0].value, count: parseInt(f[1].value, 10) || 1 };
          if (f[2].value.trim()) { a.when = f[2].value.trim(); }
          appr.push(a);
        }
      });
      if (appr.length) { out.approvals = appr; }
      return [nm.value.trim(), out];
    };
    return card;
  }

  var extra = null;
  function draw() {
    var snapshot = collectTransitions();
    if (snapshot) { policy.transitions = snapshot; }
    root.innerHTML = '';
    root.appendChild(renderStates());
    var list = h('div', { id: 'transition-list' });
    Object.keys(policy.transitions).forEach(function (n) { list.appendChild(transitionCard(n, policy.transitions[n])); });
    root.appendChild(h('h3', { text: 'Transitions' }));
    root.appendChild(list);
    var add = h('button', { type: 'button', 'class': 'btn btn-sm btn-outline-secondary mb-2', text: '+ transition' });
    add.addEventListener('click', function () { list.appendChild(transitionCard('new_transition', { from: [], to: policy.states[0] })); });
    root.appendChild(add);
    var other = {};
    Object.keys(policy).forEach(function (k) { if (k !== 'states' && k !== 'transitions') { other[k] = policy[k]; } });
    extra = h('textarea', { 'class': 'form-control mono', rows: '4', 'aria-label': 'SLA and notification routing (JSON)' });
    extra.value = JSON.stringify(other, null, 2);
    root.appendChild(h('div', { 'class': 'form-label mt-2', text: 'SLA and notification routing (JSON: sla_days, notify)' }));
    root.appendChild(extra);
    drawDiagram();
  }

  function collectTransitions() {
    var cards = root.querySelectorAll('[data-transition]');
    if (!cards.length) { return null; }
    var out = {};
    cards.forEach(function (c) { var kv = c.__read(); if (kv[0]) { out[kv[0]] = kv[1]; } });
    return out;
  }

  function current() {
    var p = { states: policy.states.slice(), transitions: collectTransitions() || {} };
    try { Object.assign(p, JSON.parse(extra.value || '{}')); }
    catch (e) { throw new Error('SLA/notification JSON is invalid: ' + e.message); }
    return p;
  }

  function post(url, body) {
    return fetch(url, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.MayaCsrf },
      body: JSON.stringify(body) }).then(function (r) { return r.json(); });
  }

  function show(kind, lines) {
    result.innerHTML = '';
    var box = h('div', { 'class': 'alert alert-' + kind });
    lines.forEach(function (l) { box.appendChild(h('div', { text: l })); });
    result.appendChild(box);
  }

  document.getElementById('policy-validate').addEventListener('click', function () {
    var p;
    try { p = current(); } catch (e) { show('danger', [e.message]); return; }
    post('/workflow/policies/validate', { object_type: data.object_type, policy: p }).then(function (r) {
      if (r.error) { show('danger', [r.error]); return; }
      var msgs = r.errors.length ? r.errors.map(function (e) { return '✗ ' + e; }) : ['✓ The policy is valid.'];
      show(r.errors.length ? 'danger' : 'success', msgs.concat((r.impact.messages || []).map(function (m) { return 'Impact: ' + m; })));
      policy.states = p.states; policy.transitions = p.transitions;
      drawDiagram();
    });
  });

  document.getElementById('policy-save').addEventListener('click', function () {
    var p;
    try { p = current(); } catch (e) { show('danger', [e.message]); return; }
    post('/workflow/policies/save', { object_type: data.object_type, policy: p, scope: data.scope,
      note: document.getElementById('policy-note').value }).then(function (r) {
      if (r.error) { show('danger', [r.error].concat(((r.context || {}).errors) || [])); return; }
      location.href = '/workflow/policies/' + r.id;
    });
  });

  function drawDiagram() {
    var box = document.getElementById('state-diagram');
    if (!box) { return; }
    var level = { draft: 0 }, queue = ['draft'], ts = policy.transitions;
    while (queue.length) {
      var s = queue.shift();
      Object.keys(ts).forEach(function (n) {
        var t = ts[n], src = Array.isArray(t.from) ? t.from : [t.from];
        if (src.indexOf(s) >= 0 && level[t.to] === undefined) { level[t.to] = level[s] + 1; queue.push(t.to); }
      });
    }
    var byLevel = {}, pos = {};
    policy.states.forEach(function (st) {
      var l = level[st] === undefined ? 99 : level[st];
      (byLevel[l] = byLevel[l] || []).push(st);
    });
    var levels = Object.keys(byLevel).map(Number).sort(function (a, b) { return a - b; });
    levels.forEach(function (l, i) { byLevel[l].forEach(function (st, j) { pos[st] = { x: 80 + i * 170, y: 50 + j * 80 }; }); });
    var W = 160 + levels.length * 170, H = 60 + Math.max.apply(null, levels.map(function (l) { return byLevel[l].length; })) * 80;
    var ns = 'http://www.w3.org/2000/svg', css = getComputedStyle(document.documentElement);
    function tok(n) { return css.getPropertyValue(n).trim(); }
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H); svg.setAttribute('width', '100%'); svg.setAttribute('role', 'img');
    svg.innerHTML = '<defs><marker id="arr" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0L10,5L0,10z" fill="' + tok('--maya-slate') + '"/></marker></defs>';
    Object.keys(ts).forEach(function (n) {
      var t = ts[n], src = Array.isArray(t.from) ? t.from : [t.from];
      src.forEach(function (sname) {
        var a = pos[sname], b = pos[t.to];
        if (!a || !b) { return; }
        var path = document.createElementNS(ns, 'path');
        var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2 - (a.x === b.x ? 0 : 18);
        path.setAttribute('d', 'M' + a.x + ',' + a.y + ' Q' + mx + ',' + my + ' ' + b.x + ',' + b.y);
        path.setAttribute('fill', 'none'); path.setAttribute('stroke', tok('--maya-slate')); path.setAttribute('marker-end', 'url(#arr)');
        svg.appendChild(path);
        var label = document.createElementNS(ns, 'text');
        label.setAttribute('x', mx); label.setAttribute('y', my - 2); label.setAttribute('text-anchor', 'middle');
        label.setAttribute('font-size', '10'); label.textContent = n;
        svg.appendChild(label);
      });
    });
    policy.states.forEach(function (st) {
      var p = pos[st], g = document.createElementNS(ns, 'g');
      var c = document.createElementNS(ns, 'rect');
      c.setAttribute('x', p.x - 62); c.setAttribute('y', p.y - 18); c.setAttribute('width', 124); c.setAttribute('height', 36); c.setAttribute('rx', 18);
      c.setAttribute('fill', tok('--maya-surface'));
      c.setAttribute('stroke', level[st] === undefined ? tok('--maya-bad') : tok('--maya-crimson'));
      c.setAttribute('stroke-width', '2');
      var tx = document.createElementNS(ns, 'text');
      tx.setAttribute('x', p.x); tx.setAttribute('y', p.y + 4); tx.setAttribute('text-anchor', 'middle');
      tx.textContent = st + ' · ' + (data.population[st] || 0) + (level[st] === undefined ? ' (unreachable)' : '');
      g.appendChild(c); g.appendChild(tx); svg.appendChild(g);
    });
    box.innerHTML = '';
    box.appendChild(svg);
  }

  draw();
})();
