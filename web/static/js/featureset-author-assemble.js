/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Assembling a point-in-time-correct training set.
 *
 * It decides NOTHING about correctness. Whether the assembly is admissible is
 * answered in two layers by the platform — layer 1 refuses outright when a
 * temporal bound is missing, layer 2 independently recomputes a stratified
 * sample by a different route and compares — and this screen renders both
 * verdicts, including the case where they disagree.
 *
 * The spine rows are seeded from the entity ids actually present in the pinned
 * namespaces. A spine invented against entities that do not exist assembles a
 * table of nulls, which looks like a working assembly and teaches nobody what
 * the bound does.
 */
(function () {
  "use strict";

  var CFG = window.MAYA_FEATURESET_ASSEMBLE || {};

  function esc(s) {
    return String(s === undefined || s === null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  /* Every entity id in the samples, and the widest ingest clock seen, so the
   * page can offer an as_of that admits something rather than an epoch nobody
   * would guess. Suggested, never imposed: the whole point of the screen is
   * moving that number and watching what the rule refuses. */
  function seed() {
    var entities = {}, latest = 0;
    Object.keys(CFG.samples || {}).forEach(function (namespace) {
      (CFG.samples[namespace].rows || []).forEach(function (r) {
        if (r.entity_id !== undefined) { entities[r.entity_id] = 1; }
        ["event_ts", "ingest_ts"].forEach(function (k) {
          if (typeof r[k] === "number" && r[k] > latest) { latest = r[k]; }
        });
      });
    });
    return { entities: Object.keys(entities).sort(), latest: latest };
  }

  var SEED = seed();

  function entityField(value) {
    if (!SEED.entities.length) {
      return '<input class="form-control form-control-sm s-entity" ' +
             'value="' + esc(value) + '" placeholder="entity id" ' +
             'aria-label="Entity id">';
    }
    return '<select class="form-select form-select-sm s-entity" ' +
      'aria-label="Entity id">' + SEED.entities.map(function (e) {
        return '<option value="' + esc(e) + '"' +
               (e === value ? " selected" : "") + ">" + esc(e) + "</option>";
      }).join("") + "</select>";
  }

  function spineRow(entity, labelTs) {
    return '<div class="p-2 border-bottom spine-row"><div class="row g-2 align-items-center">' +
      '<div class="col-md-4">' + entityField(entity) + "</div>" +
      '<div class="col-md-4"><input class="form-control form-control-sm s-label-ts" ' +
        'value="' + esc(labelTs) + '" placeholder="label_ts" ' +
        'aria-label="When the label matured"></div>' +
      '<div class="col-md-3"><input class="form-control form-control-sm s-label" ' +
        'placeholder="label (optional)" aria-label="Label value"></div>' +
      '<div class="col-md-1"><button type="button" class="btn btn-sm ' +
        'btn-outline-secondary py-0 px-2 s-drop" aria-label="Remove this row">' +
        "&times;</button></div>" +
    "</div></div>";
  }

  function collect() {
    var spine = [];
    $(".spine-row").each(function () {
      var entity = $(this).find(".s-entity").val();
      var at = parseFloat($(this).find(".s-label-ts").val());
      if (!entity || isNaN(at)) { return; }
      var row = { entity_id: entity, label_ts: at };
      var label = ($(this).find(".s-label").val() || "").trim();
      if (label !== "") {
        var numeric = Number(label);
        row.label = isNaN(numeric) ? label : numeric;
      }
      spine.push(row);
    });
    return spine;
  }

  function refusal(xhr) {
    var body = (xhr.responseJSON && xhr.responseJSON.detail) || xhr.responseJSON || {};
    if (typeof body === "string") { body = { detail: body }; }
    var err = body.error || (xhr.responseJSON || {}).error || "refused";
    var detail = body.detail || xhr.statusText;
    var fix = body.remediation || (xhr.responseJSON || {}).remediation || "";
    $("#asm-result").html('<span class="evidence-bad">' + esc(err) + "</span> — " +
      esc(String(detail)) +
      (fix ? '<div class="text-muted mt-1">' + esc(String(fix)) + "</div>" : ""));
  }

  function report(snapshot) {
    var pit = snapshot.pit_report || {};
    var verified = snapshot.pit_verified;
    var html = "<div>" +
      (verified ? '<span class="evidence-ok">point-in-time verified</span>'
                : '<span class="evidence-bad">not point-in-time verified</span>') +
      " — " + esc(snapshot.row_count) + " row(s) into <code>" +
      esc(snapshot.delta_table) + "</code> at delta v" +
      esc(snapshot.delta_version) + "</div>";
    html += "<table class='table maya mt-2 mb-1'><thead><tr><th>Layer</th>" +
            "<th>Checked</th><th>Verdict</th></tr></thead><tbody>" +
      "<tr><td class='small'>1 — static</td><td class='small'>both temporal bounds</td>" +
        "<td class='small'><span class='evidence-ok'>passed</span>" +
        "<div class='text-muted'>an assembly missing either bound is refused " +
        "outright, before a row is read</div></td></tr>" +
      "<tr><td class='small'>2 — " + esc(pit.layer || "sampled") + "</td>" +
        "<td class='small'>" + esc(pit.checked) + " row(s)</td>" +
        "<td class='small'>" + (pit.passed
          ? "<span class='evidence-ok'>agreed</span>"
          : "<span class='evidence-bad'>disagreed</span>") +
        "<div class='text-muted'>" + esc(pit.detail) + "</div></td></tr>" +
      "</tbody></table>";
    if ((pit.violations || []).length) {
      html += "<table class='table maya mb-1'><thead><tr><th>Entity</th>" +
              "<th>Feature</th><th>Assembled</th><th>Independently recomputed</th>" +
              "</tr></thead><tbody>";
      pit.violations.forEach(function (v) {
        html += "<tr><td class='small'>" + esc(v.entity_id) + "</td><td class='small'>" +
                esc(v.feature) + "</td><td class='small'>" + esc(v.assembled) +
                "</td><td class='small'>" + esc(v.expected) + "</td></tr>";
      });
      html += "</tbody></table>";
    }
    if ((pit.leakage || []).length) {
      html += "<div class='mt-1'><span class='evidence-bad'>suspected leakage</span> " +
              "in <code>" + esc(pit.leakage.join(", ")) + "</code>" +
              "<div class='text-muted'>a feature that predicts the label perfectly " +
              "is almost always the label under another name. A screen, not a " +
              "proof — but it fires on the shape a leak actually has.</div></div>";
    }
    html += "<div class='text-muted mt-1'>The snapshot records this report " +
            "whichever way it went, and it names the featureset version it came " +
            "from — so a fit warrant may pin the snapshot and recompute nothing." +
            "</div>";
    $("#asm-result").html(html);
  }

  // ----------------------------------------------------------------- events
  $("#add-spine").on("click", function () {
    $("#spine-rows").append(spineRow(SEED.entities[0] || "", $("#asm-asof").val() || ""));
  });
  $(document).on("click", ".s-drop", function () {
    $(this).closest(".spine-row").remove();
  });

  $("#asm-run").on("click", function () {
    var spine = collect();
    var asOf = parseFloat($("#asm-asof").val());
    if (!spine.length) {
      $("#asm-result").html('<span class="evidence-bad">the spine is empty</span> ' +
        "— an assembly with no rows has nothing to be correct about");
      return;
    }
    if (isNaN(asOf)) {
      $("#asm-result").html('<span class="evidence-bad">as_of is required</span> ' +
        "— it is the transaction-time cut, and the assembly is refused without it");
      return;
    }
    var body = { version: parseInt($("#asm-version").val(), 10),
                 spine: spine, as_of: asOf };
    var name = ($("#asm-name").val() || "").trim();
    if (name) { body.name = name; }
    $("#asm-result").html('<span class="text-muted">assembling…</span>');
    $.ajax({ url: "/api/v1/featuresets/" + encodeURIComponent(CFG.name) + "/training-sets",
             method: "POST", contentType: "application/json",
             data: JSON.stringify(body) })
      .done(report)
      .fail(refusal);
  });

  // One row per entity in the sample, so the first assembly on a fresh
  // instance is one click rather than an exercise in guessing identifiers.
  if (SEED.entities.length) {
    SEED.entities.slice(0, 8).forEach(function (e) {
      $("#spine-rows").append(spineRow(e, SEED.latest || ""));
    });
    if (!$("#asm-asof").val()) { $("#asm-asof").val(SEED.latest || ""); }
  } else {
    $("#spine-rows").append(spineRow("", ""));
  }
}());
