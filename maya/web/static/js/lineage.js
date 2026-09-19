/*
 * lineage.js — the lineage and algebra canvas (spec §16.3) on vendored Cytoscape.
 * Operator nodes (maya://op/...) are diamonds; edges are styled by type.
 * Click a node to re-root. Data comes from /ui/lineage, a thin proxy over the SDK.
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';
  var el = document.getElementById('cy');
  if (!el || !window.cytoscape) { return; }
  var root = el.getAttribute('data-root');
  var status = document.getElementById('cy-status');
  if (!root) { return; }
  var css = getComputedStyle(document.documentElement);
  function tok(n) { return css.getPropertyValue(n).trim() || '#888'; }

  function label(id) {
    var s = id.replace(/^maya:\/\//, '');
    return s.length > 48 ? '…' + s.slice(-46) : s;
  }
  function shape(kind) {
    return { op: 'diamond', feature: 'round-rectangle', featureset: 'rectangle', model: 'ellipse',
             warrant: 'hexagon', parameters: 'tag', execution: 'triangle' }[kind] || 'round-rectangle';
  }

  var url = '/ui/lineage?root=' + encodeURIComponent(root) + '&direction=' +
    encodeURIComponent(el.getAttribute('data-direction')) + '&depth=' + encodeURIComponent(el.getAttribute('data-depth'));
  fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (g) {
    if (g.error) { status.textContent = g.error; return; }
    var elements = g.nodes.map(function (n) {
      return { data: { id: n.id, label: label(n.id), kind: n.kind, root: n.id === root ? 1 : 0 } };
    }).concat(g.edges.map(function (e, i) {
      return { data: { id: 'e' + i, source: e.source, target: e.target, type: e.type,
                       label: e.type === 'operand_of' ? (e.label || '') : e.type } };
    }));
    status.textContent = g.nodes.length + ' nodes, ' + g.edges.length + ' edges' +
      (g.nodes.length > 300 ? ' — large graph: narrow the depth to focus' : '');
    var cy = window.cytoscape({
      container: el, elements: elements, wheelSensitivity: 0.2,
      layout: { name: 'breadthfirst', directed: true, spacingFactor: 1.15, padding: 20 },
      style: [
        { selector: 'node', style: { 'shape': function (n) { return shape(n.data('kind')); },
          'background-color': tok('--maya-surface'), 'border-color': tok('--maya-indigo'), 'border-width': 2,
          'label': 'data(label)', 'font-size': 10, 'color': tok('--maya-ink'), 'text-wrap': 'wrap',
          'text-max-width': 160, 'text-valign': 'bottom', 'text-margin-y': 4, 'width': 30, 'height': 22 } },
        { selector: 'node[kind = "op"]', style: { 'background-color': tok('--maya-crimson-tint'), 'border-color': tok('--maya-crimson') } },
        { selector: 'node[root = 1]', style: { 'border-color': tok('--maya-crimson'), 'border-width': 4 } },
        { selector: 'edge', style: { 'width': 1.5, 'line-color': tok('--maya-slate'), 'target-arrow-color': tok('--maya-slate'),
          'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'label': 'data(label)', 'font-size': 8,
          'color': tok('--maya-slate'), 'text-rotation': 'autorotate' } },
        { selector: 'edge[type = "extends"]', style: { 'target-arrow-shape': 'triangle', 'target-arrow-fill': 'hollow', 'width': 2 } },
        { selector: 'edge[type = "operand_of"]', style: { 'width': 1 } },
        { selector: 'edge[type = "member_of"]', style: { 'line-style': 'dashed' } },
        { selector: 'edge[type = "composite_member"]', style: { 'line-style': 'double', 'width': 4 } },
        { selector: 'edge[type = "pinned_as"]', style: { 'line-style': 'dotted', 'width': 2 } },
        { selector: 'edge[type = "trained_on"], edge[type = "executed_under"], edge[type = "parameterized_by"]',
          style: { 'width': 3.5, 'line-color': tok('--maya-indigo'), 'target-arrow-color': tok('--maya-indigo') } }
      ]
    });
    cy.on('tap', 'node', function (ev) {
      var id = ev.target.id();
      if (id.indexOf('maya://op/') === 0) { return; }
      location.href = '/lineage?root=' + encodeURIComponent(id) + '&direction=' +
        encodeURIComponent(el.getAttribute('data-direction')) + '&depth=' + encodeURIComponent(el.getAttribute('data-depth'));
    });
  }).catch(function (e) { status.textContent = 'Could not load lineage: ' + e; });
})();
