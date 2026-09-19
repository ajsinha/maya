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
 *
 * Two modes. Client mode (the default) holds every row and does all of that here.
 * Server mode (the macro was given `page`, so the wrap carries data-source) holds
 * one page: paging follows opaque cursors from /ui/table/<name>, search and sort
 * run on the server over the whole set, rows arrive as HTML rendered by the same
 * macro as page one, and CSV export walks every page of the current view. "All"
 * is not offered in server mode; "last page" walks forward to the end.
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';
  var SIZES = [25, 50, 100, 250, 0];   // 0 = All (client mode only)
  var SERVER_SIZES = [25, 50, 100, 250];
  var EXPORT_PAGE = 1000;

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

  function wrapRow(tr, i) {
    return { tr: tr, i: i, cells: Array.prototype.slice.call(tr.cells).map(function (c) {
      c.setAttribute('data-orig', c.innerHTML); return c; }) };
  }

  function rowFromHtml(html, i) {
    var body = document.createElement('tbody');
    body.innerHTML = '<tr>' + html + '</tr>';
    return wrapRow(body.rows[0], i);
  }

  function MayaTable(wrap) {
    this.wrap = wrap;
    this.table = wrap.querySelector('table');
    this.id = wrap.getAttribute('data-table-id');
    this.key = 'maya.table.' + location.pathname + '.' + this.id;
    this.heads = Array.prototype.slice.call(this.table.tHead.rows[0].cells);
    this.rows = Array.prototype.slice.call(this.table.tBodies[0].rows).map(wrapRow);
    this.source = wrap.getAttribute('data-source');
    var saved = store(this.key) || {};
    var sizes = this.source ? SERVER_SIZES : SIZES;
    this.size = sizes.indexOf(saved.size) >= 0 ? saved.size : 25;
    this.hidden = saved.hidden || [];
    this.sorts = [];
    this.page = 0;
    this.query = '';
    if (this.source) {
      this.serverSort = wrap.getAttribute('data-sort') || '';
      this.cursors = [null];                                   // cursors[p] fetches page p
      this.next = wrap.getAttribute('data-next-cursor') || null;
      var t = wrap.getAttribute('data-total');
      this.total = t === '' || t === null ? null : parseInt(t, 10);
      this.firstSize = parseInt(wrap.getAttribute('data-page-size') || '25', 10);
    }
    this.el = {
      search: wrap.querySelector('.mt-search'), size: wrap.querySelector('.mt-size'),
      info: wrap.querySelector('.mt-info'), note: wrap.querySelector('.mt-note'),
      prev: wrap.querySelector('.mt-prev'), next: wrap.querySelector('.mt-next'),
      first: wrap.querySelector('.mt-first'), last: wrap.querySelector('.mt-last'),
      cols: wrap.querySelector('.mt-cols'), csv: wrap.querySelector('.mt-csv'),
      empty: wrap.querySelector('.mt-empty'), scroll: wrap.querySelector('.mt-scroll')
    };
    this.bind();
    if (this.source && this.size !== this.firstSize) { this.fetch(0); } else { this.render(); }
  }

  MayaTable.prototype.bind = function () {
    var self = this, timer = null;
    this.el.size.value = String(this.size);
    this.el.size.addEventListener('change', function () {
      self.size = parseInt(this.value, 10); self.page = 0; self.save();
      if (self.source) { self.restart(); } else { self.render(); }
    });
    this.el.search.addEventListener('input', function () {
      var v = this.value;
      clearTimeout(timer);
      timer = setTimeout(function () {
        self.query = v.trim(); self.page = 0;
        if (self.source) { self.restart(); } else { self.render(); }
      }, self.source ? 300 : 180);
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
    if (this.source) {                          // one server key; direction toggles
      var key = this.heads[idx].getAttribute('data-sort-key');
      this.serverSort = this.serverSort === key ? '-' + key : key;
      this.restart();
      return;
    }
    var existing = this.sorts.filter(function (s) { return s.idx === idx; })[0];
    if (!add) { this.sorts = existing ? [existing] : []; }
    if (existing) { existing.dir = -existing.dir; }
    else { this.sorts.push({ idx: idx, dir: 1 }); }
    this.page = 0;
    this.render();
  };

  MayaTable.prototype.go = function (p) {
    if (!this.source) { this.page = p; this.render(); return; }
    if (p === Infinity) { this.walkToEnd(); return; }
    if (p < 0 || p === this.page) { return; }
    if (p === this.page + 1) {
      if (!this.next) { return; }
      this.cursors[p] = this.next;
    }
    if (p > this.page + 1 || this.cursors[p] === undefined) { return; }
    this.fetch(p);
  };

  MayaTable.prototype.visible = function (idx) { return this.hidden.indexOf(idx) < 0; };

  // -- server mode ------------------------------------------------------------------------
  MayaTable.prototype.url = function (cursor, size, withTotal) {
    var u = new URL(this.source, location.origin);
    u.searchParams.set('page_size', String(size));
    if (this.serverSort) { u.searchParams.set('sort', this.serverSort); }
    if (cursor) { u.searchParams.set('cursor', cursor); }
    if (this.query) { u.searchParams.set('q', this.query); }
    if (withTotal) { u.searchParams.set('total', '1'); }
    return u.toString();
  };

  MayaTable.prototype.load = function (cursor, size, withTotal) {
    return fetch(this.url(cursor, size, withTotal), { credentials: 'same-origin',
      headers: { Accept: 'application/json' } }).then(function (r) {
      return r.json().then(function (body) {
        if (!r.ok) { throw new Error(body.error || ('HTTP ' + r.status)); }
        return body;
      });
    });
  };

  MayaTable.prototype.restart = function () { this.cursors = [null]; this.page = 0; this.fetch(0); };

  MayaTable.prototype.fetch = function (p) {
    var self = this;
    this.el.note.textContent = 'Loading…';
    return this.load(this.cursors[p], this.size, p === 0).then(function (body) {
      self.page = p;
      self.next = body.next_cursor || null;
      if (body.total !== null && body.total !== undefined) { self.total = body.total; }
      self.rows = body.rows.map(rowFromHtml);
      self.render();
    }).catch(function (err) { self.el.note.textContent = 'Could not load the page: ' + err.message; });
  };

  MayaTable.prototype.walkToEnd = function () {
    var self = this, hops = 0;
    function step() {
      if (!self.next || hops++ > 500) { return null; }
      self.cursors[self.page + 1] = self.next;
      return self.fetch(self.page + 1).then(step);
    }
    return step();
  };

  // -- both modes ----------------------------------------------------------------------------
  MayaTable.prototype.filtered = function () {
    if (this.source) { return this.rows; }       // the server already searched and sorted
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

  MayaTable.prototype.paint = function (rows) {
    var self = this, body = this.table.tBodies[0];
    while (body.firstChild) { body.removeChild(body.firstChild); }
    rows.forEach(function (r) {
      r.cells.forEach(function (c, idx) { c.hidden = !self.visible(idx); self.highlight(c); });
      body.appendChild(r.tr);
    });
    this.heads.forEach(function (th, idx) {
      th.hidden = !self.visible(idx);
      var dir = th.querySelector('.mt-dir');
      if (self.source) {
        var key = th.getAttribute('data-sort-key');
        var on = key && (self.serverSort === key || self.serverSort === '-' + key);
        var asc = self.serverSort === key;
        if (dir) { dir.textContent = on ? (asc ? '▲' : '▼') : ''; }
        th.setAttribute('aria-sort', on ? (asc ? 'ascending' : 'descending') : 'none');
        return;
      }
      var s = self.sorts.filter(function (x) { return x.idx === idx; })[0];
      var rank = self.sorts.indexOf(s);
      if (dir) { dir.textContent = s ? (s.dir > 0 ? '▲' : '▼') + (self.sorts.length > 1 ? rank + 1 : '') : ''; }
      th.setAttribute('aria-sort', s ? (s.dir > 0 ? 'ascending' : 'descending') : 'none');
    });
  };

  MayaTable.prototype.render = function () {
    if (this.source) { this.renderServer(); return; }
    var rows = this.filtered(), total = rows.length;
    var size = this.size || total || 1;
    var pages = Math.max(1, Math.ceil(total / size));
    this.page = Math.min(Math.max(0, this.page), pages - 1);
    var start = this.page * size, end = Math.min(total, start + size);
    this.paint(rows.slice(start, end));
    var removed = this.rows.length - total;
    this.el.info.textContent = total ? ('Showing ' + (start + 1) + '–' + end + ' of ' + total) : 'Showing 0 of 0';
    this.el.note.textContent = this.query ? (removed + ' row' + (removed === 1 ? '' : 's') + ' filtered out by "' + this.query + '"') : '';
    this.el.prev.disabled = this.el.first.disabled = this.page === 0;
    this.el.next.disabled = this.el.last.disabled = this.page >= pages - 1;
    this.showEmpty(total === 0, this.rows.length);
  };

  MayaTable.prototype.renderServer = function () {
    var n = this.rows.length, start = this.page * this.size;
    this.paint(this.rows);
    var of = this.total === null ? (this.next ? 'more' : String(start + n)) : String(this.total);
    this.el.info.textContent = n ? ('Showing ' + (start + 1) + '–' + (start + n) + ' of ' + of) : 'Showing 0 of 0';
    this.el.note.textContent = this.query ? ((this.total === null ? 'Matches' : this.total + ' match') + ' "' + this.query + '"') : '';
    this.el.prev.disabled = this.el.first.disabled = this.page === 0;
    this.el.next.disabled = this.el.last.disabled = !this.next;
    this.showEmpty(n === 0, this.query ? 1 : 0);
  };

  MayaTable.prototype.showEmpty = function (none, hadRows) {
    this.el.empty.hidden = !none;
    this.el.scroll.hidden = none;
    if (none && hadRows && this.query) {
      this.el.empty.textContent = 'No rows match "' + this.query + '". Clear the search to see all.';
    }
  };

  MayaTable.prototype.exportRows = function () {
    if (!this.source) { return Promise.resolve(this.filtered()); }
    var self = this, all = [];
    function step(cursor) {                     // every page of the current view
      return self.load(cursor, EXPORT_PAGE, false).then(function (body) {
        body.rows.forEach(function (html) { all.push(rowFromHtml(html, all.length)); });
        return body.next_cursor ? step(body.next_cursor) : all;
      });
    }
    this.el.note.textContent = 'Exporting…';
    return step(null);
  };

  MayaTable.prototype.exportCsv = function () {
    var self = this;
    function q(v) { v = String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }
    var cols = this.heads.map(function (_, i) { return i; }).filter(function (i) {
      return self.visible(i) && !self.heads[i].hasAttribute('data-noexport'); });
    this.exportRows().then(function (rows) {
      var lines = [cols.map(function (i) { return q(self.heads[i].getAttribute('data-label') || self.heads[i].textContent.trim()); }).join(',')];
      rows.forEach(function (r) {
        lines.push(cols.map(function (i) {
          var tmp = document.createElement('div'); tmp.innerHTML = r.cells[i].getAttribute('data-orig');
          return q((r.cells[i].getAttribute('data-sort') || tmp.textContent || '').trim());
        }).join(','));
      });
      var blob = new Blob([lines.join('\n') + '\n'], { type: 'text/csv' });
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = (self.id || 'table') + '.csv';
      document.body.appendChild(a); a.click(); a.remove();
      if (self.source) { self.renderServer(); }
    }).catch(function (err) { self.el.note.textContent = 'Export failed: ' + err.message; });
  };

  function init(root) {
    (root || document).querySelectorAll('[data-maya-table]').forEach(function (w) {
      if (!w.__mayaTable) { w.__mayaTable = new MayaTable(w); }
    });
  }
  window.MayaTables = { init: init };
  document.addEventListener('DOMContentLoaded', function () { init(document); });
})();
