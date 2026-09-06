/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Filling a featureset's schema.
 *
 * It decides NOTHING. Whether a feature may fill a slot — is its dtype the
 * slot's, is there a view carrying it, is that view ambiguous, does it read the
 * label — is decided by POST /featuresets/{name}/versions, and every refusal
 * shown here is that call's, rendered with its remediation.
 *
 * Two consequences worth being explicit about, because both are places a
 * well-meant client would go wrong:
 *
 *  * The feature list offered for a slot is NOT filtered to the slot's dtype.
 *    A mismatch is refused by the register with a message that names both
 *    types, and hiding the option would teach nobody why. The list carries each
 *    feature's type so the mistake is visible before it is made.
 *  * The publish button is not gated on a check, because there is no check to
 *    gate it on: the platform previews a composition and offers nothing that
 *    resolves a filling without recording it. The attempt is the check, and a
 *    refused attempt writes nothing.
 *
 * The leakage panel renders GET /derived-features/{name}/lineage — the
 * register's own closure over what the label rests on and what rests on it. It
 * is shown for information; the refusal still comes from the publish.
 */
(function () {
  "use strict";

  var CFG = window.MAYA_FEATURESET_BIND || {};
  var SLOTS = Object.keys(CFG.slots || {}).sort();

  function esc(s) {
    return String(s === undefined || s === null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function featureOptions(selected) {
    var html = '<option value="">— choose a feature —</option>';
    (CFG.catalogue || []).forEach(function (f) {
      html += '<option value="' + esc(f.name) + '"' +
              (f.name === selected ? " selected" : "") + ">" +
              esc(f.name) + " — " + esc(f.dtype) +
              (f.derived ? " (derived)" : "") + "</option>";
    });
    return html;
  }

  function viewOptions(feature, view, version) {
    var supply = (CFG.supply || {})[feature] || [];
    var html = '<option value="">— let the register choose —</option>';
    supply.forEach(function (s) {
      var value = s.view + "@" + s.version;
      html += '<option value="' + esc(value) + '"' +
              (s.view === view && s.version === version ? " selected" : "") + ">" +
              esc(s.view) + " v" + s.version + " — delta v" + s.delta_version +
              ", " + s.rows + " row(s)</option>";
    });
    return html;
  }

  function supplyNote(feature) {
    var supply = (CFG.supply || {})[feature] || [];
    if (!feature) { return ""; }
    if (!supply.length) {
      return "no materialised view carries this feature yet";
    }
    var views = {};
    supply.forEach(function (s) { views[s.view] = 1; });
    var names = Object.keys(views);
    if (names.length > 1) {
      return names.length + " views carry it (" + names.join(", ") +
             ") — the register refuses an ambiguous binding, so name one";
    }
    return "carried by " + names[0] + ", " + supply.length + " version(s)";
  }

  function row(slot) {
    var spec = (CFG.slots || {})[slot] || {};
    var bound = (CFG.bindings || {})[slot] || {};
    var isLabel = slot === CFG.labelSlot;
    var inherited = (CFG.inherited || []).indexOf(slot) >= 0;
    return '' +
      '<div class="p-3 border-bottom bind-row" data-slot="' + esc(slot) + '">' +
        '<div class="row g-2 align-items-center">' +
          '<div class="col-md-3"><span class="small fw-bold">' + esc(slot) + "</span>" +
            '<div class="text-muted" style="font-size:.72rem">' + esc(spec.dtype) +
            (spec.nullable ? ", nullable" : "") +
            (isLabel ? ' &middot; <span class="evidence-bad">label</span>' : "") +
            (inherited ? " &middot; inherited" : "") + "</div></div>" +
          '<div class="col-md-4"><select class="form-select form-select-sm b-feature" ' +
            'aria-label="Feature filling ' + esc(slot) + '">' +
            featureOptions(bound.feature) + "</select></div>" +
          '<div class="col-md-5"><select class="form-select form-select-sm b-view" ' +
            'aria-label="View version for ' + esc(slot) + '">' +
            viewOptions(bound.feature, bound.view, bound.view_version) +
            "</select>" +
            '<div class="text-muted b-note" style="font-size:.72rem">' +
              esc(supplyNote(bound.feature)) + "</div></div>" +
        "</div></div>";
  }

  function draw() {
    if (!SLOTS.length) {
      $("#bind-rows").html('<p class="p-3 mb-0 text-muted small">This featureset ' +
        "resolves to no slots, which is not a schema.</p>");
      return;
    }
    $("#bind-rows").html(SLOTS.map(row).join(""));
    leakage();
  }

  function collect() {
    var bindings = {};
    $(".bind-row").each(function () {
      // Read back as a string: jQuery's `.data()` coerces "12" to a number,
      // and a slot may legitimately be named that.
      var slot = String($(this).data("slot"));
      var feature = $(this).find(".b-feature").val();
      if (!feature) { return; }               // left unfilled, and refused as such
      var pin = $(this).find(".b-view").val();
      if (!pin) { bindings[slot] = feature; return; }
      var at = pin.lastIndexOf("@");
      bindings[slot] = { feature: feature, view: pin.slice(0, at),
                         view_version: parseInt(pin.slice(at + 1), 10) };
    });
    return bindings;
  }

  function refusal(where, xhr) {
    var body = (xhr.responseJSON && xhr.responseJSON.detail) || xhr.responseJSON || {};
    if (typeof body === "string") { body = { detail: body }; }
    var err = body.error || (xhr.responseJSON || {}).error || "refused";
    var detail = body.detail || xhr.statusText;
    var fix = body.remediation || (xhr.responseJSON || {}).remediation || "";
    $(where).html('<span class="evidence-bad">' + esc(err) + "</span> — " +
      esc(String(detail)) +
      (fix ? '<div class="text-muted mt-1">' + esc(String(fix)) + "</div>" : "") +
      '<div class="text-muted mt-1">Nothing was recorded: the schema check, the ' +
      "leakage check and every pin run before a row is written.</div>");
  }

  // --------------------------------------------------------------- leakage
  function leakage() {
    if (!CFG.labelSlot) { return; }
    // Filtered rather than selected by attribute: a slot name is whatever
    // somebody declared, and a quote in one would break the selector.
    var $row = $(".bind-row").filter(function () {
      return String($(this).data("slot")) === CFG.labelSlot;
    });
    var feature = $row.find(".b-feature").val();
    if (!feature) {
      $("#bind-leakage").html("Bind the label slot to see it.");
      return;
    }
    $.getJSON("/api/v1/derived-features/" + encodeURIComponent(feature) + "/lineage")
      .done(function (r) {
        var reads = r.depended_on_by || [];
        if (!reads.length) {
          $("#bind-leakage").html('<span class="evidence-ok">nothing in the ' +
            "catalogue is computed from " + esc(feature) + "</span> — so the " +
            "leakage check has nothing to refuse today. It still runs on every " +
            "publish, because a derivation added tomorrow would.");
          return;
        }
        $("#bind-leakage").html('<span class="evidence-bad">these are computed ' +
          "from " + esc(feature) + "</span> and will be refused in any other " +
          "slot, however many hops away: <code>" + esc(reads.join(", ")) +
          "</code><div class='text-muted mt-1'>Derive from a value known before " +
          "the outcome, or declare it an output rather than a feature.</div>");
      })
      .fail(function (xhr) { refusal("#bind-leakage", xhr); });
  }

  // ---------------------------------------------------------------- events
  $(document).on("change", ".b-feature", function () {
    var $row = $(this).closest(".bind-row");
    var feature = $(this).val();
    $row.find(".b-view").html(viewOptions(feature));
    $row.find(".b-note").text(supplyNote(feature));
    if (String($row.data("slot")) === CFG.labelSlot) { leakage(); }
  });

  $("#bind-publish").on("click", function () {
    var bindings = collect();
    $.ajax({ url: "/api/v1/featuresets/" + encodeURIComponent(CFG.name) + "/versions",
             method: "POST", contentType: "application/json",
             data: JSON.stringify({ bindings: bindings, note: $("#bind-note").val() || "" }) })
      .done(function (r) { published(r); })
      .fail(function (xhr) { refusal("#bind-result", xhr); });
  });

  function published(version) {
    $("#bind-result").html('<span class="evidence-ok">published v' + version.version +
      "</span> — reading the plan back…");
    $.getJSON("/api/v1/featuresets/" + encodeURIComponent(CFG.name) +
              "/versions/" + version.version)
      .done(function (plan) {
        var html = '<span class="evidence-ok">published v' + plan.version +
          "</span> — this is what got pinned:" +
          "<table class='table maya mt-2 mb-1'><thead><tr><th>Slot</th>" +
          "<th>Feature</th><th>Namespace</th><th>Pinned at</th></tr></thead><tbody>";
        (plan.slots || []).forEach(function (s) {
          html += "<tr><td class='small'>" + esc(s.slot) + "</td><td class='small'>" +
                  esc(s.feature) + "</td><td class='small'><code style='font-size:.72rem'>" +
                  esc(s.namespace) + "</code></td><td class='small'>delta v" +
                  esc(s.delta_version) + "</td></tr>";
        });
        html += "</tbody></table>" +
          "<div class='text-muted'>The Delta version, not just the path: a path " +
          "is mutable, and this is what makes <em>same featureset version, same " +
          "bytes</em> true rather than true-until-somebody-writes-again. " +
          "<a href='/featureset/" + encodeURIComponent(CFG.name) + "/plan/" +
          plan.version + "'>The whole plan</a> &middot; " +
          "<a href='/featureset/" + encodeURIComponent(CFG.name) +
          "/assemble?version=" + plan.version + "'>assemble a training set</a>.</div>";
        $("#bind-result").html(html);
      })
      .fail(function (xhr) { refusal("#bind-result", xhr); });
  }

  $("#bind-roll").on("click", function () {
    $.ajax({ url: "/api/v1/featuresets/" + encodeURIComponent(CFG.name) + "/roll-forward",
             method: "POST" })
      .done(function (r) {
        var moved = (r.moved || []).map(function (m) {
          return esc(m.slot) + ": " + esc(m.was || "(new)") + " &rarr; " + esc(m.now);
        }).join("<br>");
        $("#bind-result").html('<span class="evidence-ok">rolled forward to v' +
          r.version + "</span> — " +
          (moved ? "what moved:<div class='mt-1'>" + moved + "</div>"
                 : "nothing moved; every view was already at its newest version.") +
          "<div class='text-muted mt-1'>The earlier version still reads exactly " +
          "the bytes it pinned. Taking up new data is a deliberate act with a " +
          "diff, not something that happens to somebody who already trained." +
          "</div><div class='mt-1'><a href='/featureset/" +
          encodeURIComponent(CFG.name) + "/plan/" + r.version + "'>the new plan</a></div>");
      })
      .fail(function (xhr) { refusal("#bind-result", xhr); });
  });

  $("#bind-seal").on("click", function () {
    if (!window.confirm("Seal this featureset? It becomes final and takes no " +
        "further versions and no change of policy. It can still be composed " +
        "from, assembled from and named by a warrant — that is what sealing is " +
        "for. Breaking a seal needs an administrator and is recorded.")) { return; }
    $.ajax({ url: "/api/v1/featuresets/" + encodeURIComponent(CFG.name) + "/seal",
             method: "POST", contentType: "application/json",
             data: JSON.stringify({ note: $("#bind-note").val() || "" }) })
      .done(function () { window.location.reload(); })
      .fail(function (xhr) { refusal("#bind-result", xhr); });
  });

  draw();
}());
