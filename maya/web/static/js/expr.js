/*
 * expr.js — the expression editor (spec §17.3).
 *
 * One grammar is used everywhere an expression appears — feature transforms, feature
 * set filters, ACL row filters — and this file is the browser's mirror of it. The
 * authority is maya/resolution/expr.py: the server parses, checks and evaluates every
 * expression again when it is saved, and refuses what it does not like. What the
 * mirror buys is the three things §17.3 asks for, without a round trip per keystroke:
 *
 *   autocomplete      over the attributes actually available here
 *   inline checking   the construct or the attribute name that is wrong, as you type
 *   a live preview    the expression evaluated over the first three sample rows
 *
 * The mirror is deliberately strict in the same places as the Python: attribute access,
 * subscripts, lambdas, comprehensions and unlisted calls are refused by name, `in` takes
 * a literal list, and only the listed functions exist. Where the two could disagree the
 * browser says so rather than promising: the panel names the server as the authority.
 *
 *   [data-expr]                  the input or textarea to upgrade
 *   [data-expr-attrs]            JSON: {name: type} or [name, …]
 *   [data-expr-attrs-from]       a selector of inputs whose values are attribute names
 *   [data-expr-sample]           a URL answering {columns, rows} for the live preview
 *   [data-expr-insert-into]      a selector: "add to the pipeline" writes a filter step
 *
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';

  // name -> [min args, max args, kind of result]
  var FUNCTIONS = {
    abs: [1, 1, 'number'], sqrt: [1, 1, 'number'], log: [1, 1, 'number'], exp: [1, 1, 'number'],
    min: [2, 8, 'number'], max: [2, 8, 'number'], where: [3, 3, 'any'],
    isnull: [1, 1, 'bool'], notnull: [1, 1, 'bool'], round: [1, 2, 'number'],
    clip: [3, 3, 'number'], year: [1, 1, 'number'], month: [1, 1, 'number'], day: [1, 1, 'number']
  };
  var KEYWORDS = ['and', 'or', 'not', 'in', 'if', 'else', 'True', 'False', 'None'];

  function fail(message, extra) {
    var err = new Error(message);
    err.maya = true;
    err.at = extra;
    return err;
  }

  // ---- tokens -------------------------------------------------------------------
  var OPS = ['**', '//', '<=', '>=', '==', '!=', '+', '-', '*', '/', '%', '<', '>', '(', ')', '[', ']', ','];

  function tokenize(text) {
    var out = [], i = 0, s = String(text);
    while (i < s.length) {
      var c = s.charAt(i);
      if (/\s/.test(c)) { i += 1; continue; }
      if (c === '"' || c === "'") {
        var j = s.indexOf(c, i + 1);
        if (j < 0) { throw fail('a string is not closed'); }
        out.push({ t: 'str', v: s.slice(i + 1, j), at: i });
        i = j + 1;
        continue;
      }
      if (/[0-9]/.test(c) || (c === '.' && /[0-9]/.test(s.charAt(i + 1)))) {
        var num = s.slice(i).match(/^[0-9]*\.?[0-9]+(e[+-]?[0-9]+)?/i)[0];
        out.push({ t: 'num', v: parseFloat(num), at: i });
        i += num.length;
        continue;
      }
      if (/[A-Za-z_]/.test(c)) {
        var name = s.slice(i).match(/^[A-Za-z_][A-Za-z_0-9]*/)[0];
        out.push({ t: 'name', v: name, at: i });
        i += name.length;
        continue;
      }
      if (c === '.') { throw fail("attribute access '.' is not permitted"); }
      if (c === '{' || c === '}' || c === ':') { throw fail("'" + c + "' is not permitted"); }
      var op = null;
      OPS.forEach(function (candidate) {
        if (!op && s.slice(i, i + candidate.length) === candidate) { op = candidate; }
      });
      if (!op) { throw fail("'" + c + "' is not part of the expression grammar"); }
      out.push({ t: 'op', v: op, at: i });
      i += op.length;
    }
    return out;
  }

  // ---- parser: the same shapes the Python checker allows ------------------------
  function parse(text) {
    var tokens = tokenize(text), pos = 0;

    function peek() { return tokens[pos]; }
    function isOp(v) { var t = peek(); return t && t.t === 'op' && t.v === v; }
    function isName(v) { var t = peek(); return t && t.t === 'name' && t.v === v; }
    function take() { return tokens[pos++]; }
    function expect(v) {
      if (!isOp(v)) { throw fail("expected '" + v + "'"); }
      return take();
    }

    function ternary() {
      var body = orExpr();
      if (isName('if')) {
        take();
        var test = orExpr();
        if (!isName('else')) { throw fail("a conditional needs 'else'"); }
        take();
        return { k: 'if', test: test, body: body, orelse: ternary() };
      }
      return body;
    }
    function orExpr() {
      var node = andExpr();
      while (isName('or')) { take(); node = { k: 'bool', op: 'or', l: node, r: andExpr() }; }
      return node;
    }
    function andExpr() {
      var node = notExpr();
      while (isName('and')) { take(); node = { k: 'bool', op: 'and', l: node, r: notExpr() }; }
      return node;
    }
    function notExpr() {
      if (isName('not')) { take(); return { k: 'not', v: notExpr() }; }
      return comparison();
    }
    function comparison() {
      var node = arith();
      while (true) {
        var op = null;
        ['<=', '>=', '==', '!=', '<', '>'].forEach(function (c) { if (!op && isOp(c)) { op = c; } });
        if (op) { take(); node = { k: 'cmp', op: op, l: node, r: arith() }; continue; }
        if (isName('in') || (isName('not') && tokens[pos + 1] && tokens[pos + 1].v === 'in')) {
          var negate = isName('not');
          if (negate) { take(); }
          take();
          if (!isOp('[') && !isOp('(')) { throw fail("'in' needs a literal list"); }
          node = { k: 'in', negate: negate, l: node, r: literalList() };
          continue;
        }
        return node;
      }
    }
    function literalList() {
      // The server accepts a list or a tuple of literals after `in`, so both are read
      // here; a parenthesised form without a comma is not a tuple, and it refuses that.
      var close = isOp('(') ? ')' : ']';
      take();
      var items = [], commas = 0;
      while (!isOp(close)) {
        var t = peek();
        if (!t) { throw fail('a list is not closed'); }
        if (t.t === 'num' || t.t === 'str') { items.push(take().v); }
        else if (t.t === 'name' && ['True', 'False', 'None'].indexOf(t.v) >= 0) {
          items.push({ True: true, False: false, None: null }[take().v]);
        } else { throw fail("an 'in' list holds literals only"); }
        if (isOp(',')) { take(); commas += 1; }
      }
      take();
      if (close === ')' && commas === 0) { throw fail("'in' needs a literal list"); }
      return items;
    }
    function arith() {
      var node = term();
      while (isOp('+') || isOp('-')) {
        var op = take().v;
        node = { k: 'bin', op: op, l: node, r: term() };
      }
      return node;
    }
    function term() {
      var node = unary();
      while (isOp('*') || isOp('/') || isOp('%') || isOp('//')) {
        var op = take().v;
        node = { k: 'bin', op: op, l: node, r: unary() };
      }
      return node;
    }
    function unary() {
      if (isOp('-') || isOp('+')) { var op = take().v; return { k: 'unary', op: op, v: unary() }; }
      return power();
    }
    function power() {
      var node = primary();
      if (isOp('**')) { take(); return { k: 'bin', op: '**', l: node, r: unary() }; }
      return node;
    }
    function primary() {
      var t = peek();
      if (!t) { throw fail('the expression ends too early'); }
      if (isOp('(')) {
        take();
        var inner = ternary();
        expect(')');
        return inner;
      }
      if (t.t === 'num') { take(); return { k: 'const', v: t.v, type: 'number' }; }
      if (t.t === 'str') { take(); return { k: 'const', v: t.v, type: 'string' }; }
      if (t.t === 'name') {
        take();
        if (['True', 'False'].indexOf(t.v) >= 0) { return { k: 'const', v: t.v === 'True', type: 'bool' }; }
        if (t.v === 'None') { return { k: 'const', v: null, type: 'null' }; }
        if (isOp('(')) {
          take();
          var args = [];
          while (!isOp(')')) {
            args.push(ternary());
            if (isOp(',')) { take(); }
            else if (!isOp(')')) { throw fail("expected ',' or ')'"); }
          }
          take();
          if (!FUNCTIONS[t.v]) {
            throw fail("function '" + t.v + "' is not permitted; the grammar has " +
              Object.keys(FUNCTIONS).sort().join(', '));
          }
          var range = FUNCTIONS[t.v];
          if (args.length < range[0] || args.length > range[1]) {
            throw fail("function '" + t.v + "' takes " + range[0] + '..' + range[1] + ' arguments');
          }
          return { k: 'call', name: t.v, args: args };
        }
        if (KEYWORDS.indexOf(t.v) >= 0) { throw fail("'" + t.v + "' is out of place here"); }
        return { k: 'name', v: t.v };
      }
      throw fail("'" + t.v + "' is out of place here");
    }

    if (!tokens.length) { throw fail('the expression is empty'); }
    var tree = ternary();
    if (pos < tokens.length) { throw fail("'" + tokens[pos].v + "' is out of place here"); }
    return tree;
  }

  function refsOf(node, into) {
    into = into || [];
    if (!node || typeof node !== 'object') { return into; }
    if (node.k === 'name' && into.indexOf(node.v) < 0) { into.push(node.v); }
    ['l', 'r', 'v', 'test', 'body', 'orelse'].forEach(function (key) {
      if (node[key] && typeof node[key] === 'object') { refsOf(node[key], into); }
    });
    (node.args || []).forEach(function (a) { refsOf(a, into); });
    return into;
  }

  // ---- light typing: enough to catch the mistakes worth catching ----------------
  function kindOfType(t) {
    var s = String(t || '').toLowerCase();
    if (/int|float|decimal|number/.test(s)) { return 'number'; }
    if (/bool/.test(s)) { return 'bool'; }
    if (/date|timestamp/.test(s)) { return 'date'; }
    if (/string|str|text/.test(s)) { return 'string'; }
    return 'unknown';
  }

  function typeOf(node, attrs) {
    switch (node.k) {
      case 'const': return node.type;
      case 'name': return kindOfType(attrs[node.v]);
      case 'call': return FUNCTIONS[node.name][2];
      case 'cmp': case 'in': case 'bool': case 'not': return 'bool';
      case 'unary': return 'number';
      case 'if': return typeOf(node.body, attrs);
      case 'bin': {
        var l = typeOf(node.l, attrs), r = typeOf(node.r, attrs);
        if (l === 'string' && r === 'string' && node.op === '+') { return 'string'; }
        if (l === 'unknown' || r === 'unknown') { return 'unknown'; }
        if (l === 'string' || r === 'string') {
          throw fail('arithmetic mixes text with a number; cast one of them first');
        }
        return 'number';
      }
      default: return 'unknown';
    }
  }

  function typeCheck(node, attrs) {
    if (node.k === 'cmp') {
      var l = typeOf(node.l, attrs), r = typeOf(node.r, attrs);
      if ((l === 'string') !== (r === 'string') && l !== 'unknown' && r !== 'unknown') {
        throw fail('a comparison puts text against a number, which is never true');
      }
    }
    ['l', 'r', 'v', 'test', 'body', 'orelse'].forEach(function (key) {
      if (node[key] && typeof node[key] === 'object' && node[key].k) { typeCheck(node[key], attrs); }
    });
    (node.args || []).forEach(function (a) { typeCheck(a, attrs); });
    return typeOf(node, attrs);
  }

  // An ACL row filter may name the reader: the server substitutes @user.username and
  // @user.desk from the principal before it compiles, and refuses any other @user key
  // (maya/security/conditions.py). The mirror does the same, with a stand-in value, so
  // a legitimate filter is not flagged as broken here.
  var USER_KEYS = /@user\.(username|desk)\b/g;

  function substituteUser(text) {
    return String(text).replace(USER_KEYS, "'you'");
  }

  function check(text, attrs) {
    attrs = attrs || {};
    var known = Object.keys(attrs);
    if (!String(text).trim()) { return { ok: true, empty: true, refs: [], message: '' }; }
    text = substituteUser(text);
    if (text.indexOf('@user.') > -1) {
      return { ok: false, refs: [], message: 'Row filters may reference only @user.username and @user.desk' };
    }
    var tree;
    try { tree = parse(text); } catch (e) { return { ok: false, refs: [], message: e.message }; }
    var refs = refsOf(tree);
    var unknown = known.length ? refs.filter(function (r) { return known.indexOf(r) < 0; }) : [];
    if (unknown.length) {
      return {
        ok: false, refs: refs, tree: tree,
        message: 'unknown attribute ' + unknown.map(function (u) { return "'" + u + "'"; }).join(', ') +
          '; this expression may use ' + known.join(', ')
      };
    }
    var type;
    try { type = typeCheck(tree, attrs); } catch (e) { return { ok: false, refs: refs, message: e.message }; }
    return { ok: true, refs: refs, tree: tree, type: type, message: '' };
  }

  // ---- evaluation over the sample rows ------------------------------------------
  function isNull(v) { return v === null || v === undefined || (typeof v === 'number' && isNaN(v)); }

  function datePart(value, part) {
    var d = new Date(String(value));
    if (isNaN(d.getTime())) { return null; }
    return { year: d.getUTCFullYear(), month: d.getUTCMonth() + 1, day: d.getUTCDate() }[part];
  }

  function halfEven(v) {
    // numpy — and so the server — rounds a tie to the even neighbour, while
    // Math.round rounds a tie up. round(120.25, 1) is 120.2 in both, here.
    var floor = Math.floor(v), diff = v - floor;
    if (diff > 0.5) { return floor + 1; }
    if (diff < 0.5) { return floor; }
    return floor % 2 === 0 ? floor : floor + 1;
  }

  var CALLS = {
    abs: function (x) { return Math.abs(x); },
    sqrt: function (x) { return Math.sqrt(x); },
    log: function (x) { return Math.log(x); },
    exp: function (x) { return Math.exp(x); },
    min: function () { return Math.min.apply(null, arguments); },
    max: function () { return Math.max.apply(null, arguments); },
    where: function (c, a, b) { return c ? a : b; },
    isnull: function (x) { return isNull(x); },
    notnull: function (x) { return !isNull(x); },
    round: function (x, n) { var f = Math.pow(10, n || 0); return halfEven(x * f) / f; },
    clip: function (x, lo, hi) { return Math.min(Math.max(x, lo), hi); },
    year: function (x) { return datePart(x, 'year'); },
    month: function (x) { return datePart(x, 'month'); },
    day: function (x) { return datePart(x, 'day'); }
  };

  function evalNode(node, row) {
    switch (node.k) {
      case 'const': return node.v;
      case 'name':
        if (!(node.v in row)) { throw fail("the sample row has no '" + node.v + "'"); }
        return row[node.v];
      case 'unary': return node.op === '-' ? -evalNode(node.v, row) : +evalNode(node.v, row);
      case 'not': return !evalNode(node.v, row);
      case 'bool': {
        var left = evalNode(node.l, row);
        if (node.op === 'and') { return left ? evalNode(node.r, row) : left; }
        return left ? left : evalNode(node.r, row);
      }
      case 'if': return evalNode(node.test, row) ? evalNode(node.body, row) : evalNode(node.orelse, row);
      case 'in': {
        var v = evalNode(node.l, row);
        var found = node.r.indexOf(v) >= 0;
        return node.negate ? !found : found;
      }
      case 'cmp': {
        var a = evalNode(node.l, row), b = evalNode(node.r, row);
        switch (node.op) {
          case '<': return a < b;
          case '<=': return a <= b;
          case '>': return a > b;
          case '>=': return a >= b;
          case '==': return a === b;
          default: return a !== b;
        }
      }
      case 'bin': {
        var x = evalNode(node.l, row), y = evalNode(node.r, row);
        switch (node.op) {
          case '+': return typeof x === 'string' || typeof y === 'string' ? String(x) + String(y) : x + y;
          case '-': return x - y;
          case '*': return x * y;
          case '/': return x / y;
          case '%': return x % y;
          case '//': return Math.floor(x / y);
          default: return Math.pow(x, y);
        }
      }
      case 'call': {
        var args = node.args.map(function (a) { return evalNode(a, row); });
        return CALLS[node.name].apply(null, args);
      }
      default: throw fail('cannot evaluate this expression here');
    }
  }

  function evaluate(text, rows, attrs) {
    var verdict = check(text, attrs);
    if (!verdict.ok || verdict.empty) { return { ok: false, message: verdict.message, values: [] }; }
    var values = [];
    for (var i = 0; i < rows.length; i += 1) {
      try { values.push(evalNode(verdict.tree, rows[i])); }
      catch (e) { return { ok: false, message: e.message, values: values }; }
    }
    return { ok: true, values: values, message: '' };
  }

  window.MayaExpr = {
    tokenize: tokenize, parse: parse, check: check, evaluate: evaluate,
    refsOf: refsOf, FUNCTIONS: FUNCTIONS
  };

  // ---- the editor ---------------------------------------------------------------
  function esc(s) {
    return String(s === null || s === undefined ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function show(v) {
    if (v === null || v === undefined) { return '∅'; }
    if (typeof v === 'number' && !isFinite(v)) { return String(v); }
    if (typeof v === 'number') { return String(Math.round(v * 1e6) / 1e6); }
    return String(v);
  }

  function attrsOf(field) {
    var attrs = {};
    var declared = field.getAttribute('data-expr-attrs');
    if (declared) {
      try {
        var parsed = JSON.parse(declared);
        if (Array.isArray(parsed)) { parsed.forEach(function (n) { attrs[n] = ''; }); }
        else { Object.keys(parsed).forEach(function (k) { attrs[k] = parsed[k]; }); }
      } catch (e) { /* a page that sent nonsense checks syntax only */ }
    }
    var from = field.getAttribute('data-expr-attrs-from');
    if (from) {
      document.querySelectorAll(from).forEach(function (input) {
        var name = (input.value || '').trim();
        if (name) { attrs[name] = input.getAttribute('data-type') || attrs[name] || ''; }
      });
    }
    return attrs;
  }

  function upgrade(field) {
    var panel = document.createElement('div');
    panel.className = 'expr-panel';
    panel.innerHTML =
      '<div class="expr-status small" aria-live="polite"></div>' +
      '<div class="expr-hints small-muted"></div>' +
      '<div class="expr-preview small-muted"></div>';
    field.parentNode.insertBefore(panel, field.nextSibling);
    var statusEl = panel.querySelector('.expr-status');
    var hintsEl = panel.querySelector('.expr-hints');
    var previewEl = panel.querySelector('.expr-preview');
    var sample = null, sampleAsked = false;

    function word() {
      var upto = field.value.slice(0, field.selectionStart === null ? field.value.length : field.selectionStart);
      var m = upto.match(/[A-Za-z_][A-Za-z_0-9]*$/);
      return m ? m[0] : '';
    }

    function insert(name) {
      var at = field.selectionStart === null ? field.value.length : field.selectionStart;
      var head = field.value.slice(0, at).replace(/[A-Za-z_][A-Za-z_0-9]*$/, '');
      var tail = field.value.slice(at);
      var addition = FUNCTIONS[name] ? name + '(' : name;
      field.value = head + addition + tail;
      field.focus();
      field.selectionStart = field.selectionEnd = (head + addition).length;
      update();
    }

    function hints(attrs) {
      var prefix = word().toLowerCase();
      var names = Object.keys(attrs).concat(Object.keys(FUNCTIONS));
      var matching = names.filter(function (n) {
        return !prefix || n.toLowerCase().indexOf(prefix) === 0;
      }).slice(0, 12);
      hintsEl.innerHTML = matching.length
        ? 'Available: ' + matching.map(function (n) {
          return '<button type="button" class="btn btn-link btn-sm p-0 mono expr-hint" data-expr-hint="' +
            esc(n) + '">' + esc(n) + (FUNCTIONS[n] ? '()' : (attrs[n] ? ' <span class="small-muted">' + esc(attrs[n]) + '</span>' : '')) + '</button>';
        }).join(' · ')
        : '';
    }

    function preview(attrs) {
      var url = field.getAttribute('data-expr-sample');
      if (!url) {
        previewEl.innerHTML = '';
        return;
      }
      if (!sample) {
        previewEl.textContent = sampleAsked ? 'No sample rows to preview against.' : '';
        return;
      }
      var rows = (sample.rows || []).slice(0, 3);
      var out = evaluate(field.value, rows, attrs);
      previewEl.innerHTML = rows.length === 0
        ? 'No sample rows to preview against.'
        : rows.map(function (row, i) {
          var value = out.ok ? show(out.values[i]) : '—';
          return '<div class="mono">row ' + (i + 1) + ': ' +
            esc(Object.keys(row).slice(0, 4).map(function (k) { return k + '=' + show(row[k]); }).join(' ')) +
            ' → <strong>' + esc(value) + '</strong></div>';
        }).join('') + '<div>Three rows of the draft, evaluated here in the browser; the server ' +
        'evaluates the same grammar over the whole set when you save.</div>';
    }

    function update() {
      var attrs = attrsOf(field);
      var verdict = check(field.value, attrs);
      field.classList.toggle('is-invalid', !verdict.ok);
      statusEl.textContent = verdict.empty ? ''
        : verdict.ok ? 'Reads as ' + (verdict.type === 'bool' ? 'a condition' : 'a ' + verdict.type + ' expression') +
          ' over ' + (verdict.refs.length ? verdict.refs.join(', ') : 'no attribute') + '.'
          : verdict.message;
      statusEl.className = 'expr-status small ' + (verdict.ok ? 'small-muted' : 'expr-bad');
      hints(attrs);
      preview(attrs);
    }

    function loadSample() {
      var url = field.getAttribute('data-expr-sample');
      if (!url || sampleAsked) { return; }
      sampleAsked = true;
      fetch(url, { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (data) { sample = data.error ? null : data; update(); })
        .catch(function () { update(); });
    }

    panel.addEventListener('click', function (ev) {
      var hint = ev.target.closest('[data-expr-hint]');
      if (hint) { insert(hint.getAttribute('data-expr-hint')); }
    });
    field.addEventListener('input', update);
    field.addEventListener('focus', function () { loadSample(); update(); });

    var into = field.getAttribute('data-expr-insert-into');
    if (into) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-sm btn-outline-secondary mt-1';
      button.textContent = 'Add as a filter step';
      button.addEventListener('click', function () {
        var target = document.querySelector(into);
        if (!target || !check(field.value, attrsOf(field)).ok) { return; }
        var steps = [];
        try { steps = JSON.parse(target.value || '[]'); } catch (e) { steps = []; }
        if (!Array.isArray(steps)) { steps = []; }
        steps.push({ op: 'filter', expr: field.value.trim() });
        target.value = JSON.stringify(steps, null, 2);
        target.dispatchEvent(new Event('input', { bubbles: true }));
        statusEl.textContent = 'Added to the pipeline below.';
      });
      panel.appendChild(button);
    }
    update();
  }

  document.querySelectorAll('[data-expr]').forEach(upgrade);
})();
