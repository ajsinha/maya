/*
 * lineage.js — the lineage and algebra canvas (spec §16.3) on vendored Cytoscape.
 *
 * Object versions and pins are nodes, algebra operations are diamonds, and edges
 * are styled by type. What the canvas adds beyond drawing:
 *   direction and depth   re-fetched in place, no page reload
 *   filters               type, namespace, status, pinned-only, each stating what it removed
 *   collapse              an inheritance chain becomes one node with a depth badge
 *   clustering            beyond ~300 nodes, the far graph collapses into namespace counts
 *   overlays              freshness, approval, access and cost, recoloured and *worded*
 *   detail                hover or select a node (or a row of the table) for its facts
 *   review                added green, changed amber, removed struck through
 *   authoring             two features selected offer an operator; a set offers a pin
 *
 * Two rules the file keeps. Nothing is hidden silently: the count of objects the
 * server withheld (`hidden`) is drawn as its own node and said in words, and every
 * filter reports what it removed. And no meaning is carried by colour alone (§16.5):
 * every overlay writes its value into the node's label and into the node table.
 *
 * Data comes from /ui/lineage and /ui/lineage/cost, both thin proxies over the SDK.
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';

  var MAX_LABEL = 44;
  var CLUSTER_AT = 300;   // §16.3: beyond ~300 visible nodes, focus plus context
  var FOCUS_HOPS = 2;     // hops from the root that stay drawn in full when clustered
  var HIDDEN_ID = 'maya://hidden';

  // ---- pure helpers. Exported on window.MayaLineage so the browser tests can ----
  // ---- exercise them without a graph, and so a page can reuse the wording.  ----
  function bare(ref) { return String(ref).split('@')[0].split('#')[0]; }

  function kindOf(ref) {
    var s = String(ref);
    return s.indexOf('maya://') === 0 ? s.slice(7).split('/')[0] : 'other';
  }

  function isPin(ref) { return String(ref).indexOf('#') > -1; }

  function versionOf(ref) {
    var m = String(ref).match(/@v(\d+)$/);
    return m ? parseInt(m[1], 10) : null;
  }

  function shortLabel(ref) {
    var s = String(ref).replace(/^maya:\/\//, '');
    return s.length > MAX_LABEL ? '…' + s.slice(-(MAX_LABEL - 1)) : s;
  }

  function strike(text) {
    // Cytoscape has no text-decoration, so "removed" is struck through with the
    // combining long stroke overlay: the label really is struck out, in any font.
    return String(text).split('').join('̶') + '̶';
  }

  var OPERATORS = {
    project: { notation: 'π[attrs](F)', typing: 'a subset of the attributes; the index must be retained' },
    rename: { notation: 'ρ[a→b](F)', typing: 'pure metadata: the same data under new attribute names' },
    transform: { notation: 'τ[pipeline](F)', typing: 'the §5.4 pipeline applied to a feature' },
    union: { notation: 'F₁ ∪ F₂', typing: 'rows of both; the schemas must unify', collision: 'index collisions resolved by the declared policy (error, prefer_left, prefer_right)' },
    intersect: { notation: 'F₁ ∩ F₂', typing: 'rows whose index is in both', collision: 'values are taken from the priority side' },
    difference: { notation: 'F₁ ∖ F₂', typing: 'rows of the first absent from the second; index-only comparison' },
    compose: { notation: 'F₁ ⋈ F₂', typing: 'attributes of both, aligned on the index — widening' },
    coalesce: { notation: '⊕(F₁, F₂, …)', typing: 'the first non-null value across ordered inputs', collision: 'order is the policy: the earlier operand wins' },
    aggregate: { notation: 'γ[by, agg](F)', typing: 'a coarser index; the aggregation is declared per attribute' },
    lag: { notation: 'lag[n](F)', typing: 'the same shape, shifted along the index' },
    resample: { notation: 'resample[freq](F)', typing: 'a new index; an index change is a breaking class' },
    case: { notation: 'σ[cond](F₁, F₂)', typing: 'row-wise selection; the condition is an expression over index or attributes' },
    pivot: { notation: 'pivot[on, value](F)', typing: 'a new orientation; an index change is a breaking class' },
    unpivot: { notation: 'unpivot[into](F)', typing: 'a new orientation; an index change is a breaking class' },
    sample: { notation: 'sample[spec](F)', typing: 'a declared subset of the rows' }
  };

  function operatorInfo(ref) {
    var name = String(ref).indexOf('maya://op/') === 0 ? String(ref).split('/')[3] : '';
    var info = OPERATORS[name];
    if (!info) { return null; }
    return {
      name: name, notation: info.notation, typing: info.typing,
      collision: info.collision || 'no collision policy: this operator cannot collide'
    };
  }

  function edgeLabel(edge) {
    var type = edge.type, extra = edge.label;
    if (type === 'operand_of') { return extra ? 'operand ' + extra : 'operand_of'; }
    if (type === 'extends') { return extra ? 'extends ·' + extra : 'extends'; }
    if (type === 'derived_from' && extra) { return extra; }
    return type;
  }

  function extendsDetail(edge) {
    if (!edge.label) {
      return 'Inheritance. The override diff is not carried in the graph, so the ' +
        'count is not shown here; the child’s Definition tab holds it.';
    }
    return 'Inheritance with ' + edge.label + ' override(s). The child stores the diff, not a copy.';
  }

  function ageDays(iso, now) {
    if (!iso) { return null; }
    var then = Date.parse(String(iso).replace(' ', 'T'));
    if (isNaN(then)) { return null; }
    return Math.max(0, Math.floor(((now || Date.now()) - then) / 86400000));
  }

  function bytesText(n) {
    if (n === null || n === undefined) { return 'not priced'; }
    var units = ['B', 'kB', 'MB', 'GB', 'TB'], i = 0, v = Number(n);
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
    return (i === 0 ? v : v.toFixed(1)) + ' ' + units[i];
  }

  // Each overlay answers with a bucket (a colour class) and a word for the label.
  var OVERLAYS = {
    freshness: function (n) {
      var days = ageDays(n.meta && n.meta.updated, n.now);
      if (days === null) { return { ov: 'none', word: 'no date' }; }
      if (days < 7) { return { ov: 'ok', word: days + 'd' }; }
      if (days < 30) { return { ov: 'info', word: days + 'd' }; }
      if (days < 90) { return { ov: 'warn', word: days + 'd' }; }
      return { ov: 'bad', word: days + 'd' };
    },
    approval: function (n) {
      var meta = n.meta;
      if (!meta) { return { ov: 'none', word: 'not an object' }; }
      var v = versionOf(n.id);
      if (v !== null && meta.latest_version && v < meta.latest_version) {
        return { ov: 'none', word: 'v' + v + ', superseded by v' + meta.latest_version };
      }
      var state = meta.state || 'no version';
      if (state === 'approved' || state === 'published') { return { ov: 'ok', word: state }; }
      if (state === 'deprecated' || state === 'retired') { return { ov: 'none', word: state }; }
      return { ov: 'warn', word: state };
    },
    access: function (n) {
      if (n.id === HIDDEN_ID) { return { ov: 'bad', word: 'withheld' }; }
      if (n.meta) { return { ov: 'ok', word: 'you can read it' }; }
      return { ov: 'info', word: 'internal node' };
    },
    cost: function (n) {
      var p = n.cost;
      if (!p || p.bytes === null || p.bytes === undefined) { return { ov: 'none', word: 'not priced' }; }
      var text = bytesText(p.bytes) + (p.partial ? '+' : '');
      if (p.bytes === 0) { return { ov: 'none', word: 'nothing pinned' }; }
      if (p.bytes < 1048576) { return { ov: 'ok', word: text }; }
      if (p.bytes < 104857600) { return { ov: 'info', word: text }; }
      return { ov: 'warn', word: text };
    }
  };

  var LEGENDS = {
    freshness: 'Freshness — when the object last changed: under 7 days, under 30, under 90, older. A node with no date is drawn plain.',
    approval: 'Approval — the state of the object’s latest version. A node naming an older version says so instead of borrowing that state.',
    access: 'Access — what you can read. Everything drawn, you may read; internal nodes (operators, pins, warrants) carry no read check of their own; the withheld count is what the server left out.',
    cost: 'Cost — what this object’s sealed pins occupy: nothing, under 1 MB, under 100 MB, more. A "+" means only the first page of pins was summed.'
  };

  var MayaLineage = {
    bare: bare, kindOf: kindOf, isPin: isPin, versionOf: versionOf, shortLabel: shortLabel,
    strike: strike, edgeLabel: edgeLabel, extendsDetail: extendsDetail, operatorInfo: operatorInfo,
    ageDays: ageDays, bytesText: bytesText, overlays: OVERLAYS, legends: LEGENDS,
    CLUSTER_AT: CLUSTER_AT, HIDDEN_ID: HIDDEN_ID
  };
  window.MayaLineage = MayaLineage;

  // ---------------------------------------------------------------- the canvas
  var el = document.getElementById('cy');
  if (!el || !window.cytoscape) { return; }
  var root = el.getAttribute('data-root');
  var status = document.getElementById('cy-status');
  if (!root) { return; }

  var css = getComputedStyle(document.documentElement);
  function tok(n) { return css.getPropertyValue(n).trim() || '#888'; }

  function shape(kind) {
    return {
      op: 'diamond', feature: 'round-rectangle', featureset: 'rectangle', model: 'ellipse',
      warrant: 'hexagon', parameters: 'tag', execution: 'triangle', cluster: 'octagon',
      chain: 'round-diamond', hidden: 'round-octagon'
    }[kind] || 'round-rectangle';
  }

  function $(id) { return document.getElementById(id); }
  function val(id, dflt) { var e = $(id); return e ? (e.type === 'checkbox' ? e.checked : e.value) : dflt; }

  var state = {
    graph: null, cy: null, cost: null, now: Date.now(),
    direction: el.getAttribute('data-direction') || 'both',
    depth: el.getAttribute('data-depth') || '3',
    root: root, expandedChains: {}, expandedClusters: {}, selection: []
  };

  var review = (function () {
    var block = $('cy-review');
    if (!block) { return null; }
    try { return JSON.parse(block.textContent); } catch (e) { return null; }
  })();

  function reviewClass(id) {
    if (!review) { return null; }
    var b = bare(id);
    function has(list) {
      return (list || []).some(function (r) { return r === id || bare(r) === b; });
    }
    if (has(review.removed)) { return 'removed'; }
    if (has(review.added)) { return 'added'; }
    if (has(review.changed)) { return 'changed'; }
    return null;
  }

  // ---- the model the canvas draws: nodes with their meta, cost and review mark ----
  function nodeModel(n) {
    var g = state.graph;
    var meta = g.meta ? g.meta[bare(n.id)] : null;
    return {
      id: n.id, kind: n.kind, meta: meta, now: state.now,
      cost: state.cost && state.cost.items ? state.cost.items[bare(n.id)] : null,
      review: reviewClass(n.id)
    };
  }

  function statusOf(m) { return (m.meta && m.meta.state) || ''; }

  function passesFilters(m) {
    var type = val('cy-f-type', ''), ns = val('cy-f-namespace', ''),
      st = val('cy-f-status', ''), pinnedOnly = val('cy-f-pinned', false);
    if (m.id === HIDDEN_ID) { return true; }
    if (type && kindOf(m.id) !== type) { return false; }
    if (ns && (!m.meta || m.meta.namespace !== ns)) { return false; }
    if (st && statusOf(m) !== st) { return false; }
    if (pinnedOnly && !isPin(m.id)) { return false; }
    return true;
  }

  function neighbourhood(hops) {
    // Undirected hops from the root: the focus of the focus-plus-context layout.
    var near = {}, frontier = [state.root], adj = {};
    state.graph.edges.forEach(function (e) {
      (adj[e.source] = adj[e.source] || []).push(e.target);
      (adj[e.target] = adj[e.target] || []).push(e.source);
    });
    near[state.root] = true;
    for (var h = 0; h < hops; h += 1) {
      var next = [];
      frontier.forEach(function (id) {
        (adj[id] || []).forEach(function (other) {
          if (!near[other]) { near[other] = true; next.push(other); }
        });
      });
      frontier = next;
    }
    return near;
  }

  // Maximal inheritance chains: parent -extends-> child, where every node in the
  // middle has exactly one extends in, one extends out and no other edge, so
  // collapsing the chain loses nothing but the names.
  function chains() {
    var g = state.graph, deg = {}, ext = {}, extIn = {}, extOut = {};
    g.edges.forEach(function (e) {
      deg[e.source] = (deg[e.source] || 0) + 1;
      deg[e.target] = (deg[e.target] || 0) + 1;
      if (e.type !== 'extends') { return; }
      ext[e.source + '>' + e.target] = true;
      extOut[e.source] = (extOut[e.source] || 0) + 1;
      extIn[e.target] = (extIn[e.target] || 0) + 1;
    });
    function interior(id) {
      return extIn[id] === 1 && extOut[id] === 1 && deg[id] === 2;
    }
    var starts = Object.keys(ext).map(function (k) { return k.split('>'); })
      .filter(function (pair) { return !interior(pair[0]); });
    var out = [];
    starts.forEach(function (pair) {
      var path = [pair[0], pair[1]];
      while (interior(path[path.length - 1])) {
        var head = path[path.length - 1], found = null;
        g.edges.forEach(function (e) {
          if (e.type === 'extends' && e.source === head) { found = e.target; }
        });
        if (!found) { break; }
        path.push(found);
      }
      if (path.length > 2) { out.push(path); }
    });
    return out;
  }

  function build() {
    var g = state.graph, models = {}, shown = {}, removed = 0;
    g.nodes.forEach(function (n) { models[n.id] = nodeModel(n); });
    if (g.hidden) {
      models[HIDDEN_ID] = { id: HIDDEN_ID, kind: 'hidden', meta: null, now: state.now, review: null };
    }
    Object.keys(models).forEach(function (id) {
      if (passesFilters(models[id])) { shown[id] = true; } else { removed += 1; }
    });

    // Collapse: every chain not explicitly expanded becomes one node with a badge.
    var folded = {}, foldNodes = [];
    if (val('cy-collapse', false)) {
      chains().forEach(function (path) {
        var id = 'chain:' + path[0] + '..' + path[path.length - 1];
        if (state.expandedChains[id]) { return; }
        // Only the interior of the chain folds: its two ends carry other edges, and a
        // fold that swallowed them would hide relationships rather than tidy them.
        var inner = path.slice(1, path.length - 1).filter(function (x) { return shown[x]; });
        if (inner.length < 2) { return; }
        inner.forEach(function (x) { folded[x] = id; });
        foldNodes.push({ id: id, depth: inner.length, head: path[path.length - 1] });
      });
    }

    // Focus plus context: the far graph becomes one node per namespace, with a count.
    var clusterOf = {}, clusters = {};
    if (val('cy-cluster', false)) {
      var near = neighbourhood(FOCUS_HOPS);
      Object.keys(shown).forEach(function (id) {
        if (near[id] || folded[id] || id === HIDDEN_ID) { return; }
        var m = models[id], ns = (m.meta && m.meta.namespace) || 'no namespace';
        if (state.expandedClusters[ns]) { return; }
        clusterOf[id] = 'cluster:' + ns;
        clusters['cluster:' + ns] = (clusters['cluster:' + ns] || 0) + 1;
      });
    }

    function place(id) { return clusterOf[id] || folded[id] || id; }

    var overlay = val('cy-overlay', 'none');
    var elements = [], words = {};
    Object.keys(shown).forEach(function (id) {
      if (folded[id] || clusterOf[id]) { return; }
      var m = models[id], mark = OVERLAYS[overlay] ? OVERLAYS[overlay](m) : null;
      var name = shortLabel(id);
      if (m.meta && m.meta.name) { name = m.meta.namespace + '/' + m.meta.name + (versionOf(id) ? '@v' + versionOf(id) : ''); }
      if (id === HIDDEN_ID) { name = g.hidden + ' object(s) you may not read\n· withheld, counted not named'; }
      var word = mark ? mark.word : '';
      words[id] = word;
      var label = name + (word ? '\n· ' + word : '');
      if (m.review === 'removed') { label = strike(name) + '\n· removed'; }
      else if (m.review) { label = name + '\n· ' + m.review + (word ? ', ' + word : ''); }
      elements.push({
        data: {
          id: id, label: label, kind: id === HIDDEN_ID ? 'hidden' : m.kind,
          root: id === state.root ? 1 : 0, ov: mark ? mark.ov : '',
          review: m.review || '', ghost: id === HIDDEN_ID ? 1 : 0
        }
      });
    });
    foldNodes.forEach(function (c) {
      elements.push({
        data: {
          id: c.id, kind: 'chain', root: 0, ov: '', review: '',
          label: 'inheritance chain\n· ' + c.depth + ' version(s) folded'
        }
      });
    });
    Object.keys(clusters).forEach(function (id) {
      elements.push({
        data: {
          id: id, kind: 'cluster', root: 0, ov: '', review: '',
          label: 'namespace ' + id.slice('cluster:'.length) + '\n· ' + clusters[id] +
            ' node(s), click to expand'
        }
      });
    });
    var drawn = {};
    elements.forEach(function (e) { drawn[e.data.id] = true; });
    var seen = {};
    g.edges.forEach(function (e, i) {
      if (!shown[e.source] || !shown[e.target]) { return; }
      var s = place(e.source), t = place(e.target);
      if (s === t || !drawn[s] || !drawn[t]) { return; }
      var key = s + '|' + t + '|' + e.type;
      if (seen[key]) { return; }
      seen[key] = true;
      elements.push({
        data: { id: 'e' + i, source: s, target: t, type: e.type, raw: e.label || '', label: edgeLabel(e) }
      });
    });
    if (g.hidden && drawn[place(state.root)]) {
      elements.push({
        data: {
          id: 'e-hidden', source: HIDDEN_ID, target: place(state.root),
          type: 'withheld', raw: '', label: 'withheld'
        }
      });
    }
    return {
      elements: elements, removed: removed, words: words, models: models,
      shownCount: Object.keys(shown).length, clustered: Object.keys(clusters).length > 0
    };
  }

  var STYLE = function () {
    return [
      { selector: 'node', style: {
        'shape': function (n) { return shape(n.data('kind')); },
        'background-color': tok('--maya-surface'), 'border-color': tok('--maya-indigo'), 'border-width': 2,
        'label': 'data(label)', 'font-size': 10, 'color': tok('--maya-ink'), 'text-wrap': 'wrap',
        'text-max-width': 170, 'text-valign': 'bottom', 'text-margin-y': 4, 'width': 30, 'height': 22 } },
      { selector: 'node[kind = "op"]', style: { 'background-color': tok('--maya-crimson-tint'), 'border-color': tok('--maya-crimson') } },
      { selector: 'node[kind = "cluster"], node[kind = "chain"]', style: { 'width': 44, 'height': 34, 'background-color': tok('--maya-canvas'), 'border-style': 'dashed' } },
      { selector: 'node[ghost = 1]', style: { 'background-color': tok('--maya-canvas'), 'border-style': 'dashed', 'border-color': tok('--maya-slate') } },
      { selector: 'node[root = 1]', style: { 'border-color': tok('--maya-crimson'), 'border-width': 4 } },
      { selector: 'node[ov = "ok"]', style: { 'background-color': tok('--maya-ok'), 'border-color': tok('--maya-ok') } },
      { selector: 'node[ov = "warn"]', style: { 'background-color': tok('--maya-warn'), 'border-color': tok('--maya-warn') } },
      { selector: 'node[ov = "bad"]', style: { 'background-color': tok('--maya-bad'), 'border-color': tok('--maya-bad') } },
      { selector: 'node[ov = "info"]', style: { 'background-color': tok('--maya-indigo'), 'border-color': tok('--maya-indigo') } },
      { selector: 'node[ov = "none"]', style: { 'background-color': tok('--maya-surface'), 'border-color': tok('--maya-slate') } },
      { selector: 'node[review = "added"]', style: { 'border-color': tok('--maya-ok'), 'border-width': 5 } },
      { selector: 'node[review = "changed"]', style: { 'border-color': tok('--maya-warn'), 'border-width': 5 } },
      { selector: 'node[review = "removed"]', style: { 'border-color': tok('--maya-slate'), 'border-style': 'dotted', 'border-width': 4 } },
      { selector: 'node:selected', style: { 'border-color': tok('--maya-crimson-strong'), 'border-width': 5 } },
      { selector: 'edge', style: {
        'width': 1.5, 'line-color': tok('--maya-slate'), 'target-arrow-color': tok('--maya-slate'),
        'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'label': 'data(label)', 'font-size': 8,
        'color': tok('--maya-slate'), 'text-rotation': 'autorotate' } },
      { selector: 'edge[type = "extends"]', style: { 'target-arrow-shape': 'triangle', 'target-arrow-fill': 'hollow', 'width': 2 } },
      { selector: 'edge[type = "operand_of"]', style: { 'width': 1 } },
      { selector: 'edge[type = "member_of"]', style: { 'line-style': 'dashed' } },
      { selector: 'edge[type = "composite_member"]', style: { 'line-style': 'double', 'width': 4 } },
      { selector: 'edge[type = "pinned_as"]', style: { 'line-style': 'dotted', 'width': 2 } },
      { selector: 'edge[type = "withheld"]', style: { 'line-style': 'dotted', 'target-arrow-shape': 'none' } },
      { selector: 'edge[type = "trained_on"], edge[type = "executed_under"], edge[type = "parameterized_by"]',
        style: { 'width': 3.5, 'line-color': tok('--maya-indigo'), 'target-arrow-color': tok('--maya-indigo') } }
    ];
  };

  // ---- detail panel -------------------------------------------------------------
  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; });
  }

  function rows(pairs) {
    return '<dl class="kv mb-0">' + pairs.filter(function (p) { return p[1]; }).map(function (p) {
      return '<dt>' + esc(p[0]) + '</dt><dd>' + p[1] + '</dd>';
    }).join('') + '</dl>';
  }

  function nodeDetail(id, built) {
    var m = built.models[id];
    if (!m) {
      if (id.indexOf('cluster:') === 0) {
        return '<h4 class="h6">' + esc(id.slice(8)) + '</h4><p class="mb-0 small">A namespace cluster: ' +
          'the neighbourhood of the root is drawn in full, the rest is counted. Click it to expand.</p>';
      }
      if (id.indexOf('chain:') === 0) {
        return '<h4 class="h6">Folded inheritance chain</h4><p class="mb-0 small">Versions that inherit ' +
          'one from the next, with nothing else attached. Click it to expand.</p>';
      }
      return '';
    }
    if (id === HIDDEN_ID) {
      return '<h4 class="h6">Withheld</h4><p class="mb-0 small">' + esc(state.graph.hidden) +
        ' object(s) in this lineage are not drawn because you may not read them. They are counted, ' +
        'never named — and never quietly dropped.</p>';
    }
    var op = operatorInfo(id);
    if (op) {
      return '<h4 class="h6">Operator <code>' + esc(op.name) + '</code></h4>' + rows([
        ['Notation', '<span class="mono">' + esc(op.notation) + '</span>'],
        ['Typing rule', esc(op.typing)],
        ['Collision policy', esc(op.collision)]
      ]);
    }
    var meta = m.meta, word = built.words[id];
    var head = '<h4 class="h6">' + esc(shortLabel(id)) + '</h4>';
    if (!meta) {
      return head + '<p class="mb-0 small">' + (isPin(id)
        ? 'A pin: one immutable materialization of a version.'
        : 'An internal node: it carries no catalog record of its own.') + '</p>';
    }
    return head + rows([
      ['Type', esc(meta.type)],
      ['Namespace', esc(meta.namespace)],
      ['Owner', esc(meta.owner || 'nobody')],
      ['Latest', meta.latest_version ? 'v' + esc(meta.latest_version) + ' · ' + esc(meta.state) : ''],
      ['Last change', esc(meta.updated || '').slice(0, 19).replace('T', ' ')],
      ['Change class', esc(meta.change_class)],
      ['Re-approval', esc(meta.needs_reapproval)],
      ['Overlay', esc(word)],
      ['Open', meta.url ? '<a href="' + esc(meta.url) + '">' + esc(meta.namespace + '/' + meta.name) + '</a>' : '']
    ]) + '<div class="d-flex gap-1 mt-2"><button class="btn btn-sm btn-outline-secondary" type="button" ' +
      'data-cy-reroot="' + esc(id) + '">Re-root the view here</button></div>';
  }

  function setDetail(html) {
    var panel = $('cy-detail');
    if (panel) { panel.innerHTML = html || '<p class="small-muted mb-0">Hover or select a node for its detail.</p>'; }
  }

  // ---- authoring: the canvas is a surface to build from, not only a report -------
  function syncAuthor(built) {
    var panel = $('cy-author');
    if (!panel) { return; }
    var features = state.selection.filter(function (id) { return kindOf(id) === 'feature'; });
    var sets = state.selection.filter(function (id) { return kindOf(id) === 'featureset'; });
    var opSel = $('cy-operator');
    var open = $('cy-author-open');
    var note = $('cy-author-note') || { textContent: '' };
    if (features.length >= 2 && opSel && open) {
      open.hidden = false;
      open.setAttribute('href', '/workbench/features/new?operator=' + encodeURIComponent(opSel.value) +
        '&operands=' + encodeURIComponent(features.join(',')));
      note.textContent = features.length + ' features selected: the designer opens prefilled with this algebra.';
    } else if (open) {
      open.hidden = true;
      note.textContent = sets.length === 1
        ? 'One feature set selected — its Pins tab offers a cascade pin over every member.'
        : 'Select two or more feature nodes (shift-click) to build a derived feature from them.';
    }
    var pin = $('cy-author-pin');
    if (pin) {
      var one = state.selection.length === 1 ? state.selection[0] : null;
      var meta = one && built && built.models[one] ? built.models[one].meta : null;
      pin.hidden = !(meta && meta.url && (meta.type === 'feature' || meta.type === 'featureset'));
      if (!pin.hidden) {
        pin.setAttribute('href', meta.url + '?tab=pins');
        pin.textContent = meta.type === 'featureset' ? 'Cascade pin this set' : 'Pin this feature';
      }
    }
  }

  // ---- the same graph in words: keyboard-reachable, and readable without colour --
  function syncList(built) {
    var list = $('cy-nodes');
    if (!list) { return; }
    list.innerHTML = built.elements.filter(function (e) { return !e.data.source; }).map(function (e) {
      var id = e.data.id, m = built.models[id], meta = m && m.meta;
      var lines = String(e.data.label || '').split('\n');
      // A fold, a cluster and the withheld count read as themselves; a real node reads
      // as its reference, so the list is searchable by the reference somebody has.
      var synthetic = id.indexOf('maya://') !== 0 || id === HIDDEN_ID;
      var facts = [];
      if (synthetic) {
        facts = lines.slice(1).map(function (s) { return s.replace(/^·\s*/, ''); });
        if (!facts.length) { facts = [e.data.kind]; }
      } else {
        facts = [kindOf(id) === 'other' ? e.data.kind : kindOf(id)];
        if (meta && meta.state) { facts.push(meta.state); }
        if (meta && meta.owner) { facts.push('owned by ' + meta.owner); }
        if (built.words[id]) { facts.push(built.words[id]); }
        if (m && m.review) { facts.push(m.review + ' in this review'); }
      }
      return '<li><button type="button" class="btn btn-link btn-sm p-0 mono" data-cy-row="' +
        esc(id) + '">' + esc(synthetic ? lines[0] : shortLabel(id)) + '</button> ' +
        '<span class="small-muted">— ' + esc(facts.join(' · ')) + '</span></li>';
    }).join('');
  }

  function say(built) {
    var g = state.graph;
    var parts = [built.shownCount + ' node(s), ' + built.elements.filter(function (e) {
      return !!e.data.source;
    }).length + ' edge(s)'];
    if (built.removed) { parts.push(built.removed + ' hidden by your filters'); }
    if (g.hidden) { parts.push(g.hidden + ' left out because you may not read them'); }
    if (built.clustered) { parts.push('the far graph is clustered by namespace — click a cluster to expand it'); }
    if (g.meta_complete === false) { parts.push('this graph spans more namespaces than one draw reads, so some nodes carry no detail'); }
    if (status) { status.textContent = parts.join(' · ') + '.'; }
    var legend = $('cy-legend');
    if (legend) {
      var overlay = val('cy-overlay', 'none');
      legend.textContent = LEGENDS[overlay] || 'No overlay: nodes are drawn by kind, the root outlined in crimson.';
    }
  }

  function draw() {
    var built = build();
    state.built = built;
    if (!state.cy) {
      state.cy = window.cytoscape({
        container: el, elements: built.elements, wheelSensitivity: 0.2, selectionType: 'additive',
        layout: { name: 'breadthfirst', directed: true, spacingFactor: 1.15, padding: 20 },
        style: STYLE()
      });
      wire();
    } else {
      state.cy.batch(function () {
        state.cy.elements().remove();
        state.cy.add(built.elements);
      });
      state.cy.layout({ name: 'breadthfirst', directed: true, spacingFactor: 1.15, padding: 20 }).run();
    }
    state.selection = state.selection.filter(function (id) { return state.cy.getElementById(id).length > 0; });
    state.selection.forEach(function (id) { state.cy.getElementById(id).select(); });
    syncList(built);
    syncAuthor(built);
    say(built);
  }

  function wire() {
    var cy = state.cy;
    cy.on('mouseover', 'node', function (ev) { setDetail(nodeDetail(ev.target.id(), state.built)); });
    cy.on('mouseover', 'edge', function (ev) {
      var e = ev.target;
      var text = e.data('type') === 'extends'
        ? extendsDetail({ label: e.data('raw') })
        : 'Edge: ' + e.data('type').replace(/_/g, ' ') + '.';
      setDetail('<h4 class="h6">' + esc(e.data('label')) + '</h4><p class="mb-0 small">' + esc(text) + '</p>');
    });
    cy.on('tap', 'node', function (ev) {
      var id = ev.target.id();
      if (id.indexOf('cluster:') === 0) {
        state.expandedClusters[id.slice('cluster:'.length)] = true;
        draw();
        return;
      }
      if (id.indexOf('chain:') === 0) {
        state.expandedChains[id] = true;
        draw();
        return;
      }
      state.selection = cy.nodes(':selected').map(function (n) { return n.id(); });
      setDetail(nodeDetail(id, state.built));
      syncAuthor(state.built);
    });
    cy.on('dbltap', 'node', function (ev) {
      var id = ev.target.id();
      if (id.indexOf('maya://') === 0 && id !== HIDDEN_ID) { reroot(id); }
    });
    // A canvas inside a hidden tab measures zero: size it when the tab is shown.
    document.querySelectorAll('[data-bs-toggle="tab"]').forEach(function (btn) {
      btn.addEventListener('shown.bs.tab', function () { cy.resize(); cy.fit(undefined, 20); });
    });
  }

  function reroot(id) {
    state.root = id;
    state.expandedChains = {};
    state.expandedClusters = {};
    state.selection = [];
    load();  // which puts the new root in the address bar and in the Draw form
  }

  function fetchJson(url) {
    return fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.json(); });
  }

  function load() {
    if (status) { status.textContent = 'Drawing…'; }
    // The "Draw" form round-trips whatever the canvas is showing, so a new root
    // does not silently reset the direction and depth somebody just chose; and on
    // the canvas's own page the address bar follows, so the view can be sent to
    // somebody else. An object page's URL is left alone: the canvas is a tab there.
    var fd = $('cy-form-direction'), fp = $('cy-form-depth');
    if (fd) { fd.value = state.direction; }
    if (fp) { fp.value = state.depth; }
    if (location.pathname === '/lineage' && window.history && history.replaceState) {
      history.replaceState(null, '', '/lineage?root=' + encodeURIComponent(state.root) +
        '&direction=' + encodeURIComponent(state.direction) +
        '&depth=' + encodeURIComponent(state.depth));
    }
    return fetchJson('/ui/lineage?root=' + encodeURIComponent(state.root) + '&direction=' +
      encodeURIComponent(state.direction) + '&depth=' + encodeURIComponent(state.depth))
      .then(function (g) {
        if (g.error) { if (status) { status.textContent = g.error; } return; }
        state.graph = g;
        state.cost = null;
        fillFilters(g);
        // §16.3: beyond ~300 nodes the canvas switches itself to focus plus context.
        // Turning it off is remembered, because a person who asked for the whole graph
        // once should not have to ask again on every redraw.
        var cluster = $('cy-cluster');
        if (cluster && g.nodes.length > CLUSTER_AT && !state.clusterOff) { cluster.checked = true; }
        if (val('cy-overlay', 'none') === 'cost') { return price(); }
        draw();
      })
      .catch(function (e) { if (status) { status.textContent = 'Could not load lineage: ' + e; } });
  }

  function price() {
    var refs = state.graph.nodes.map(function (n) { return bare(n.id); });
    return fetchJson('/ui/lineage/cost?refs=' + encodeURIComponent(refs.join(',')))
      .then(function (c) { state.cost = c.error ? null : c; draw(); })
      .catch(function () { state.cost = null; draw(); });
  }

  function fillFilters(g) {
    var kinds = {}, spaces = {}, states = {};
    g.nodes.forEach(function (n) {
      kinds[kindOf(n.id)] = true;
      var meta = g.meta ? g.meta[bare(n.id)] : null;
      if (meta) {
        if (meta.namespace) { spaces[meta.namespace] = true; }
        if (meta.state) { states[meta.state] = true; }
      }
    });
    function fill(id, values, anyLabel) {
      var sel = $(id);
      if (!sel) { return; }
      var keep = sel.value;
      sel.innerHTML = '<option value="">' + anyLabel + '</option>' + Object.keys(values).sort()
        .map(function (v) { return '<option value="' + esc(v) + '">' + esc(v) + '</option>'; }).join('');
      if (keep && values[keep]) { sel.value = keep; }
    }
    fill('cy-f-type', kinds, 'any type');
    fill('cy-f-namespace', spaces, 'any namespace');
    fill('cy-f-status', states, 'any status');
  }

  // ---- controls ----------------------------------------------------------------
  ['cy-f-type', 'cy-f-namespace', 'cy-f-status'].forEach(function (id) {
    var e = $(id);
    if (e) { e.addEventListener('change', function () { draw(); }); }
  });
  ['cy-f-pinned', 'cy-collapse', 'cy-cluster'].forEach(function (id) {
    var e = $(id);
    if (e) {
      e.addEventListener('change', function () {
        if (id === 'cy-cluster' && !e.checked) { state.clusterOff = true; }
        if (id === 'cy-collapse' && e.checked) { state.expandedChains = {}; }
        draw();
      });
    }
  });
  var overlaySel = $('cy-overlay');
  if (overlaySel) {
    overlaySel.addEventListener('change', function () {
      if (overlaySel.value === 'cost' && !state.cost) { price(); } else { draw(); }
    });
  }
  var dirSel = $('cy-direction');
  if (dirSel) {
    dirSel.addEventListener('change', function () { state.direction = dirSel.value; load(); });
  }
  var depthSel = $('cy-depth');
  if (depthSel) {
    depthSel.addEventListener('change', function () { state.depth = depthSel.value; load(); });
  }
  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest ? ev.target.closest('[data-cy-reroot]') : null;
    if (btn) { ev.preventDefault(); reroot(btn.getAttribute('data-cy-reroot')); }
  });
  var list = $('cy-nodes');
  if (list) {
    list.addEventListener('mouseover', function (ev) {
      var row = ev.target.closest('[data-cy-row]');
      if (row) { setDetail(nodeDetail(row.getAttribute('data-cy-row'), state.built)); }
    });
    list.addEventListener('focusin', function (ev) {
      var row = ev.target.closest('[data-cy-row]');
      if (row) { setDetail(nodeDetail(row.getAttribute('data-cy-row'), state.built)); }
    });
    list.addEventListener('click', function (ev) {
      var row = ev.target.closest('[data-cy-row]');
      if (!row) { return; }
      var id = row.getAttribute('data-cy-row');
      // A fold or a cluster expands from here too, so expanding never needs the mouse.
      if (id.indexOf('cluster:') === 0) {
        state.expandedClusters[id.slice('cluster:'.length)] = true;
        draw();
        return;
      }
      if (id.indexOf('chain:') === 0) {
        state.expandedChains[id] = true;
        draw();
        return;
      }
      setDetail(nodeDetail(id, state.built));
      var node = state.cy && state.cy.getElementById(id);
      if (node && node.length) {
        node.select();
        state.selection = state.cy.nodes(':selected').map(function (n) { return n.id(); });
        syncAuthor(state.built);
      }
    });
  }
  var opSelect = $('cy-operator');
  if (opSelect) { opSelect.addEventListener('change', function () { syncAuthor(state.built); }); }

  load();
})();
