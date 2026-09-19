/*
 * table.js — behaviour for THE table macro (spec §16.7). Every table in MAYA is
 * emitted by templates/_macros/table.html and enhanced here, uniformly:
 *   - pagination: 25 / 50 / 100 / 250 / All, remembered per table (localStorage),
 *     "showing x–y of N";
 *   - search across visible columns, debounced, matches highlighted, with a count
 *     of what the filter removed;
 *   - sort on every sortable column, applied to the WHOLE result set (never just the
 *     visible page); shift-click adds a secondary key; the header shows direction;
 *   - column show/hide, remembered; CSV export of the current view (filter + sort);
 *   - keyboard paging (PageUp/PageDown, Home/End while the table has focus).
 * Client-side paging throughout: MAYA's catalog pages load their full result sets
 * (server-side cursor paging for very large tables is a stated future extension).
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';
  var SIZES = [25, 50, 100, 250, 0];   // 0 = All

  function store(key, value) {
    try {
      if (value === undefined) { return JSON.parse(localStorage.getItem(key) || 'null'); }
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) { return null; }
    return null;
  }

  function cellText(cell) { return (cell.getAttribute('data-sort') || cell.textContent || '').trim(); }

  function compare(a, b) {
    var na = parseFloat(a), nb = parseFloat(b);
    var numeric = /^-?[\d.,e+-]+$/i.test(a) && /^-?[\d.,e+-]+$/i.test(b) && !isNaN(na) && !isNaN(nb);
    if (numeric) { return na - nb; }
    return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
  }

  function escapeRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function MayaTable(wrap) {
    this.wrap = wrap;
    this.table = wrap.querySelector('table');
    this.id = wrap.getAttribute('data-table-id');
    this.key = 'maya.table.' + location.pathname + '.' + this.id;
    this.heads = Array.prototype.slice.call(this.table.tHead.rows[0].cells);
    this.rows = Array.prototype.slice.call(this.table.tBodies[0].rows).map(function (tr, i) {
      return { tr: tr, i: i, cells: Array.prototype.slice.call(tr.cells).map(function (c) {
        c.setAttribute('data-orig', c.innerHTML); return c; }) };
    });
    var saved = store(this.key) || {};
    this.size = SIZES.indexOf(saved.size) >= 0 ? saved.size : 25;
    this.hidden = saved.hidden || [];
    this.sorts = [];
    this.page = 0;
    this.query = '';
    this.el = {
      search: wrap.querySelector('.mt-search'), size: wrap.querySelector('.mt-size'),
      info: wrap.querySelector('.mt-info'), note: wrap.querySelector('.mt-note'),
      prev: wrap.querySelector('.mt-prev'), next: wrap.querySelector('.mt-next'),
      first: wrap.querySelector('.mt-first'), last: wrap.querySelector('.mt-last'),
      cols: wrap.querySelector('.mt-cols'), csv: wrap.querySelector('.mt-csv'),
      empty: wrap.querySelector('.mt-empty'), scroll: wrap.querySelector('.mt-scroll')
    };
    this.bind();
    this.render();
  }

  MayaTable.prototype.bind = function () {
    var self = this, timer = null;
    this.el.size.value = String(this.size);
    this.el.size.addEventListener('change', function () {
      self.size = parseInt(this.value, 10); self.page = 0; self.save(); self.render();
    });
    this.el.search.addEventListener('input', function () {
      var v = this.value;
      clearTimeout(timer);
      timer = setTimeout(function () { self.query = v.trim(); self.page = 0; self.render(); }, 180);
    });
    this.heads.forEach(function (th, idx) {
      if (!th.hasAttribute('data-sortable')) { return; }
      th.setAttribute('tabindex', '0');
      th.addEventListener('click', function (ev) { self.sortBy(idx, ev.shiftKey); });
      th.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); self.sortBy(idx, ev.shiftKey); }
      });
    });
    this.el.prev.addEventListener('click', function () { self.go(self.page - 1); });
    this.el.next.addEventListener('click', function () { self.go(self.page + 1); });
    this.el.first.addEventListener('click', function () { self.go(0); });
    this.el.last.addEventListener('click', function () { self.go(Infinity); });
    this.el.csv.addEventListener('click', function () { self.exportCsv(); });
    this.table.setAttribute('tabindex', '0');
    this.table.addEventListener('keydown', function (ev) {
      var map = { PageDown: self.page + 1, PageUp: self.page - 1, Home: 0, End: Infinity };
      if (ev.target === self.table && ev.key in map) { ev.preventDefault(); self.go(map[ev.key]); }
    });
    this.buildColumnMenu();
  };

  MayaTable.prototype.buildColumnMenu = function () {
    var self = this;
    this.heads.forEach(function (th, idx) {
      var label = document.createElement('label');
      label.className = 'dropdown-item d-flex gap-2 align-items-center';
      var box = document.createElement('input');
      box.type = 'checkbox'; box.className = 'form-check-input';
      box.checked = self.hidden.indexOf(idx) < 0;
      box.addEventListener('change', function () {
        if (this.checked) { self.hidden = self.hidden.filter(function (h) { return h !== idx; }); }
        else { self.hidden.push(idx); }
        self.save(); self.render();
      });
      label.appendChild(box);
      label.appendChild(document.createTextNode(th.getAttribute('data-label') || th.textContent.trim() || '#' + idx));
      self.el.cols.appendChild(label);
    });
  };

  MayaTable.prototype.save = function () { store(this.key, { size: this.size, hidden: this.hidden }); };

  MayaTable.prototype.sortBy = function (idx, add) {
    var existing = this.sorts.filter(function (s) { return s.idx === idx; })[0];
    if (!add) { this.sorts = existing ? [existing] : []; }
    if (existing) { existing.dir = -existing.dir; }
    else { this.sorts.push({ idx: idx, dir: 1 }); }
    this.page = 0;
    this.render();
  };

  MayaTable.prototype.go = function (p) { this.page = p; this.render(); };

  MayaTable.prototype.visible = function (idx) { return this.hidden.indexOf(idx) < 0; };

  MayaTable.prototype.filtered = function () {
    var self = this, q = this.query.toLowerCase();
    var rows = this.rows.filter(function (r) {
      if (!q) { return true; }
      return r.cells.some(function (c, idx) {
        return self.visible(idx) && cellText(c).toLowerCase().indexOf(q) >= 0;
      });
    });
    if (this.sorts.length) {
      var sorts = this.sorts;
      rows = rows.slice().sort(function (a, b) {
        for (var k = 0; k < sorts.length; k++) {
          var s = sorts[k];
          var c = compare(cellText(a.cells[s.idx] || { textContent: '' }),
                          cellText(b.cells[s.idx] || { textContent: '' }));
          if (c !== 0) { return c * s.dir; }
        }
        return a.i - b.i;
      });
    }
    return rows;
  };

  MayaTable.prototype.highlight = function (cell) {
    cell.innerHTML = cell.getAttribute('data-orig');
    if (!this.query || cell.querySelector('a,button,form,input,select')) { return; }
    var re = new RegExp('(' + escapeRe(this.query) + ')', 'ig');
    var walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT, null);
    var nodes = [];
    while (walker.nextNode()) { nodes.push(walker.currentNode); }
    nodes.forEach(function (n) {
      if (!re.test(n.nodeValue)) { return; }
      var span = document.createElement('span');
      span.innerHTML = n.nodeValue.replace(/[&<>]/g, function (ch) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch];
      }).replace(re, '<mark>$1</mark>');
      n.parentNode.replaceChild(span, n);
    });
  };

  MayaTable.prototype.render = function () {
    var self = this, rows = this.filtered(), total = rows.length;
    var size = this.size || total || 1;
    var pages = Math.max(1, Math.ceil(total / size));
    this.page = Math.min(Math.max(0, this.page), pages - 1);
    var start = this.page * size, end = Math.min(total, start + size);
    var body = this.table.tBodies[0];
    while (body.firstChild) { body.removeChild(body.firstChild); }
    rows.slice(start, end).forEach(function (r) {
      r.cells.forEach(function (c, idx) { c.hidden = !self.visible(idx); self.highlight(c); });
      body.appendChild(r.tr);
    });
    this.heads.forEach(function (th, idx) {
      th.hidden = !self.visible(idx);
      var dir = th.querySelector('.mt-dir');
      var s = self.sorts.filter(function (x) { return x.idx === idx; })[0];
      var rank = self.sorts.indexOf(s);
      if (dir) { dir.textContent = s ? (s.dir > 0 ? '▲' : '▼') + (self.sorts.length > 1 ? rank + 1 : '') : ''; }
      th.setAttribute('aria-sort', s ? (s.dir > 0 ? 'ascending' : 'descending') : 'none');
    });
    var removed = this.rows.length - total;
    this.el.info.textContent = total ? ('Showing ' + (start + 1) + '–' + end + ' of ' + total) : 'Showing 0 of 0';
    this.el.note.textContent = this.query ? (removed + ' row' + (removed === 1 ? '' : 's') + ' filtered out by "' + this.query + '"') : '';
    this.el.prev.disabled = this.el.first.disabled = this.page === 0;
    this.el.next.disabled = this.el.last.disabled = this.page >= pages - 1;
    var none = total === 0;
    this.el.empty.hidden = !none;
    this.el.scroll.hidden = none;
    if (none && this.rows.length) {
      this.el.empty.textContent = 'No rows match "' + this.query + '". Clear the search to see all ' + this.rows.length + '.';
    }
  };

  MayaTable.prototype.exportCsv = function () {
    var self = this;
    function q(v) { v = String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
    var cols = this.heads.map(function (_, i) { return i; }).filter(function (i) {
      return self.visible(i) && !self.heads[i].hasAttribute('data-noexport'); });
    var lines = [cols.map(function (i) { return q(self.heads[i].getAttribute('data-label') || self.heads[i].textContent.trim()); }).join(',')];
    this.filtered().forEach(function (r) {
      lines.push(cols.map(function (i) {
        var tmp = document.createElement('div'); tmp.innerHTML = r.cells[i].getAttribute('data-orig');
        return q((r.cells[i].getAttribute('data-sort') || tmp.textContent || '').trim());
      }).join(','));
    });
    var blob = new Blob([lines.join('\n') + '\n'], { type: 'text/csv' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = (this.id || 'table') + '.csv';
    document.body.appendChild(a); a.click(); a.remove();
  };

  function init(root) {
    (root || document).querySelectorAll('[data-maya-table]').forEach(function (w) {
      if (!w.__mayaTable) { w.__mayaTable = new MayaTable(w); }
    });
  }
  window.MayaTables = { init: init };
  document.addEventListener('DOMContentLoaded', function () { init(document); });
})();
