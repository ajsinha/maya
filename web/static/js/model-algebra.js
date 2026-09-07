/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Shared plumbing for the model-algebra screens.
 *
 * There is deliberately no governance logic in this file or in any file beside
 * it. These functions render a verdict the server reached and post a form to
 * the endpoint that decides; nothing here works out whether an act is
 * permitted, and nothing re-derives a trainability class or a tier. A screen
 * that answered such a question locally would be a second implementation of a
 * rule, and the second one drifts in the direction of permitting more.
 *
 * The CSRF token is attached by `csrf.js`, which every page loads from the base
 * template. It is not reimplemented here — a control every caller has to
 * remember is a control that will be missing from the next page somebody adds.
 */
(function () {
  "use strict";

  function escapeHtml(text) {
    return String(text === null || text === undefined ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* A refusal, as the API returned it. The detail is the platform's own words:
     it names the clause that failed, and paraphrasing it here would lose the
     one thing the caller can act on. */
  function refusalHtml(xhr) {
    /* `MAYA.refusal.read` normalises every shape the server sends. This used to
       do `escapeHtml(body.detail)`, and on a 422 `detail` is an ARRAY of
       pydantic error objects — so a letter typed into a number box rendered as
       "Refused — [object Object]". */
    var r = window.MAYA.refusal.read(xhr);
    var out = '<div class="evidence-bad">Refused — ' +
              r.lines.map(escapeHtml).join("</div><div class=\"evidence-bad\">") +
              "</div>";
    if (r.remediation) {
      out += '<div class="text-muted" style="font-size:.76rem">' +
             escapeHtml(r.remediation) + "</div>";
    }
    if (r.code) {
      out += '<div class="text-muted mono" style="font-size:.7rem">' +
             escapeHtml(r.code) + " · HTTP " + r.status + "</div>";
    }
    return out;
  }

  function refuse(selector, xhr) {
    document.querySelectorAll(selector).forEach(function (node) {
      node.innerHTML = refusalHtml(xhr);
    });
  }

  function accept(selector, message) {
    document.querySelectorAll(selector).forEach(function (node) {
      node.innerHTML = '<span class="evidence-ok">' + escapeHtml(message) + "</span>";
    });
  }

  /* JSON out of a textarea, or null with the parse error shown. A field left
     empty is absent rather than empty: a version submitted with an empty
     schema because somebody typed nothing is a version whose type is a
     mistake nobody made deliberately. */
  function parseField(value, label, where) {
    if (!value || !value.trim()) { return {ok: true, value: null}; }
    try {
      return {ok: true, value: JSON.parse(value)};
    } catch (err) {
      document.querySelectorAll(where).forEach(function (node) {
        node.innerHTML = '<span class="evidence-bad">The ' + escapeHtml(label) +
          " is not valid JSON — " + escapeHtml(err.message) + "</span>";
      });
      return {ok: false, value: null};
    }
  }

  function post(url, body) {
    return jQuery.ajax({url: url, method: "POST", contentType: "application/json",
                        data: JSON.stringify(body || {})});
  }

  function put(url, body) {
    return jQuery.ajax({url: url, method: "PUT", contentType: "application/json",
                        data: JSON.stringify(body || {})});
  }

  /* DELETE, which the three verbs above did not cover. Added when the model
     page grew a delete control; a screen assembling its own `$.ajax` beside
     these would be a fourth spelling of the same thing. */
  function remove(url) {
    return jQuery.ajax({url: url, method: "DELETE"});
  }

  function patch(url, body) {
    return jQuery.ajax({url: url, method: "PATCH", contentType: "application/json",
                        data: JSON.stringify(body || {})});
  }

  function fields(form) {
    return Object.fromEntries(new FormData(form));
  }

  /* A schema as chips, for the composite and the refinement answers. */
  function schemaHtml(schema) {
    if (!schema || !schema.length) { return '<span class="text-muted">none</span>'; }
    return schema.map(function (f) {
      var span = "";
      if (f.minimum !== null && f.minimum !== undefined) { span += " ≥" + f.minimum; }
      if (f.maximum !== null && f.maximum !== undefined) { span += " ≤" + f.maximum; }
      return '<span class="chip">' + escapeHtml(f.name) + ":" +
             escapeHtml(f.dtype || "numeric") + escapeHtml(span) + "</span> ";
    }).join("");
  }

  window.mayaAlgebra = {
    escapeHtml: escapeHtml, refusalHtml: refusalHtml, refuse: refuse,
    accept: accept, parseField: parseField, post: post, put: put,
    patch: patch, remove: remove,
    fields: fields, schemaHtml: schemaHtml
  };
}());
