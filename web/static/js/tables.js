/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright (c) 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Search, sort and pagination for every table in the interface.
 *
 * Written rather than vendored, for the same reason the JWT verifier and the
 * xlsx writer are: this platform must be deployable air-gapped, every asset is
 * served from disk, and a table plugin is a hundred lines of arithmetic wearing
 * eighty kilobytes. It also means the controls match Bootstrap exactly instead
 * of fighting it.
 *
 * IT ENHANCES EVERY TABLE AND SHOWS CONTROLS ONLY WHERE THEY HELP. Sorting is
 * always available, because a reader who wants the worst finding first should
 * not have to count rows. Search and paging appear once a table is long enough
 * for them to be worth the space — a pager under four rows is noise, and noise
 * is what makes people stop reading a page.
 *
 * Opt out with `data-plain` on the table.
 */
(function () {
  "use strict";

  var PAGE_SIZE = 15;      // rows per page once paging kicks in
  var CONTROLS_FROM = 8;   // rows below which search and paging are just noise

  function text(cell) {
    return (cell.textContent || "").trim();
  }

  /* A cell's sort key. Numbers sort as numbers and dates as dates, so "9"
   * does not come after "10" and a Gini of 0.61 does not sort below 0.7
   * as a string would. Everything else falls back to lowercased text. */
  function key(cell) {
    var raw = cell.getAttribute("data-sort");
    if (raw !== null) { return raw; }
    var value = text(cell);
    var numeric = value.replace(/[,%\s]/g, "").replace(/^[£$€]/, "");
    if (numeric !== "" && !isNaN(numeric)) { return parseFloat(numeric); }
    var stamp = Date.parse(value);
    if (!isNaN(stamp) && /\d{4}/.test(value)) { return stamp; }
    return value.toLowerCase();
  }

  function compare(a, b) {
    if (typeof a === "number" && typeof b === "number") { return a - b; }
    return String(a) < String(b) ? -1 : (String(a) > String(b) ? 1 : 0);
  }

  function build(table) {
    var body = table.tBodies[0];
    if (!body) { return null; }
    var rows = Array.prototype.slice.call(body.rows);
    /* A row that spans the whole table is a message ("nothing here yet"), not
     * data. Sorting or paging it away would hide the one thing a reader needs. */
    rows = rows.filter(function (r) {
      return !(r.cells.length === 1 && r.cells[0].colSpan > 1);
    });
    return { table: table, body: body, all: rows, shown: rows,
             page: 0, sortIndex: -1, ascending: true };
  }

  function render(state) {
    var start = state.page * PAGE_SIZE;
    var paging = state.all.length >= CONTROLS_FROM;
    state.all.forEach(function (row) { row.hidden = true; });
    var visible = paging ? state.shown.slice(start, start + PAGE_SIZE) : state.shown;
    visible.forEach(function (row) { row.hidden = false; });
    if (state.status) {
      var total = state.all.length;
      state.status.textContent = state.shown.length === total
        ? (paging ? "Showing " + (state.shown.length ? start + 1 : 0) + "–" +
                    Math.min(start + PAGE_SIZE, total) + " of " + total : "")
        : state.shown.length + " of " + total + " match";
    }
    if (state.pager) { pager(state); }
  }

  function pager(state) {
    var pages = Math.max(1, Math.ceil(state.shown.length / PAGE_SIZE));
    state.pager.innerHTML = "";
    if (pages < 2) { return; }
    function button(label, target, disabled, current) {
      var li = document.createElement("li");
      li.className = "page-item" + (disabled ? " disabled" : "") +
                     (current ? " active" : "");
      var a = document.createElement("button");
      a.type = "button";
      a.className = "page-link";
      a.textContent = label;
      if (current) { a.setAttribute("aria-current", "page"); }
      a.addEventListener("click", function () {
        state.page = target;
        render(state);
      });
      li.appendChild(a);
      state.pager.appendChild(li);
    }
    button("‹", Math.max(0, state.page - 1), state.page === 0, false);
    /* A window around the current page: a hundred page numbers is not
     * navigation, it is a wall. */
    var first = Math.max(0, Math.min(state.page - 2, pages - 5));
    var last = Math.min(pages, first + 5);
    for (var i = first; i < last; i++) {
      button(String(i + 1), i, false, i === state.page);
    }
    button("›", Math.min(pages - 1, state.page + 1), state.page >= pages - 1, false);
  }

  function filter(state, query) {
    var needle = query.trim().toLowerCase();
    state.shown = needle === "" ? state.all : state.all.filter(function (row) {
      return (row.textContent || "").toLowerCase().indexOf(needle) !== -1;
    });
    state.page = 0;
    render(state);
  }

  function sortBy(state, index, header) {
    state.ascending = state.sortIndex === index ? !state.ascending : true;
    state.sortIndex = index;
    var direction = state.ascending ? 1 : -1;
    state.all.sort(function (a, b) {
      if (!a.cells[index] || !b.cells[index]) { return 0; }
      return direction * compare(key(a.cells[index]), key(b.cells[index]));
    });
    state.all.forEach(function (row) { state.body.appendChild(row); });
    Array.prototype.forEach.call(header.parentNode.cells, function (cell) {
      cell.setAttribute("aria-sort", "none");
      var mark = cell.querySelector(".sort-mark");
      if (mark) { mark.textContent = ""; }
    });
    header.setAttribute("aria-sort", state.ascending ? "ascending" : "descending");
    var own = header.querySelector(".sort-mark");
    if (own) { own.textContent = state.ascending ? " ▲" : " ▼"; }
    filter(state, state.search ? state.search.value : "");
  }

  function controls(state) {
    var table = state.table;
    var bar = document.createElement("div");
    bar.className = "d-flex flex-wrap align-items-center gap-2 mb-2";

    var input = document.createElement("input");
    input.type = "search";
    input.className = "form-control form-control-sm";
    input.style.maxWidth = "16rem";
    input.placeholder = "Search " + state.all.length + " rows";
    input.setAttribute("aria-label", "Search this table");
    input.addEventListener("input", function () { filter(state, input.value); });
    state.search = input;

    var status = document.createElement("span");
    status.className = "text-muted small ms-auto";
    /* Announced politely: a screen reader should hear the count settle, not be
     * interrupted on every keystroke. */
    status.setAttribute("aria-live", "polite");
    state.status = status;

    bar.appendChild(input);
    bar.appendChild(status);
    table.parentNode.insertBefore(bar, table);

    var nav = document.createElement("nav");
    nav.setAttribute("aria-label", "Table pages");
    var ul = document.createElement("ul");
    ul.className = "pagination pagination-sm mb-0 mt-2";
    nav.appendChild(ul);
    table.parentNode.insertBefore(nav, table.nextSibling);
    state.pager = ul;
  }

  function enhance(table) {
    if (table.hasAttribute("data-plain") || table.dataset.enhanced) { return; }
    var head = table.tHead;
    if (!head || !head.rows.length) { return; }
    var state = build(table);
    if (!state || state.all.length < 2) { return; }
    table.dataset.enhanced = "1";

    Array.prototype.forEach.call(head.rows[0].cells, function (cell, index) {
      if (cell.hasAttribute("data-no-sort")) { return; }
      cell.setAttribute("role", "columnheader");
      cell.setAttribute("aria-sort", "none");
      cell.tabIndex = 0;
      cell.style.cursor = "pointer";
      cell.title = "Sort by " + text(cell);
      if (!cell.querySelector(".sort-mark")) {
        var mark = document.createElement("span");
        mark.className = "sort-mark text-muted";
        cell.appendChild(mark);
      }
      function activate() { sortBy(state, index, cell); }
      cell.addEventListener("click", activate);
      cell.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
    });

    if (state.all.length >= CONTROLS_FROM) { controls(state); }
    render(state);
  }

  function enhanceAll() {
    Array.prototype.forEach.call(document.querySelectorAll("table"), enhance);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceAll);
  } else {
    enhanceAll();
  }
  /* Tables that arrive from an API call after load — the policy page builds
   * several — are enhanced when whoever inserted them says so. */
  window.mayaEnhanceTables = enhanceAll;
})();
