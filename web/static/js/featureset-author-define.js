/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Composing a featureset.
 *
 * It decides NOTHING. Every question about whether a composition resolves — is
 * that parent known, does that operation do anything, is this a cycle, is it
 * deeper than the limit, is that retrieval policy a policy — is answered by
 * POST /api/v1/featuresets/preview, which runs the same fold `define` runs and
 * writes nothing. The screen renders the answer.
 *
 * So the Declare button is enabled by that call returning 200, and by nothing
 * computed here. A client that re-implemented the fold would be a second
 * implementation of a composition rule, and the second disagrees with the first
 * eventually, in the direction of permitting more.
 *
 * The preview does not see the name, the label slot or the outcome window —
 * they are not part of the composition — so three of `define`'s refusals can
 * only arrive when Declare is pressed. The page says so rather than implying a
 * green preview is a guarantee.
 */
(function () {
  "use strict";

  var CFG = window.MAYA_FEATURESET_AUTHOR || {};
  var timer = null;

  function esc(s) {
    return String(s === undefined || s === null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function options(values, selected) {
    return values.map(function (v) {
      return '<option value="' + esc(v) + '"' +
             (v === selected ? " selected" : "") + ">" + esc(v) + "</option>";
    }).join("");
  }

  // A slot's type must equal its feature's exactly, so the offered list is the
  // types the catalogue carries. An empty catalogue gets a free-text box rather
  // than an empty select: a register with no features can still declare a
  // schema, and offering nothing would make that impossible.
  function typeField(cls, selected) {
    if (!(CFG.dtypes || []).length) {
      return '<input class="form-control form-control-sm ' + cls + '" ' +
             'value="' + esc(selected || "numeric") + '" aria-label="Type">';
    }
    return '<select class="form-select form-select-sm ' + cls +
           '" aria-label="Type">' + options(CFG.dtypes, selected) + "</select>";
  }

  function dropButton() {
    return '<div class="col-auto"><button type="button" class="btn btn-sm ' +
           'btn-outline-secondary py-0 px-2 drop-row" style="font-size:.72rem" ' +
           'aria-label="Remove this row">&times;</button></div>';
  }

  function slotRow() {
    return '<div class="row g-2 mb-1 align-items-center fs-row">' +
      '<div class="col-md-4"><input class="form-control form-control-sm slot-name" ' +
        'placeholder="slot name, e.g. dscr" aria-label="Slot name"></div>' +
      '<div class="col-md-3">' + typeField("slot-type") + "</div>" +
      '<div class="col-md-3"><div class="form-check">' +
        '<input class="form-check-input slot-null" type="checkbox">' +
        '<label class="form-check-label small">nullable</label></div></div>' +
      dropButton() + "</div>";
  }

  function parentRow() {
    return '<div class="row g-2 mb-1 align-items-center fs-row">' +
      '<div class="col-md-6"><select class="form-select form-select-sm parent-name" ' +
        'aria-label="Featureset to compose from">' +
        options(CFG.parents || []) + "</select></div>" +
      '<div class="col-md-5"><span class="text-muted" style="font-size:.72rem">' +
        "later rows win where they overlap</span></div>" +
      dropButton() + "</div>";
  }

  function opRow() {
    return '<div class="row g-2 mb-1 align-items-center fs-row">' +
      '<div class="col-md-3"><select class="form-select form-select-sm op-kind" ' +
        'aria-label="Operation">' + options(["add", "drop", "override"]) +
        "</select></div>" +
      '<div class="col-md-4"><input class="form-control form-control-sm op-name" ' +
        'placeholder="slot name" aria-label="Slot the operation applies to"></div>' +
      '<div class="col-md-3">' + typeField("op-type") + "</div>" +
      dropButton() + "</div>";
  }

  // ------------------------------------------------------------- collecting
  function composition() {
    var body = { slots: {}, composes: [], operations: [] };
    $("#slot-rows .fs-row").each(function () {
      var name = ($(this).find(".slot-name").val() || "").trim();
      if (!name) { return; }
      body.slots[name] = { dtype: $(this).find(".slot-type").val(),
                           nullable: $(this).find(".slot-null").is(":checked") };
    });
    $("#parent-rows .fs-row").each(function () {
      var name = $(this).find(".parent-name").val();
      if (name) { body.composes.push({ name: name }); }
    });
    $("#op-rows .fs-row").each(function () {
      var name = ($(this).find(".op-name").val() || "").trim();
      if (!name) { return; }
      var op = { op: $(this).find(".op-kind").val(), name: name };
      if (op.op !== "drop") { op.value = { dtype: $(this).find(".op-type").val() }; }
      body.operations.push(op);
    });
    var raw = ($("#fs-defaults").val() || "").trim();
    if (raw) { body.defaults = JSON.parse(raw); }        // thrown to the caller
    return body;
  }

  function identity() {
    var body = {};
    body.name = ($("#fs-name").val() || "").trim();
    body.entity = ($("#fs-entity").val() || "").trim();
    if ($("#fs-grain").val()) { body.grain = $("#fs-grain").val(); }
    if ($("#fs-description").val()) { body.description = $("#fs-description").val(); }
    if ($("#fs-label").val()) { body.label_slot = ($("#fs-label").val() || "").trim(); }
    var window_ = ($("#fs-window").val() || "").trim();
    if (window_) { body.outcome_window_days = parseInt(window_, 10); }
    if ($("#fs-ephemeral").is(":checked")) { body.ephemeral = true; }
    var ttl = ($("#fs-ttl").val() || "").trim();
    if (ttl) { body.ttl_days = parseFloat(ttl); }
    return body;
  }

  // -------------------------------------------------------------- rendering
  function slotTable(resolved, declared, inherited, provenance) {
    var names = Object.keys(resolved).sort();
    if (!names.length) { return ""; }
    var html = '<table class="table maya mb-2"><thead><tr><th>Slot</th>' +
               "<th>Type</th><th>Nullable</th><th>Decided by</th></tr></thead><tbody>";
    names.forEach(function (slot) {
      var spec = resolved[slot] || {};
      var from = (provenance || {})[slot] || {};
      var origin = declared.indexOf(slot) >= 0
        ? "declared here"
        : (from.from ? "inherited from " + esc(from.from) : "inherited");
      html += "<tr><td class='small'>" + esc(slot) + "</td>" +
              "<td class='small'>" + esc(spec.dtype) + "</td>" +
              "<td class='small'>" + (spec.nullable ? "yes" : "no") + "</td>" +
              "<td class='small text-muted'>" + origin +
              (from.overrode ? " — overrode " + esc(from.overrode) : "") +
              "</td></tr>";
    });
    return html + "</tbody></table>";
  }

  function showPreview(r) {
    $("#fs-verdict").html(
      '<span class="evidence-ok">resolves</span> <span class="text-muted">— ' +
      esc(r.detail) + "</span>");
    var lineage = (r.lineage || []).map(function (l) {
      return esc(l.name) + " (" + (l.contributes || []).length + " slot(s))";
    }).join(" &rarr; ");
    $("#fs-resolved").html(
      slotTable(r.slots || {}, r.declared_slots || [], r.inherited_slots || [],
                r.provenance) +
      (lineage ? '<p class="small text-muted mb-1">Folded left to right: ' +
                 lineage + ", then this featureset's own slots and operations." +
                 "</p>" : "") +
      (r.policy && r.policy.precedence
        ? '<p class="small text-muted mb-0">Retrieval policy: ' +
          esc(r.policy.precedence) + ".</p>"
        : ""));
    $("#fs-declare").prop("disabled", false);
  }

  function refusal(where, xhr) {
    var body = (xhr.responseJSON && xhr.responseJSON.detail) || xhr.responseJSON || {};
    if (typeof body === "string") { body = { detail: body }; }
    var err = body.error || (xhr.responseJSON || {}).error || "refused";
    var detail = body.detail || xhr.statusText;
    var fix = body.remediation || (xhr.responseJSON || {}).remediation || "";
    $(where).html('<span class="evidence-bad">' + esc(err) + "</span> — " +
      esc(String(detail)) +
      (fix ? '<div class="text-muted mt-1">' + esc(String(fix)) + "</div>" : ""));
  }

  function preview() {
    var body;
    try { body = composition(); }
    catch (e) {
      $("#fs-verdict").html('<span class="evidence-bad">the retrieval policy is ' +
        "not valid JSON</span> — " + esc(e.message));
      $("#fs-resolved").empty();
      $("#fs-declare").prop("disabled", true);
      return;
    }
    if (!Object.keys(body.slots).length && !body.composes.length) {
      $("#fs-verdict").html('<span class="text-muted">Nothing to resolve yet. ' +
        "A featureset is a schema, and a schema with nothing in it is not one." +
        "</span>");
      $("#fs-resolved").empty();
      // Disabled because there is nothing to ask about, not because this page
      // formed a view: an empty composition is never sent.
      $("#fs-declare").prop("disabled", true);
      return;
    }
    $.ajax({ url: "/api/v1/featuresets/preview", method: "POST",
             contentType: "application/json", data: JSON.stringify(body) })
      .done(showPreview)
      .fail(function (xhr) {
        refusal("#fs-verdict", xhr);
        $("#fs-resolved").empty();
        // Disabled by the SERVER's verdict, never by anything decided here.
        $("#fs-declare").prop("disabled", true);
      });
  }

  function schedule() {
    if (timer) { window.clearTimeout(timer); }
    timer = window.setTimeout(preview, 250);
  }

  // ----------------------------------------------------------------- events
  $("#add-slot").on("click", function () { $("#slot-rows").append(slotRow()); schedule(); });
  $("#add-parent").on("click", function () { $("#parent-rows").append(parentRow()); schedule(); });
  $("#add-op").on("click", function () { $("#op-rows").append(opRow()); schedule(); });
  $(document).on("click", ".drop-row", function () {
    $(this).closest(".fs-row").remove();
    schedule();
  });
  $(document).on("input change", "#fs-form input, #fs-form select, #fs-form textarea",
    function () { schedule(); });
  $("#fs-form").on("submit", function (e) { e.preventDefault(); });

  $("#fs-declare").on("click", function () {
    var body;
    try { body = composition(); }
    catch (e) {
      $("#fs-result").html('<span class="evidence-bad">the retrieval policy is ' +
        "not valid JSON</span> — " + esc(e.message));
      return;
    }
    var who = identity();
    Object.keys(who).forEach(function (k) { body[k] = who[k]; });
    if (!body.name || !body.entity) {
      $("#fs-result").html('<span class="evidence-bad">a name and an entity are ' +
        "required</span> — the entity is the thing one row is about, and a " +
        "featureset without one cannot be joined to a spine");
      return;
    }
    $.ajax({ url: "/api/v1/featuresets", method: "POST",
             contentType: "application/json", data: JSON.stringify(body) })
      .done(function (r) {
        $("#fs-result").html('<span class="evidence-ok">declared</span> — ' +
          esc(r.name) + " has a schema and nothing filling it. " +
          '<a href="/featureset/' + encodeURIComponent(r.name) + '/bind">Fill its slots</a>.');
        window.setTimeout(function () {
          window.location = "/featureset/" + encodeURIComponent(r.name) + "/bind";
        }, 600);
      })
      .fail(function (xhr) { refusal("#fs-result", xhr); });
  });

  $("#slot-rows").append(slotRow());
  preview();
}());
