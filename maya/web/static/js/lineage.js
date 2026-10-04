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
 * Data comes from /ui/lineage, one thin proxy over the SDK: the graph, and a row per
 * node carrying the state of the version that node names, the object's last change, a
 * feature's data freshness and what its sealed pins occupy. Every overlay reads that one
 * payload, so none of them is an estimate and none needs a second round trip.
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

  function nsOf(ref) {
    if (String(ref).indexOf('maya://') !== 0) { return ''; }
    var parts = bare(ref).slice(7).split('/');
    // A warrant ref carries its kind before its namespace: warrant/<kind>/<ns>/<name>.
    return (parts[0] === 'warrant' ? parts[2] : parts[1]) || '';
  }

  function pinOf(ref) {
    var i = String(ref).indexOf('#');
    return i > -1 ? String(ref).slice(i + 1) : '';
  }

  // What to write on the face of a node. A ref is a path and a path is not a name: drawn
  // whole, `warrant/train/impairment/ecl_fit_2025h1@v1` is four times the width of the thing
  // it names. The last segment is the name; everything before it is said on the second line
  // or, where it is the same for every node in the graph, not said at all.
  function nodeTitle(ref, meta) {
    var name = (meta && meta.name) || bare(ref).replace(/^maya:\/\//, '').split('/').pop();
    // A parameter set is named by the hash of its own contents. Forty hex characters is not
    // a name anybody reads; the first ten identify it among the handful on one canvas, and
    // the detail panel carries the whole of it for anyone who needs to quote it.
    if (/^[0-9a-f-]{24,}$/.test(name)) { name = name.slice(0, 10) + '…'; }
    if (isPin(ref)) { return name + ' #' + pinOf(ref); }
    var v = versionOf(ref);
    return name + (v ? ' v' + v : '');
  }

  // The second line: what the node is, and where it lives when that is not where the root
  // lives. A pin says so, because a pin and the version it seals share a name and would
  // otherwise be drawn as the same thing twice.
  function nodeKindLine(ref, meta, rootNs) {
    var kind = (meta && meta.kind) || kindOf(ref);
    var line = isPin(ref) ? 'pin of a ' + kind : kind;
    // Only a namespace the server names, and only when it is not the root's: a ref's second
    // segment is a namespace for a feature and a content hash for a parameter set, and
    // repeating that hash under the node says the same nothing twice.
    var ns = meta && meta.namespace;
    return ns && ns !== rootNs ? line + ' · ' + ns : line;
  }

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
      // A feature's freshness is when its data was last known to be true; anything else
      // has no ingest of its own, so it is when the object changed. The word says which,
      // because "7d" means two different things for the two.
      var meta = n.meta;
      if (!meta) { return { ov: 'none', word: 'no date' }; }
      var isData = !!meta.data_freshness;
      var days = ageDays(isData ? meta.data_freshness : meta.updated_at, n.now);
      if (days === null) { return { ov: 'none', word: 'no date' }; }
      var word = days + 'd ' + (isData ? 'of data' : 'since a change');
      if (days < 7) { return { ov: 'ok', word: word }; }
      if (days < 30) { return { ov: 'info', word: word }; }
      if (days < 90) { return { ov: 'warn', word: word }; }
      return { ov: 'bad', word: word };
    },
    approval: function (n) {
      // The state of the version this node names, which the server sends per node. It is
      // not the object's latest state: a graph drawn on v1 of something now at v4 must
      // not borrow v4's approval, and saying "superseded" is not the same as saying
      // whether v1 itself was ever approved.
      var meta = n.meta;
      if (!meta) { return { ov: 'none', word: 'not an object' }; }
      var v = versionOf(n.id);
      var state = meta.state || 'no version';
      var suffix = (v !== null && meta.latest_version && v < meta.latest_version)
        ? ', superseded by v' + meta.latest_version : '';
      if (state === 'approved' || state === 'published') {
        return { ov: suffix ? 'info' : 'ok', word: state + suffix };
      }
      if (state === 'deprecated' || state === 'retired') {
        return { ov: 'none', word: state + suffix };
      }
      return { ov: 'warn', word: state + suffix };
    },
    access: function (n) {
      if (n.id === HIDDEN_ID) { return { ov: 'bad', word: 'withheld' }; }
      if (n.meta) { return { ov: 'ok', word: 'you can read it' }; }
      return { ov: 'info', word: 'internal node' };
    },
    cost: function (n) {
      var bytes = n.meta ? n.meta.pinned_bytes : null;
      if (bytes === null || bytes === undefined) { return { ov: 'none', word: 'not priced' }; }
      if (bytes === 0) { return { ov: 'none', word: 'nothing pinned' }; }
      if (bytes < 1048576) { return { ov: 'ok', word: bytesText(bytes) }; }
      if (bytes < 104857600) { return { ov: 'info', word: bytesText(bytes) }; }
      return { ov: 'warn', word: bytesText(bytes) };
    }
  };

  var LEGENDS = {
    freshness: 'Freshness — for a feature, how old the newest data it knows about is; for anything else, how long since the object changed. Each node says which. Under 7 days, under 30, under 90, older; a node with no date is drawn plain.',
    approval: 'Approval — the state of the version each node names, not of the object’s latest version. A node naming an older version also says what superseded it.',
    access: 'Access — what you can read. Everything drawn, you may read; internal nodes (operators, pins, warrants) carry no read check of their own; the withheld count is what the server left out.',
    cost: 'Cost — what this object’s sealed pins occupy, summed over all of them: nothing, under 1 MB, under 100 MB, more. A model has no pins of its own and is not priced.'
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

  // A node carries its own name, so the shape has to be one text can sit inside. Diamonds,
  // hexagons and triangles cannot hold two lines of it, which is why every kind but the
  // algebra operator is now a rounded box and the kind is carried by colour instead. The
  // operator keeps its diamond: its labels are one short word.
  function shape(kind) {
    return { op: 'diamond' }[kind] || 'round-rectangle';
  }

  // One accent per kind, used for the border and for a wash behind the label. These are the
  // palette's own tokens, so both themes get a colour that was chosen for their ground.
  function accent(kind) {
    return tok({
      feature: '--maya-indigo', featureset: '--maya-heading', model: '--maya-crimson',
      warrant: '--maya-ok', parameters: '--maya-warn', execution: '--maya-slate',
      op: '--maya-crimson-strong'
    }[kind] || '--maya-slate');
  }

  function $(id) { return document.getElementById(id); }
  function val(id, dflt) { var e = $(id); return e ? (e.type === 'checkbox' ? e.checked : e.value) : dflt; }

  var state = {
    graph: null, cy: null, now: Date.now(),
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

  // ---- the model the canvas draws: nodes with their meta and review mark ----------
  function nodeModel(n) {
    var g = state.graph;
    var meta = g.meta ? g.meta[bare(n.id)] : null;
    return { id: n.id, kind: n.kind, meta: meta, now: state.now, review: reviewClass(n.id) };
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
        foldNodes.push({ id: id, depth: inner.length });
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
    var elements = [], words = {}, rootNs = nsOf(state.root);
    Object.keys(shown).forEach(function (id) {
      if (folded[id] || clusterOf[id]) { return; }
      var m = models[id], mark = OVERLAYS[overlay] ? OVERLAYS[overlay](m) : null;
      // Two lines: what the node is called, then what it is. The namespace is only worth a
      // line when it is not the root's own — in a single-namespace graph repeating it on
      // every node doubles the width of the label and says nothing.
      var meta = m.meta ? { name: m.meta.name, namespace: m.meta.namespace, kind: m.kind } : { kind: m.kind };
      var name = nodeTitle(id, meta), under = nodeKindLine(id, meta, rootNs);
      if (id === HIDDEN_ID) { name = g.hidden + ' object(s) you may not read'; under = 'withheld, counted not named'; }
      var word = mark ? mark.word : '';
      words[id] = word;
      var notes = [];
      if (m.review === 'removed') { name = strike(name); notes.push('removed'); }
      else if (m.review) { notes.push(m.review); }
      if (word) { notes.push(word); }
      var label = name + '\n' + [under].concat(notes).filter(Boolean).join(' · ');
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
          label: 'inheritance chain\n' + c.depth + ' version(s) folded'
        }
      });
    });
    Object.keys(clusters).forEach(function (id) {
      elements.push({
        data: {
          id: id, kind: 'cluster', root: 0, ov: '', review: '',
          label: 'namespace ' + id.slice('cluster:'.length) + '\n' + clusters[id] + ' node(s), click to expand'
        }
      });
    });
    var drawn = {};
    elements.forEach(function (e) { drawn[e.data.id] = true; });
    var seen = {}, named = {}, repeats = 0;
    g.edges.forEach(function (e, i) {
      if (!shown[e.source] || !shown[e.target]) { return; }
      var s = place(e.source), t = place(e.target);
      if (s === t || !drawn[s] || !drawn[t]) { return; }
      var key = s + '|' + t + '|' + e.type;
      if (seen[key]) { return; }
      seen[key] = true;
      // A fan of five edges that all say `parameterized_by` writes that word five times
      // across the same patch of canvas and none of the five stays readable. The name is
      // written once per source and relationship; the repeats are drawn, their name is not,
      // and the status line below the canvas says that is what happened.
      var fan = s + '|' + e.type;
      var repeat = !!named[fan];
      named[fan] = (named[fan] || 0) + 1;
      if (repeat) { repeats += 1; }
      elements.push({
        data: {
          id: 'e' + i, source: s, target: t, type: e.type, raw: e.label || '',
          label: repeat ? '' : edgeLabel(e), name: edgeLabel(e)
        }
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
      shownCount: Object.keys(shown).length, clustered: Object.keys(clusters).length > 0,
      unnamedEdges: repeats
    };
  }

  var STYLE = function () {
    return [
      // A node is a box with its own name written inside it, sized to the text it holds.
      // Everything else here follows from that: no floating labels to collide, no zoom
      // needed to read one, and the graph is as wide as its names actually are.
      { selector: 'node', style: {
        'shape': function (n) { return shape(n.data('kind')); },
        'background-color': function (n) { return accent(n.data('kind')); },
        'background-opacity': 0.13,
        'border-color': function (n) { return accent(n.data('kind')); }, 'border-width': 1.5,
        'label': 'data(label)', 'font-size': 11, 'color': tok('--maya-ink'),
        'text-wrap': 'wrap', 'text-max-width': 148,
        'text-valign': 'center', 'text-halign': 'center', 'line-height': 1.4,
        'width': 'label', 'height': 'label', 'padding': 11 } },
      { selector: 'node[kind = "op"]', style: { 'padding': 26, 'font-size': 10 } },
      { selector: 'node[kind = "cluster"], node[kind = "chain"]', style: { 'border-style': 'dashed', 'background-opacity': 0.07 } },
      { selector: 'node[ghost = 1]', style: { 'border-style': 'dashed', 'background-opacity': 0.06 } },
      { selector: 'node[root = 1]', style: { 'border-color': tok('--maya-crimson'), 'border-width': 3 } },
      // An overlay repaints the wash, not the label's ground: the word inside the node has
      // to stay readable, so the colour is a tint and the border carries the full value.
      { selector: 'node[ov = "ok"]', style: { 'background-color': tok('--maya-ok'), 'background-opacity': 0.22, 'border-color': tok('--maya-ok') } },
      { selector: 'node[ov = "warn"]', style: { 'background-color': tok('--maya-warn'), 'background-opacity': 0.22, 'border-color': tok('--maya-warn') } },
      { selector: 'node[ov = "bad"]', style: { 'background-color': tok('--maya-bad'), 'background-opacity': 0.22, 'border-color': tok('--maya-bad') } },
      { selector: 'node[ov = "info"]', style: { 'background-color': tok('--maya-indigo'), 'background-opacity': 0.22, 'border-color': tok('--maya-indigo') } },
      { selector: 'node[ov = "none"]', style: { 'background-color': tok('--maya-slate'), 'background-opacity': 0.08, 'border-color': tok('--maya-slate') } },
      { selector: 'node[review = "added"]', style: { 'border-color': tok('--maya-ok'), 'border-width': 3 } },
      { selector: 'node[review = "changed"]', style: { 'border-color': tok('--maya-warn'), 'border-width': 3 } },
      { selector: 'node[review = "removed"]', style: { 'border-color': tok('--maya-slate'), 'border-style': 'dotted', 'border-width': 3 } },
      { selector: 'node:selected', style: { 'border-color': tok('--maya-crimson-strong'), 'border-width': 3.5 } },
      { selector: 'edge', style: {
        'width': 1.5, 'line-color': tok('--maya-slate'), 'target-arrow-color': tok('--maya-slate'),
        'target-arrow-shape': 'triangle', 'arrow-scale': 0.8,
        'curve-style': 'bezier', 'label': 'data(label)', 'font-size': 9,
        'text-background-color': tok('--maya-surface'), 'text-background-opacity': 0.9,
        'text-background-padding': 2, 'text-background-shape': 'roundrectangle',
        'color': tok('--maya-slate') } },
      { selector: 'edge[type = "extends"]', style: { 'target-arrow-shape': 'triangle', 'target-arrow-fill': 'hollow', 'width': 2 } },
      { selector: 'edge[type = "operand_of"]', style: { 'width': 1 } },
      { selector: 'edge[type = "member_of"]', style: { 'line-style': 'dashed' } },
      { selector: 'edge[type = "composite_member"]', style: { 'line-style': 'double', 'width': 4 } },
      { selector: 'edge[type = "pinned_as"]', style: { 'line-style': 'dotted', 'width': 2 } },
      { selector: 'edge[type = "withheld"]', style: { 'line-style': 'dotted', 'target-arrow-shape': 'none' } },
      { selector: 'edge[type = "version_of"], edge[type = "pin_of"]', style: { 'line-style': 'dashed', 'width': 1, 'target-arrow-shape': 'none' } },
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
      ['This version', meta.version ? 'v' + esc(meta.version) + ' · ' + esc(meta.state) : ''],
      ['Latest', meta.latest_version ? 'v' + esc(meta.latest_version) + ' · ' + esc(meta.latest_state) : ''],
      ['Last change', esc(meta.updated_at || '').slice(0, 19).replace('T', ' ')],
      ['Data known to', esc(meta.data_freshness || '').slice(0, 19).replace('T', ' ')],
      ['Pinned', meta.pinned_bytes === null || meta.pinned_bytes === undefined
        ? '' : esc(bytesText(meta.pinned_bytes))],
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
    if (built.unnamedEdges) {
      parts.push(built.unnamedEdges + ' edge(s) repeat a relationship already named from the same node, so only the first of each carries its name');
    }
    if (built.clustered) { parts.push('the far graph is clustered by namespace — click a cluster to expand it'); }
    if (g.meta_complete === false) { parts.push('this graph holds more objects than one draw describes, so some nodes carry no detail'); }
    if (status) { status.textContent = parts.join(' · ') + '.'; }
    var legend = $('cy-legend');
    if (legend) {
      var overlay = val('cy-overlay', 'none');
      legend.textContent = LEGENDS[overlay] || 'No overlay: each node is coloured by kind — features indigo, feature sets rose, models crimson, warrants green, parameter sets amber, executions slate — and the root is outlined in crimson.';
    }
  }

  // ---- the graph, in words ---------------------------------------------------------------
  // A drawing is not an explanation. Somebody looking at a lineage graph for the first time
  // can see that thirteen boxes are joined by arrows and still not know what the page is
  // telling them, and the arrows carry the part that matters: which way a thing was used.
  // So the canvas also writes out what it drew. Every sentence below is generated from the
  // same payload the drawing uses, so the two cannot disagree -- a commentary maintained
  // separately from the picture would drift from it, which is the failure this platform is
  // about.
  //
  // MAYA's edges all run the same way: from the thing that was used to the thing that used
  // it. Each relation therefore reads differently depending on which end the page's object
  // sits at, and both readings are spelled out rather than left to the arrowhead.
  var RELATIONS = {
    trained_on: {
      into: function (n) { return 'was trained on ' + n; },
      outof: function (n) { return 'was used to train ' + n; }
    },
    composite_member: {
      into: function (n) { return 'combines ' + n; },
      outof: function (n) { return 'is a member of the composite ' + n; }
    },
    parameterized_by: {
      into: function (n) { return 'holds the parameters produced under ' + n; },
      outof: function (n) { return 'produced ' + n; }
    },
    executed_under: {
      into: function (n) { return 'licenses the model fitted under ' + n; },
      outof: function (n) { return 'is what ' + n + ' licenses to run'; }
    },
    member_of: {
      into: function (n) { return 'is assembled from ' + n; },
      outof: function (n) { return 'is a member of ' + n; }
    },
    pinned_as: {
      into: function (n) { return 'seals what ' + n + ' held'; },
      outof: function (n) { return 'is sealed by ' + n; }
    },
    extends: {
      into: function (n) { return 'inherits from ' + n; },
      outof: function (n) { return 'is inherited by ' + n; }
    },
    derived_from: {
      into: function (n) { return 'is computed by ' + n; },
      outof: function (n) { return 'feeds the computation of ' + n; }
    },
    operand_of: {
      into: function (n) { return 'takes ' + n + ' as operands'; },
      outof: function (n) { return 'is an operand of ' + n; }
    },
    version_of: {
      into: function (n) { return 'has the version ' + n; },
      outof: function (n) { return 'is a version of ' + n; }
    },
    pin_of: {
      into: function (n) { return 'has the pin ' + n; },
      outof: function (n) { return 'is a pin of ' + n; }
    },
    withheld: {
      into: function (n) { return 'has ' + n + ' you may not read'; },
      outof: function (n) { return 'is used by ' + n + ' you may not read'; }
    }
  };

  // What each kind of arrow asserts. Only the kinds actually drawn are explained, because a
  // legend listing nine relations when the picture shows two is a legend nobody reads.
  var EDGE_MEANING = {
    trained_on: 'a warrant was trained on that model or that data',
    composite_member: 'that model is a member of this composite',
    parameterized_by: 'a warrant produced that set of parameters',
    executed_under: 'the fitted model is licensed to run by that execution warrant',
    member_of: 'that feature is one of the feature set\u2019s members',
    pinned_as: 'that pin seals what the version held',
    extends: 'the child inherits the parent\u2019s definition and stores only its overrides',
    derived_from: 'the feature is computed by that algebra operation',
    operand_of: 'that feature is an operand of the operation',
    composite_member_alias: 'that model is a member of this composite',
    version_of: 'that version belongs to the object you asked about (lineage is recorded between versions and pins)',
    pin_of: 'that pin belongs to the object you asked about',
    withheld: 'something is there that you may not read'
  };

  function arrowGlossary(g, built) {
    var seen = {};
    g.edges.forEach(function (e) {
      if (built.models[e.source] || built.models[e.target]) { seen[e.type] = true; }
    });
    var kinds = Object.keys(seen).filter(function (t) { return EDGE_MEANING[t]; });
    if (!kinds.length) { return ''; }
    return '<p class="mb-0 small-muted mt-1">Every arrow runs from the thing that was used ' +
      'to the thing that used it. Here: ' +
      kinds.map(function (t) {
        return '<code>' + esc(t) + '</code> \u2014 ' + esc(EDGE_MEANING[t]);
      }).join('; ') + '.</p>';
  }

  function nameOf(id, models) {
    var m = models[id] || {};
    var meta = m.meta ? { name: m.meta.name, namespace: m.meta.namespace, kind: m.kind } : { kind: m.kind };
    return nodeTitle(id, meta);
  }

  // "a, b and c", and beyond three a count, because a sentence naming eleven parameter sets
  // is not a sentence anybody finishes.
  function listOf(names) {
    if (names.length === 1) { return names[0]; }
    if (names.length === 2) { return names[0] + ' and ' + names[1]; }
    if (names.length <= 4) { return names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1]; }
    return names.slice(0, 3).join(', ') + ' and ' + (names.length - 3) + ' more';
  }

  function narrate(built) {
    var host = $('cy-story');
    if (!host) { return; }
    var g = state.graph, models = built.models, root = state.root;
    if (!g || !models[root]) { host.innerHTML = ''; return; }

    var me = models[root], meta = me.meta || {};
    var kind = me.kind || kindOf(root);
    var opening = '<strong>' + esc(nameOf(root, models)) + '</strong> is ' +
      (/^[aeiou]/.test(kind) ? 'an ' : 'a ') + esc(kind) +
      (meta.namespace ? ' in <code>' + esc(meta.namespace) + '</code>' : '') +
      (meta.state ? ', ' + esc(meta.state) : '') +
      (meta.owner ? ', owned by ' + esc(meta.owner) : '') + '.';

    // Only the root's own edges: the sentences describe its neighbourhood, and the drawing
    // carries the rest. A commentary that walked the whole graph would be a second drawing.
    var groups = {};
    g.edges.forEach(function (e) {
      var here = e.source === root ? 'outof' : (e.target === root ? 'into' : null);
      if (!here) { return; }
      var other = here === 'outof' ? e.target : e.source;
      if (!models[other] && other !== HIDDEN_ID) { return; }
      var key = e.type + '|' + here;
      (groups[key] = groups[key] || []).push(other === HIDDEN_ID ? 'objects' : nameOf(other, models));
    });

    var clauses = [];
    Object.keys(groups).forEach(function (key) {
      var parts = key.split('|'), rel = RELATIONS[parts[0]];
      var names = groups[key].filter(function (n, i, a) { return a.indexOf(n) === i; });
      var phrase = rel
        ? rel[parts[1]](listOf(names))
        : parts[0].replace(/_/g, ' ') + ' ' + listOf(names);
      clauses.push(phrase);
    });

    var body = '';
    if (clauses.length) {
      body = ' It ' + clauses.join('; it ') + '.';
    } else {
      body = ' Nothing in this view is joined to it: it stands alone at the depth and ' +
        'direction you are looking at.';
    }

    // What the reader is looking at, as distinct from what exists. A commentary that did not
    // say this would be read as a complete account of the object's lineage, which at depth
    // three it is not.
    var shown = built.shownCount || 0;
    var scope = ' You are seeing ' + shown + ' object(s), ' + esc(state.direction) +
      ' to a depth of ' + esc(String(state.depth)) + '.';
    if (g.hidden) {
      scope += ' ' + g.hidden + ' more are withheld because you may not read them; they are ' +
        'counted and not named.';
    }
    host.innerHTML = '<p class="mb-0">' + opening + body + '</p>' +
      arrowGlossary(g, built) +
      '<p class="mb-0 small-muted mt-1">' + scope + '</p>';
  }

  // ---- arrangement ---------------------------------------------------------------------
  // No arrangement is right for every graph. A chain of eight reads best left to right; a
  // hub with twenty parameter sets reads best radially; a graph whose edges cross whatever
  // you do is sometimes untangled by letting it settle under its own forces. So the choice
  // belongs to whoever is looking at it, and the canvas keeps it rather than asking twice.
  //
  // Every layout below reserves room for the labels rather than for the shapes alone:
  // without nodeDimensionsIncludeLabels the ranks pack at shape width, and each rank's text
  // collides with its neighbour's.
  var LAYOUTS = {
    layered: {
      label: 'Layered, top down',
      options: function () {
        return {
          name: 'breadthfirst', directed: true, spacingFactor: 1.6, padding: 24,
          nodeDimensionsIncludeLabels: true, avoidOverlap: true, grid: false
        };
      }
    },
    'layered-lr': {
      label: 'Layered, left to right',
      // Cytoscape's breadthfirst only runs downward, so this is that layout transposed
      // afterwards. Doing it by swapping the coordinates keeps one implementation of the
      // ranking and cannot disagree with the downward one about which rank a node is in.
      options: function () {
        return {
          name: 'breadthfirst', directed: true, spacingFactor: 1.5, padding: 24,
          nodeDimensionsIncludeLabels: true, avoidOverlap: true, grid: false,
          transpose: true
        };
      }
    },
    organic: {
      label: 'Organic',
      options: function () {
        return {
          name: 'cose', padding: 24, nodeDimensionsIncludeLabels: true, animate: false,
          nodeRepulsion: 12000, idealEdgeLength: 120, nestingFactor: 1.1, gravity: 0.6,
          numIter: 1200, randomize: false
        };
      }
    },
    radial: {
      label: 'Radial',
      // Rings are hops from the root, so the picture says how far each thing is from the
      // object the page is about. Keying the rings on anything else -- a node's degree, say
      // -- produces a drawing that looks radial and means nothing, which is worse than a
      // layout that is plainly the wrong shape.
      options: function () {
        return {
          name: 'concentric', padding: 24, nodeDimensionsIncludeLabels: true,
          minNodeSpacing: 55, avoidOverlap: true, spacingFactor: 1.1,
          concentric: function (n) { return 100 - (n.data('hops') || 0); },
          levelWidth: function () { return 1; }
        };
      }
    },
    grid: {
      label: 'Grid',
      options: function () {
        return {
          name: 'grid', padding: 24, nodeDimensionsIncludeLabels: true, avoidOverlap: true,
          condense: false
        };
      }
    }
  };

  function chosenLayout() {
    var pick = $('cy-layout');
    var name = (pick && pick.value) || state.layout || 'layered';
    return LAYOUTS[name] ? name : 'layered';
  }

  // A per-viewer convenience, so it is browser storage and nothing depends on it: a reader
  // who prefers the left-to-right arrangement should not have to say so on every page.
  function rememberLayout(name) {
    try { window.localStorage.setItem('maya.lineage.layout', name); } catch (e) { /* private window */ }
  }

  function recalledLayout() {
    try { return window.localStorage.getItem('maya.lineage.layout') || ''; } catch (e) { return ''; }
  }

  function layoutOptions() {
    return LAYOUTS[chosenLayout()].options();
  }

  // Run the chosen arrangement over whatever is drawn, and fit afterwards. `transpose` is
  // handled here because cytoscape has no left-to-right breadthfirst: the layout is run,
  // then every node's coordinates are swapped, which turns the ranks through a right angle
  // without a second ranking implementation to keep in step with the first.
  // How many hops each node is from the root, following edges in either direction. The
  // radial layout needs it, and it is cheap enough to compute on every arrangement rather
  // than cache and risk serving a stale answer after a redraw.
  function markHops() {
    var cy = state.cy;
    var root = cy.getElementById(state.root);
    cy.nodes().forEach(function (n) { n.data('hops', 99); });
    if (!root || root.length === 0) { return; }
    cy.elements().bfs({
      roots: root,
      visit: function (v, e, u, i, depth) { v.data('hops', depth); },
      directed: false
    });
  }

  function arrange(fitAfter) {
    if (!state.cy) { return; }
    if (chosenLayout() === 'radial') { markHops(); }
    var opts = layoutOptions();
    var transpose = opts.transpose;
    delete opts.transpose;
    var run = state.cy.layout(opts);
    run.promiseOn('layoutstop').then(function () {
      if (transpose) {
        // Swapping the axes also swaps the two spacings, and they are not interchangeable:
        // the gap between siblings was sized for a node 180px wide and now separates nodes
        // 44px tall, while the gap between ranks was sized for the height and now has to
        // clear the width. Without correcting for that the graph comes out four times
        // taller than it is wide and fits only by zooming out past legibility.
        state.cy.batch(function () {
          state.cy.nodes().forEach(function (n) {
            var p = n.position();
            n.position({ x: p.y * 1.3, y: p.x * 0.42 });
          });
        });
      }
      if (fitAfter !== false) { fitNicely(); }
    });
    run.run();
  }

  // Fit the graph, then hold the zoom somewhere a person can read. `fit` on its own will
  // magnify three nodes until their labels are the size of headings, which is what made this
  // canvas unreadable on a small estate.
  function fitNicely() {
    if (!state.cy) { return; }
    state.cy.fit(undefined, 28);
    if (state.cy.zoom() > 1) { state.cy.zoom({ level: 1, renderedPosition: centreOf() }); }
  }

  function centreOf() {
    var box = el.getBoundingClientRect();
    return { x: box.width / 2, y: box.height / 2 };
  }

  function draw() {
    var built = build();
    state.built = built;
    if (!state.cy) {
      primeLayoutChoice();
      state.cy = window.cytoscape({
        container: el, elements: built.elements, wheelSensitivity: 0.2, selectionType: 'additive',
        // A small graph must not be magnified to fill the canvas: cytoscape fits by zooming,
        // and at 30px nodes that meant a zoom near 3, which drew a 10px label at 30px and
        // turned six of them into one illegible line. Nodes are now sized to be read at 1:1
        // and the zoom is capped just above it.
        minZoom: 0.2, maxZoom: 1.6,
        // Laid out by `arrange` below rather than here, so that the chosen arrangement --
        // including the transposed one, which cytoscape cannot express as options -- runs
        // through one path on the first draw and on every redraw.
        layout: { name: 'preset' }, style: STYLE()
      });
      wire();
      wireControls();
    } else {
      state.cy.batch(function () {
        state.cy.elements().remove();
        state.cy.add(built.elements);
      });
    }
    arrange(true);
    state.selection = state.selection.filter(function (id) { return state.cy.getElementById(id).length > 0; });
    state.selection.forEach(function (id) { state.cy.getElementById(id).select(); });
    syncList(built);
    syncAuthor(built);
    say(built);
    narrate(built);
  }

  // The map controls. Zoom keeps the centre of the canvas fixed rather than the origin,
  // because a control that zooms towards a corner feels broken however correct it is.
  // The recalled preference has to be in place before the first arrangement runs, or the
  // canvas lays out twice and the reader watches it jump.
  function primeLayoutChoice() {
    var pick = $('cy-layout');
    var recalled = recalledLayout();
    if (pick && recalled && LAYOUTS[recalled]) { pick.value = recalled; }
    state.layout = pick ? pick.value : (LAYOUTS[recalled] ? recalled : 'layered');
  }

  function wireControls() {
    var pick = $('cy-layout');
    if (pick) {
      pick.addEventListener('change', function () {
        state.layout = pick.value;
        rememberLayout(pick.value);
        arrange(true);
      });
    }
    var on = function (id, fn) {
      var el = $(id);
      if (el) { el.addEventListener('click', function (ev) { ev.preventDefault(); fn(); }); }
    };
    on('cy-relayout', function () { arrange(true); });
    on('cy-fit', function () { fitNicely(); });
    on('cy-zoom-in', function () { step(1.25); });
    on('cy-zoom-out', function () { step(0.8); });
  }

  function step(by) {
    if (!state.cy) { return; }
    state.cy.zoom({ level: state.cy.zoom() * by, renderedPosition: centreOf() });
  }

  // A few facts at the pointer. The detail panel holds everything; this holds the handful
  // that decide whether the reader wants the rest, and it follows the pointer so that they
  // never have to look away from the node they are asking about.
  function tipFor(id) {
    var m = (state.built.models || {})[id];
    if (!m) { return id === HIDDEN_ID ? 'Objects you may not read, counted and not named.' : ''; }
    var meta = m.meta || {}, bits = [];
    var head = nodeTitle(id, { name: meta.name, namespace: meta.namespace, kind: m.kind });
    bits.push(nodeKindLine(id, { kind: m.kind, namespace: meta.namespace }, nsOf(state.root)));
    if (meta.state) { bits.push(meta.state); }
    if (meta.owner) { bits.push('owned by ' + meta.owner); }
    if (meta.updated_at) { bits.push('changed ' + String(meta.updated_at).slice(0, 10)); }
    if (meta.data_freshness) { bits.push('data to ' + String(meta.data_freshness).slice(0, 10)); }
    if (meta.bytes !== undefined && meta.bytes !== null) { bits.push(bytesText(meta.bytes)); }
    var foot = id === state.root
      ? 'The object this page is about.'
      : 'Double-click to open it.';
    return '<strong>' + esc(head) + '</strong><br>' + esc(bits.join(' \u00b7 ')) +
      '<br><span class="cy-tip-foot">' + foot + '</span>';
  }

  function showTip(ev) {
    var tip = $('cy-tip');
    if (!tip) { return; }
    var html = tipFor(ev.target.id());
    if (!html) { hideTip(); return; }
    tip.innerHTML = html;
    tip.hidden = false;
    var box = el.getBoundingClientRect(), p = ev.renderedPosition || ev.position;
    // Kept inside the canvas: a tooltip that leaves the drawing to the right is a tooltip
    // somebody reads half of.
    var x = Math.min(p.x + 16, box.width - tip.offsetWidth - 8);
    var y = Math.min(p.y + 16, box.height - tip.offsetHeight - 8);
    tip.style.left = Math.max(8, x) + 'px';
    tip.style.top = Math.max(8, y) + 'px';
  }

  function hideTip() {
    var tip = $('cy-tip');
    if (tip) { tip.hidden = true; }
  }

  function wire() {
    var cy = state.cy;
    cy.on('mouseover', 'node', function (ev) {
      setDetail(nodeDetail(ev.target.id(), state.built));
      showTip(ev);
    });
    cy.on('mousemove', 'node', showTip);
    cy.on('mouseout', 'node', hideTip);
    cy.on('pan zoom drag', hideTip);
    cy.on('mouseover', 'edge', function (ev) {
      var e = ev.target;
      var text = e.data('type') === 'extends'
        ? extendsDetail({ label: e.data('raw') })
        : 'Edge: ' + e.data('type').replace(/_/g, ' ') + '.';
      setDetail('<h4 class="h6">' + esc(e.data('name') || e.data('label')) + '</h4><p class="mb-0 small">' + esc(text) + '</p>');
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
    // Double-click opens the object. Re-rooting stays on the detail panel's own button:
    // between the two, opening is what somebody reading a graph wants far more often, and
    // a graph whose nodes cannot be followed is a picture of a catalogue rather than a way
    // into one.
    cy.on('dbltap', 'node', function (ev) {
      var id = ev.target.id();
      if (id === HIDDEN_ID) { return; }
      var m = state.built.models[id] || {};
      var url = m.meta && m.meta.url;
      if (url) { window.location.href = url; return; }
      if (id.indexOf('maya://') === 0) { reroot(id); }
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
        fillFilters(g);
        // §16.3: beyond ~300 nodes the canvas switches itself to focus plus context.
        // Turning it off is remembered, because a person who asked for the whole graph
        // once should not have to ask again on every redraw.
        var cluster = $('cy-cluster');
        if (cluster && g.nodes.length > CLUSTER_AT && !state.clusterOff) { cluster.checked = true; }
        draw();
      })
      .catch(function (e) { if (status) { status.textContent = 'Could not load lineage: ' + e; } });
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
    // Every overlay reads the payload already in hand, so switching one on is a redraw
    // rather than a fetch: no spinner, and no overlay that is a round trip behind.
    overlaySel.addEventListener('change', draw);
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
