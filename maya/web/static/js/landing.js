/*
 * landing.js — the three figures on the landing page.
 *
 *   #lpQuestion  (hero)   the question every model has to answer turns into the chain MAYA
 *                         keeps: data, feature, pin, model, warrant, run, sealed by a hash.
 *   #lpClocks             two clocks on every value; a value known too late is refused at the
 *                         gate  k <= e + l  and never reaches the training set.
 *   #lpLedger             the audit log writing itself, each entry chained to the one before.
 *
 * Each figure plays once, when it first comes into view, and then rests on its last frame; a
 * small button replays it. Nothing loops, so the page stays a page. A reader who has asked for
 * less motion gets the last frame, drawn once. Colours come from MAYA's tokens and follow a
 * theme change; the mathematics is set in KaTeX's own faces, which the page already loads.
 *
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';

  var W = 800, DURATION = 9000, REST = 0.94;
  var SANS = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  var MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
  var MATH = 'KaTeX_Main, "Times New Roman", serif';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function clamp(x) { return Math.min(1, Math.max(0, x)); }
  function seg(t, a, b) { return clamp((t - a) / (b - a)); }
  function ease(x) { return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; }
  function lerp(a, b, u) { return a + (b - a) * u; }

  var C = {};
  function readColours() {
    var css = getComputedStyle(document.documentElement);
    function tok(n, d) { return (css.getPropertyValue(n) || d).trim() || d; }
    C = {
      ink: tok('--maya-ink', '#1A1A1A'), slate: tok('--maya-slate', '#6B7480'),
      accent: tok('--maya-crimson', '#A51C30'), tint: tok('--maya-crimson-tint', '#FBEEF0'),
      ok: tok('--maya-ok', '#1E6B3A'), bad: tok('--maya-bad', '#8A1626'),
      line: tok('--maya-border', '#E3DED7'), card: tok('--maya-surface', '#FFFFFF')
    };
  }

  function text(c, s, x, y, font, colour, align) {
    c.font = font; c.fillStyle = colour; c.textAlign = align || 'left'; c.fillText(s, x, y);
  }
  function box(c, x, y, w, h, r) {
    c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
  }
  function line(c, x0, y0, x1, y1) { c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1); c.stroke(); }
  function arrow(c, x, y, colour) {
    c.fillStyle = colour; c.beginPath(); c.moveTo(x, y); c.lineTo(x - 8, y - 4.5); c.lineTo(x - 8, y + 4.5); c.closePath(); c.fill();
  }

  /* -- the question becomes the chain ------------------------------------------------ */
  var DOTS = (function () {
    var pts = [], cx = 400, cy = 76, r = 44, i, th;
    for (i = 0; i < 40; i++) { th = Math.PI + i / 39 * 1.25 * Math.PI; pts.push([cx + r * Math.cos(th), cy + r * Math.sin(th)]); }
    var ex = cx + r * Math.cos(2.25 * Math.PI), ey = cy + r * Math.sin(2.25 * Math.PI);
    for (i = 1; i <= 16; i++) { pts.push([lerp(ex, cx, i / 16), lerp(ey, cy + r * 1.5, i / 16)]); }
    for (i = 0; i < 16; i++) { th = i / 16 * 2 * Math.PI; pts.push([cx + 5 * Math.cos(th), cy + r * 2.1 + 5 * Math.sin(th)]); }
    return pts;
  }());
  var STAGES = ['data', 'feature', 'pin', 'model', 'warrant', 'run'];
  var GLYPHS = ['≡', 'ƒ', '#', 'Σ', '✓', '▸'];
  // the chain figure's own notes, one line under each stage
  var NOTES = ['as it arrived', 'as it stood then', 'readable for ever', 'MAYA evaluates it',
    'or it does not run', 'reported, checked'];

  function question(c, t) {
    var appear = ease(seg(t, 0, 0.16)), morph = ease(seg(t, 0.26, 0.52)), nodes = seg(t, 0.48, 0.58), ny = 150;
    function nx(i) { return 115 + i * 114; }
    DOTS.forEach(function (q, i) {
      var k = Math.floor(i / 12), a = (i % 12) / 12 * 2 * Math.PI;
      var x = lerp(q[0], nx(k) + 13 * Math.cos(a), morph), y = lerp(q[1], ny + 13 * Math.sin(a), morph);
      c.globalAlpha = appear * (1 - nodes * 0.95); c.fillStyle = C.accent; c.beginPath(); c.arc(x, y, 2.3, 0, 7); c.fill();
    });
    for (var k = 0; k < 5; k++) {
      var p = seg(t, 0.58 + k * 0.045, 0.62 + k * 0.045); if (p <= 0) { continue; }
      var x0 = nx(k) + 21, x1 = nx(k + 1) - 21;
      c.globalAlpha = 1; c.strokeStyle = C.accent; c.lineWidth = 2; line(c, x0, ny, lerp(x0, x1, p), ny);
      if (p >= 1) { arrow(c, x1, ny, C.accent); }
    }
    STAGES.forEach(function (name, i) {
      var lit = t >= (i === 0 ? 0.58 : 0.62 + (i - 1) * 0.045);
      c.globalAlpha = nodes; c.fillStyle = lit ? C.tint : C.card; c.strokeStyle = C.accent; c.lineWidth = 1.6;
      c.beginPath(); c.arc(nx(i), ny, 19, 0, 7); c.fill(); c.stroke();
      text(c, GLYPHS[i], nx(i), ny + 5, '600 14px ' + MONO, C.accent, 'center');
      text(c, name, nx(i), ny + 42, '500 13px ' + SANS, C.ink, 'center');
      text(c, NOTES[i], nx(i), ny + 59, '11.5px ' + SANS, C.slate, 'center');
    });
    c.globalAlpha = seg(t, 0.6, 0.7); text(c, 'ŷ = a·x + b', nx(3), ny - 34, 'italic 21px ' + MATH, C.ink, 'center');
    var s = seg(t, 0.84, 0.92);
    c.globalAlpha = s * 0.6; c.strokeStyle = C.accent; c.lineWidth = 1.2; box(c, 230, 232, 340, 32, 6); c.stroke();
    c.globalAlpha = s; text(c, 'sealed · sha256 9f3a 61c0 … 7b2d e21c', W / 2, 254, '500 13px ' + MONO, C.slate, 'center');
  }

  /* -- two clocks -------------------------------------------------------------------- */
  function dial(c, x, y, label, ang) {
    c.strokeStyle = C.line; c.lineWidth = 1.5; c.fillStyle = C.card; c.beginPath(); c.arc(x, y, 50, 0, 7); c.fill(); c.stroke();
    c.strokeStyle = C.slate; c.lineWidth = 1.2;
    for (var i = 0; i < 12; i++) {
      var a = i / 12 * 2 * Math.PI; line(c, x + 42 * Math.cos(a), y + 42 * Math.sin(a), x + 47 * Math.cos(a), y + 47 * Math.sin(a));
    }
    c.strokeStyle = C.accent; c.lineWidth = 2.5; line(c, x, y, x + 34 * Math.cos(ang - Math.PI / 2), y + 34 * Math.sin(ang - Math.PI / 2));
    c.fillStyle = C.accent; c.beginPath(); c.arc(x, y, 3, 0, 7); c.fill();
    text(c, label, x, y + 72, '500 13px ' + SANS, C.ink, 'center');
  }

  function clocks(c, t) {
    var lane = 140, gate = 430, bx = 548, bw = 92, rows = 0;
    c.globalAlpha = 1;
    dial(c, 95, lane, 'event time  e', t * 2 * Math.PI);
    dial(c, 705, lane, 'known at  k', t * 2 * Math.PI - 0.5);
    c.strokeStyle = C.line; c.lineWidth = 1; c.setLineDash([2, 4]); line(c, 160, lane, bx, lane); c.setLineDash([]);
    c.strokeStyle = C.accent; c.lineWidth = 2; c.setLineDash([6, 4]); line(c, gate, 50, gate, 225); c.setLineDash([]);
    text(c, 'k ≤ e + ℓ', gate, 37, 'italic 23px ' + MATH, C.ink, 'center');
    text(c, 'known in time, or refused', gate, 245, '12px ' + SANS, C.slate, 'center');
    box(c, bx, 90, bw, 100, 8); c.fillStyle = C.card; c.fill(); c.strokeStyle = C.ok; c.lineWidth = 1.6; c.stroke();
    text(c, 'training set', bx + bw / 2, 80, '500 12px ' + SANS, C.ok, 'center');
    for (var j = 0; j < 7; j++) {
      var s = j * 0.09, p = seg(t, s, s + 0.36), leak = (j === 2 || j === 5), x, y = lane, a = 1;
      if (p <= 0) { continue; }
      if (!leak) {
        if (p >= 1) { rows++; continue; }
        x = lerp(160, bx + bw / 2, ease(p)); if (x > bx) { a = 1 - (x - bx) / (bw / 2); }
        c.globalAlpha = a; c.fillStyle = C.ok; c.beginPath(); c.arc(x, y, 6, 0, 7); c.fill();
        text(c, 'k = e', x, y + 24, '11px ' + MONO, C.slate, 'center');
      } else {
        x = lerp(160, gate - 10, ease(clamp(p / 0.6)));
        if (p > 0.6) { var d = (p - 0.6) / 0.4; y = lane + d * d * 60; a = 1 - d; }
        c.globalAlpha = a; c.fillStyle = C.bad; c.beginPath(); c.arc(x, y, 6, 0, 7); c.fill();
        if (p > 0.55) { text(c, 'leak · known 3 days late', x - 8, y - 14, '600 11px ' + MONO, C.bad, 'right'); }
        else { text(c, 'k = e + 3d', x, y + 24, '11px ' + MONO, C.slate, 'center'); }
      }
    }
    c.globalAlpha = 1; text(c, 'rows ' + rows, bx + bw / 2, 146, '600 15px ' + MONO, C.ink, 'center');
    c.globalAlpha = seg(t, 0.88, 0.94);
    text(c, '5 rows admitted · 2 refused as leaks', W / 2, 272, '500 12.5px ' + MONO, C.slate, 'center');
  }

  /* -- the ledger -------------------------------------------------------------------- */
  var ENTRIES = [
    [['09:14:02  ', 't'], ['feature  ', 'k'], ['eq/px@v4   ', 'i'], ['12,480 rows, two clocks each', 's']],
    [['09:14:40  ', 't'], ['pin      ', 'k'], ['eq/px#eom/2026-03-31  ', 'i'], ['sealed 4be1…9c07', 's']],
    [['09:15:11  ', 't'], ['model    ', 'k'], ['credit/pd@v3   ', 'i'], ['PD = 1 / (1 + e', 'm'], ['−(β₀ + β₁x)', 'sup'], [')', 'm']],
    [['09:16:05  ', 't'], ['params   ', 'k'], ['β₀ = −2.10  β₁ = 0.84   ', 'i'], ['fitted on 4be1…9c07', 's']],
    [['09:17:30  ', 't'], ['approve  ', 'k'], ['credit/pd@v3   ', 'i'], ['by mgr2, not the author', 'ok']],
    [['09:18:02  ', 't'], ['run      ', 'k'], ['refused   ', 'bad'], ['warrant suspended: null_rate 0.40 > 0.10', 'bad']]
  ];
  var HASHES = ['a1f0', '77c2', '0d9e', '5b31', 'c8e4', 'f203'];
  function style(kind) {
    return {
      t: ['12.5px ' + MONO, C.slate, 0], k: ['600 12.5px ' + MONO, C.accent, 0], i: ['12.5px ' + MONO, C.ink, 0],
      s: ['12.5px ' + MONO, C.slate, 0], m: ['italic 17px ' + MATH, C.ink, 0], sup: ['italic 12px ' + MATH, C.ink, -7],
      ok: ['12.5px ' + MONO, C.ok, 0], bad: ['600 12.5px ' + MONO, C.bad, 0]
    }[kind];
  }

  function ledger(c, t) {
    ENTRIES.forEach(function (parts, i) {
      var s0 = 0.04 + i * 0.135, p = seg(t, s0, s0 + 0.11), y = 40 + i * 40;
      if (t < s0) { return; }
      c.globalAlpha = 1; box(c, 44, y - 15, 58, 22, 4); c.fillStyle = C.tint; c.fill();
      c.strokeStyle = C.accent; c.lineWidth = 1; c.stroke();
      text(c, HASHES[i], 73, y + 1, '500 11.5px ' + MONO, C.accent, 'center');
      if (i > 0) { c.strokeStyle = C.accent; c.lineWidth = 1.4; line(c, 73, y - 33, 73, y - 15); }
      var total = parts.reduce(function (n, q) { return n + q[0].length; }, 0), left = Math.floor(total * p), x = 124;
      parts.forEach(function (q) {
        if (left <= 0) { return; }
        var st = style(q[1]), piece = q[0].slice(0, left); left -= q[0].length;
        c.font = st[0]; c.fillStyle = st[1]; c.textAlign = 'left'; c.fillText(piece, x, y + st[2]);
        x += c.measureText(piece).width;
      });
      if (p < 1) { c.fillStyle = C.accent; c.fillRect(x + 2, y - 11, 7, 14); }
    });
    c.globalAlpha = seg(t, 0.1, 0.2);
    text(c, 'each entry carries the hash of the one before it', W / 2, 282, '12px ' + SANS, C.slate, 'center');
  }

  /* -- the runner -------------------------------------------------------------------- */
  var FIGURES = [
    { id: 'lpQuestion', draw: question, h: 272 },
    { id: 'lpClocks', draw: clocks, h: 285 },
    { id: 'lpLedger', draw: ledger, h: 295 }
  ].map(function (f) {
    f.canvas = document.getElementById(f.id);
    return f;
  }).filter(function (f) { return f.canvas && f.canvas.getContext; });
  if (!FIGURES.length) { return; }

  function size(f) {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    f.canvas.width = W * dpr; f.canvas.height = f.h * dpr;
    f.ctx = f.canvas.getContext('2d'); f.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function paint(f) {
    var c = f.ctx; c.save(); c.clearRect(0, 0, W, f.h); c.textBaseline = 'alphabetic';
    f.draw(c, f.t); c.restore();
  }
  function play(f) {
    if (reduce) { f.t = REST; paint(f); return; }
    var start = null;
    f.playing = true;
    function step(ts) {
      if (start === null) { start = ts; }
      f.t = Math.min(REST, (ts - start) / DURATION);
      paint(f);
      if (f.t < REST) { window.requestAnimationFrame(step); } else { f.playing = false; }
    }
    window.requestAnimationFrame(step);
  }

  readColours();
  FIGURES.forEach(function (f) {
    size(f); f.t = reduce ? REST : 0; f.played = false; paint(f);
    var replay = document.querySelector('[data-replay="' + f.id + '"]');
    if (replay) {
      if (reduce) { replay.hidden = true; }
      replay.addEventListener('click', function () { if (!f.playing) { play(f); } });
    }
  });
  function startWhenSeen(f) {
    if (f.played) { return; }
    f.played = true; play(f);
  }
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) {
          FIGURES.forEach(function (f) { if (f.canvas === e.target) { startWhenSeen(f); } });
        }
      });
    }, { threshold: 0.4 });
    FIGURES.forEach(function (f) { io.observe(f.canvas); });
  } else {
    FIGURES.forEach(startWhenSeen);
  }
  function repaintAll() { readColours(); FIGURES.forEach(function (f) { if (!f.playing) { paint(f); } }); }
  window.addEventListener('resize', function () { FIGURES.forEach(function (f) { size(f); paint(f); }); });
  // The theme can change without a reload, and KaTeX's faces may arrive after the first paint.
  new MutationObserver(repaintAll).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  if (document.fonts && document.fonts.load) {
    Promise.all([document.fonts.load('italic 21px KaTeX_Main'), document.fonts.load('21px KaTeX_Main')])
      .then(repaintAll, function () { /* the serif fallback is fine */ });
  }
}());
