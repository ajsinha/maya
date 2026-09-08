/* MAYA — the live log viewer.
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 *
 * An EventSource, a bounded list of nodes, and filters that reopen the stream
 * rather than hiding rows. Two decisions worth stating.
 *
 * Filtering happens on the SERVER. Hiding rows in the browser looks the same
 * until the ring turns over, at which point the page is holding a filtered
 * view of lines that no longer exist and cannot get the ones it discarded —
 * so a narrow filter would show less and less of what matched it.
 *
 * The list is capped here as well as in the process. A tab left open on a busy
 * server accumulates DOM nodes until the browser gives up, and the page that
 * exists to diagnose a problem must not become one.
 */
(function () {
  "use strict";

  var MAX_NODES = 3000;
  var view = document.getElementById("logv");
  var empty = document.getElementById("empty");
  var status = document.getElementById("status");
  var counts = document.getElementById("counts");
  var follow = document.getElementById("follow");
  var wrap = document.getElementById("wrap");
  var download = document.getElementById("download");
  if (!view) { return; }

  /* The server rendered the first screenful and said how far it got. Starting
     at 0 instead would replay every one of those lines underneath itself. */
  var source = null;
  var cursor = parseInt(view.getAttribute("data-cursor"), 10) || 0;
  var shown = view.querySelectorAll(".logl").length;

  function filters() {
    return {
      level: document.getElementById("f-level").value,
      logger_name: document.getElementById("f-logger").value,
      contains: document.getElementById("f-contains").value.trim(),
      request_id: document.getElementById("f-request").value.trim(),
      principal: document.getElementById("f-principal").value.trim(),
      quiet: document.getElementById("quiet").checked ? "true" : "false"
    };
  }

  function query(extra) {
    var f = filters(), parts = [];
    Object.keys(f).forEach(function (k) {
      if (f[k]) { parts.push(k + "=" + encodeURIComponent(f[k])); }
    });
    if (extra) { parts.push(extra); }
    return parts.join("&");
  }

  function say(text, tone) {
    status.textContent = text;
    status.className = "chip" + (tone ? " " + tone : "");
  }

  function atBottom() {
    return view.scrollHeight - view.scrollTop - view.clientHeight < 40;
  }

  function trim() {
    while (view.children.length > MAX_NODES) { view.removeChild(view.firstChild); }
  }

  function add(node) {
    /* Whether to scroll is decided BEFORE the node is added: afterwards the
       page is already taller and every position looks like "not at the
       bottom", so following would stop the moment the first line arrived. */
    var stick = follow.checked && atBottom();
    if (empty) { empty.remove(); empty = null; }
    view.appendChild(node);
    trim();
    if (stick) { view.scrollTop = view.scrollHeight; }
  }

  function cell(className, text, title) {
    var el = document.createElement("span");
    el.className = className;
    el.textContent = text;
    if (title) { el.title = title; }
    return el;
  }

  function render(line) {
    var row = document.createElement("div");
    row.className = "logl lvl-" + line.level;
    row.appendChild(cell("lt", line.ts.slice(11), line.ts));
    row.appendChild(cell("ll", line.level));

    var body = document.createElement("span");
    body.className = "lm";
    body.appendChild(cell("lg", line.logger + " "));
    if (line.request_id && line.request_id !== "-") {
      /* Clicking a request id filters to that one request. Following one call
         through six modules is the single most common thing somebody does
         with a log, and typing a sixteen-character hex string to do it is how
         they stop bothering. */
      var rid = cell("lr", "[" + line.request_id +
        (line.principal && line.principal !== "-" ? " " + line.principal : "") + "] ",
        "show only this request");
      rid.addEventListener("click", function () {
        document.getElementById("f-request").value = line.request_id;
        restart();
      });
      body.appendChild(rid);
    }
    /* The access line's own message already reads "GET /path -> 200 in 3.9ms".
       Appending the structured fields printed all four of them twice on every
       request line, which is most of them. */
    body.appendChild(document.createTextNode(line.message));
    row.appendChild(body);

    if (line.exception) {
      var trace = document.createElement("pre");
      trace.textContent = line.exception;
      row.appendChild(trace);
      row.style.gridTemplateColumns = "8.5rem 5rem 1fr";
    }
    return row;
  }

  function gap(missed) {
    var el = document.createElement("div");
    el.className = "loggap";
    el.textContent = "… " + missed + " line(s) aged out of the window before " +
      "this page could show them. The server is writing faster than the ring holds.";
    return el;
  }

  function open() {
    close();
    say("connecting…");
    source = new EventSource("/api/v1/logs/stream?" + query("after=" + cursor));
    source.onopen = function () { say("live", "chip-ok"); };
    source.onmessage = function (event) {
      var line = JSON.parse(event.data);
      cursor = line.seq;
      add(render(line));
      shown += 1;
      counts.textContent = shown + " line(s) shown";
    };
    source.addEventListener("gap", function (event) {
      add(gap(JSON.parse(event.data).missed));
    });
    source.addEventListener("closing", function () {
      /* The server closes a long-lived stream on purpose. EventSource will
         reconnect by itself and resume from the last id, so this is a note
         rather than a problem — but saying nothing would leave a two-second
         gap that looks like a stall. */
      say("reconnecting…");
    });
    source.onerror = function () {
      /* Reporting this matters: a viewer that silently stops updating is
         indistinguishable from a server that has gone quiet, and those need
         opposite responses.

         But the two states are not the same, and calling both "disconnected"
         overstates the common one. EventSource retries by itself, and while it
         is doing so `readyState` is CONNECTING — a proxy that recycled the
         connection, a server that restarted, a laptop that woke up. CLOSED is
         the one that needs a person: the browser has given up. */
      if (source && source.readyState === EventSource.CLOSED) {
        say("disconnected — reload to resume", "chip-bad");
      } else {
        say("reconnecting…", "chip-warn");
      }
    };
  }

  function close() {
    if (source) { source.close(); source = null; }
  }

  function restart() {
    /* A changed filter starts a NEW window: the lines already on screen matched
       the old one. Cursor goes back to 0 so the server replays what it still
       holds through the new filter, which is what somebody who has just typed
       a request id expects to see. */
    cursor = 0; shown = 0;
    view.textContent = "";
    var note = document.createElement("p");
    note.className = "text-muted small p-3 mb-0";
    note.textContent = "Reading the window through the new filter…";
    view.appendChild(note);
    empty = note;
    download.href = "/api/v1/logs/download?" + query();
    open();
  }

  var typing = null;
  function debounced() {
    window.clearTimeout(typing);
    typing = window.setTimeout(restart, 300);
  }

  ["f-level", "f-logger", "quiet"].forEach(function (id) {
    document.getElementById(id).addEventListener("change", restart);
  });
  ["f-contains", "f-request", "f-principal"].forEach(function (id) {
    document.getElementById(id).addEventListener("input", debounced);
  });
  wrap.addEventListener("change", function () {
    view.classList.toggle("nowrap", !wrap.checked);
  });
  follow.addEventListener("change", function () {
    if (follow.checked) { view.scrollTop = view.scrollHeight; }
  });
  /* Scrolling up turns following off, because a person scrolling up is reading
     something and a viewer that yanks them back to the bottom is one they
     fight. Scrolling back to the bottom turns it on again. */
  view.addEventListener("scroll", function () {
    follow.checked = atBottom();
  });
  window.addEventListener("beforeunload", close);

  /* The request ids the server rendered are clickable too — the same act as
     on a streamed line, wired once here rather than duplicated in the
     template, which cannot attach a handler under this CSP anyway. */
  view.querySelectorAll(".lr").forEach(function (el) {
    el.addEventListener("click", function () {
      document.getElementById("f-request").value = el.getAttribute("data-request");
      restart();
    });
  });

  if (shown) { counts.textContent = shown + " line(s) shown"; }
  view.scrollTop = view.scrollHeight;
  download.href = "/api/v1/logs/download?" + query();
  open();
}());
