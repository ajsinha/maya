/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * The rule-set editor.
 *
 * It decides NOTHING. Every question about whether a rule set is valid — can
 * this rule fire, do these two disagree, does this field exist — is answered by
 * POST /rulesets/check, and the screen renders the answer. A client that
 * re-implemented any of that would be a second implementation of a governance
 * rule, and a second implementation disagrees with the first eventually, in the
 * direction of permitting more, because that is the direction in which nobody
 * files a bug.
 *
 * So the publish button is enabled by the server saying the document is valid,
 * never by anything computed here.
 *
 * The row editor covers the common shape: a list of rules, each an `all` or
 * `any` of field tests. Anything more nested is edited as the document, which
 * the rows re-read from — one representation, two ways in.
 */
(function () {
  "use strict";

  var CFG = window.MAYA_RULES || {};
  var doc = CFG.document && CFG.document.rules ? CFG.document
          : { rules: [], otherwise: {}, note: "" };
  var checkTimer = null;

  var ORDERED = {};
  (CFG.inputs || []).forEach(function (f) { ORDERED[f.name] = !!f.ordered; });

  // ------------------------------------------------------------------ atoms
  function fieldOptions(selected) {
    return (CFG.inputs || []).map(function (f) {
      return '<option value="' + f.name + '"' +
             (f.name === selected ? " selected" : "") + ">" + f.name + "</option>";
    }).join("");
  }

  function opOptions(selected, field) {
    return (CFG.vocabulary.operators || []).map(function (o) {
      // Offered, not enforced: an ordered comparison on a categorical field is
      // refused by the server with a message that explains it, and hiding the
      // option would teach nobody why.
      var warn = o.needs_ordered_field && !ORDERED[field] ? " ⚠" : "";
      return '<option value="' + o.op + '"' +
             (o.op === selected ? " selected" : "") + ">" +
             o.op + " — " + o.means + warn + "</option>";
    }).join("");
  }

  function atomRow(atom, ruleIndex, atomIndex) {
    var nullary = atom.op === "is_null" || atom.op === "not_null";
    return '' +
      '<div class="row g-1 mb-1 atom" data-rule="' + ruleIndex + '" data-atom="' + atomIndex + '">' +
        '<div class="col-4"><select class="form-select form-select-sm a-field">' +
          fieldOptions(atom.field) + '</select></div>' +
        '<div class="col-4"><select class="form-select form-select-sm a-op">' +
          opOptions(atom.op, atom.field) + '</select></div>' +
        '<div class="col-3"><input class="form-control form-control-sm a-value" ' +
          'value="' + (nullary ? "" : jsonish(atom.value)) + '"' +
          (nullary ? " disabled placeholder=\"(none)\"" : "") + '></div>' +
        '<div class="col-1"><button class="btn btn-sm btn-outline-secondary w-100 a-del" ' +
          'title="remove this test">&times;</button></div>' +
      '</div>';
  }

  function ruleCard(rule, index) {
    var group = rule.when && rule.when.any ? "any" : "all";
    var atoms = (rule.when && (rule.when.all || rule.when.any)) ||
                (rule.when && rule.when.field ? [rule.when] : []);
    var nested = atoms.some(function (a) { return !a.field; });
    return '' +
      '<div class="p-3 border-bottom rule-card" data-rule="' + index + '">' +
        '<div class="row g-1 mb-2">' +
          '<div class="col-4"><input class="form-control form-control-sm r-id" ' +
            'value="' + esc(rule.id || "") + '" placeholder="rule id"></div>' +
          '<div class="col-8"><input class="form-control form-control-sm r-because" ' +
            'value="' + esc(rule.because || "") + '" placeholder="why this rule exists — the policy, the limit, the regulation"></div>' +
        '</div>' +
        (nested
          ? '<p class="small text-muted mb-2">This rule&rsquo;s condition is nested; edit it in the document below.</p>'
          : '<div class="mb-2"><span class="small text-muted me-2">match</span>' +
              '<select class="form-select form-select-sm d-inline-block w-auto r-group">' +
                '<option value="all"' + (group === "all" ? " selected" : "") + '>all of</option>' +
                '<option value="any"' + (group === "any" ? " selected" : "") + '>any of</option>' +
              '</select></div>' +
            '<div class="atoms">' +
              atoms.map(function (a, i) { return atomRow(a, index, i); }).join("") +
            '</div>' +
            '<button class="btn btn-sm btn-outline-secondary r-add-atom">Add a test</button>') +
        '<div class="mt-2"><span class="small text-muted me-2">then</span>' +
          '<input class="form-control form-control-sm d-inline-block w-auto r-then" ' +
            'value="' + esc(JSON.stringify(rule.then || {})) + '" style="min-width:16rem"></div>' +
        '<button class="btn btn-sm btn-outline-danger mt-2 r-del">Remove this rule</button>' +
      '</div>';
  }

  // -------------------------------------------------------------- rendering
  function draw() {
    $("#rules").html(doc.rules.map(ruleCard).join("") ||
      '<p class="p-3 mb-0 text-muted small">No rules yet.</p>');
    $("#otherwise").html(
      '<input id="otherwise-then" class="form-control form-control-sm" value="' +
      esc(JSON.stringify(doc.otherwise || {})) + '">');
    $("#doc").val(JSON.stringify(doc, null, 2));
    scheduleCheck();
  }

  function scheduleCheck() {
    if (checkTimer) { window.clearTimeout(checkTimer); }
    checkTimer = window.setTimeout(check, 250);
  }

  function check() {
    $.ajax({
      url: "/api/v1/rulesets/check", method: "POST",
      contentType: "application/json",
      data: JSON.stringify({ urn: CFG.urn, semver: CFG.semver, document: doc })
    }).done(function (r) {
      $("#verdict").html('<span class="evidence-ok">valid</span> — ' +
        r.rules + " rules over " + (r.reads || []).join(", "));
      $("#english").html((r.explanation || []).map(function (line) {
        return "<li>" + esc(line) + "</li>";
      }).join(""));
      $("#publish").prop("disabled", false);
    }).fail(function (xhr) {
      var body = (xhr.responseJSON && xhr.responseJSON.detail) || {};
      var err = body.error || (xhr.responseJSON || {}).error || "refused";
      var detail = body.detail || (xhr.responseJSON || {}).detail || xhr.statusText;
      var fix = body.remediation || (xhr.responseJSON || {}).remediation || "";
      $("#verdict").html('<span class="evidence-bad">' + esc(err) + "</span> — " +
        esc(String(detail)) +
        (fix ? '<div class="text-muted mt-1">' + esc(String(fix)) + "</div>" : ""));
      $("#english").empty();
      // Disabled by the SERVER's verdict, never by anything decided here.
      $("#publish").prop("disabled", true);
    });
  }

  // ------------------------------------------------------------- collecting
  function collect() {
    $(".rule-card").each(function () {
      var $card = $(this), index = +$card.data("rule"), rule = doc.rules[index];
      if (!rule) { return; }
      rule.id = $card.find(".r-id").val().trim();
      rule.because = $card.find(".r-because").val();
      rule.then = parseOr($card.find(".r-then").val(), rule.then);
      var $atoms = $card.find(".atom");
      if (!$atoms.length) { return; }              // nested: left as it is
      var atoms = [];
      $atoms.each(function () {
        var $a = $(this), op = $a.find(".a-op").val();
        var atom = { field: $a.find(".a-field").val(), op: op };
        if (op !== "is_null" && op !== "not_null") {
          atom.value = parseValue($a.find(".a-value").val());
        }
        atoms.push(atom);
      });
      var group = $card.find(".r-group").val();
      rule.when = atoms.length === 1 && group === "all"
        ? atoms[0] : (group === "any" ? { any: atoms } : { all: atoms });
    });
    doc.otherwise = parseOr($("#otherwise-then").val(), doc.otherwise);
  }

  function parseValue(text) {
    var trimmed = (text || "").trim();
    if (trimmed === "") { return ""; }
    try { return JSON.parse(trimmed); } catch (e) { return trimmed; }
  }

  function parseOr(text, fallback) {
    try { return JSON.parse(text); } catch (e) { return fallback; }
  }

  function jsonish(v) {
    if (v === undefined || v === null) { return ""; }
    return esc(typeof v === "string" ? v : JSON.stringify(v));
  }

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
                    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ----------------------------------------------------------------- events
  $(document).on("input change", ".rule-card input, .rule-card select, #otherwise-then",
    function () { collect(); $("#doc").val(JSON.stringify(doc, null, 2)); scheduleCheck(); });

  $(document).on("change", ".a-op", function () { collect(); draw(); });

  $(document).on("click", ".a-del", function () {
    var $card = $(this).closest(".rule-card"), index = +$card.data("rule");
    var at = +$(this).closest(".atom").data("atom");
    var when = doc.rules[index].when;
    var list = when.all || when.any;
    if (list) { list.splice(at, 1); }
    collect(); draw();
  });

  $(document).on("click", ".r-add-atom", function () {
    var index = +$(this).closest(".rule-card").data("rule");
    var first = (CFG.inputs || [])[0] || {};
    var when = doc.rules[index].when || {};
    var list = when.all || when.any;
    if (!list) { list = when.field ? [when] : []; doc.rules[index].when = { all: list }; }
    list.push({ field: first.name, op: "eq", value: "" });
    draw();
  });

  $(document).on("click", ".r-del", function () {
    doc.rules.splice(+$(this).closest(".rule-card").data("rule"), 1);
    draw();
  });

  $("#add-rule").on("click", function () {
    var first = (CFG.inputs || [])[0] || {};
    var out = {};
    if ((CFG.outputs || []).length) { out[CFG.outputs[0].name] = ""; }
    doc.rules.push({ id: "rule_" + (doc.rules.length + 1),
                     when: { all: [{ field: first.name, op: "eq", value: "" }] },
                     then: out, because: "" });
    draw();
  });

  $("#from-json").on("click", function () {
    try {
      doc = JSON.parse($("#doc").val());
      draw();
    } catch (e) {
      $("#verdict").html('<span class="evidence-bad">that is not JSON</span> — ' +
                         esc(e.message));
    }
  });

  $("#trial").on("click", function () {
    var rows = [];
    var bad = null;
    $("#rows").val().split("\n").forEach(function (line, i) {
      if (!line.trim()) { return; }
      try { rows.push(JSON.parse(line)); }
      catch (e) { bad = "line " + (i + 1) + " is not JSON"; }
    });
    if (bad) { $("#trial-out").html('<span class="evidence-bad">' + esc(bad) + "</span>"); return; }
    $.ajax({
      url: "/api/v1/rulesets/trial", method: "POST",
      contentType: "application/json",
      data: JSON.stringify({ urn: CFG.urn, semver: CFG.semver,
                             document: doc, rows: rows })
    }).done(function (r) {
      var html = "<table class='table maya mb-1'><thead><tr><th>row</th>" +
                 "<th>outcome</th><th>rule</th></tr></thead><tbody>";
      (r.outcomes || []).forEach(function (o) {
        var decision = o.refused
          ? '<span class="evidence-bad">' + esc(o.refused) + "</span>"
          : esc(JSON.stringify(pick(o)));
        html += "<tr><td>" + o.row + "</td><td>" + decision + "</td><td>" +
                esc(o.matched_rule || "(otherwise)") + "</td></tr>";
      });
      html += "</tbody></table>";
      if ((r.never_fired || []).length) {
        html += '<p class="mb-0 text-muted">Fired on no row: <code>' +
                esc(r.never_fired.join(", ")) + "</code>. Not necessarily wrong — " +
                "but worth a look before this is approved.</p>";
      }
      $("#trial-out").html(html);
    }).fail(function (xhr) {
      var b = (xhr.responseJSON && xhr.responseJSON.detail) || xhr.responseJSON || {};
      $("#trial-out").html('<span class="evidence-bad">' +
        esc(b.error || "refused") + "</span> — " + esc(String(b.detail || "")));
    });
  });

  function pick(outcome) {
    var out = {};
    Object.keys(outcome).forEach(function (k) {
      if (k !== "row" && k !== "matched_rule" && k !== "because") { out[k] = outcome[k]; }
    });
    return out;
  }

  $("#publish").on("click", function () {
    var name = $("#name").val().trim();
    if (!name) { $("#publish-out").html('<span class="evidence-bad">give it a name</span>'); return; }
    $.ajax({
      url: "/api/v1/rulesets", method: "POST", contentType: "application/json",
      data: JSON.stringify({ urn: CFG.urn, semver: CFG.semver, name: name,
                             document: doc, note: $("#note").val() })
    }).done(function (r) {
      $("#publish-out").html('<span class="evidence-ok">recorded as ' + esc(r.name) +
        "</span> — it is <code>" + esc(r.state) + "</code> and needs somebody " +
        "other than you to approve it. <a href='/rulesets/" + esc(r.id) + "'>Read it back</a>");
      $("#publish").prop("disabled", true);
    }).fail(function (xhr) {
      var b = (xhr.responseJSON && xhr.responseJSON.detail) || xhr.responseJSON || {};
      $("#publish-out").html('<span class="evidence-bad">' + esc(b.error || "refused") +
        "</span> — " + esc(String(b.detail || "")));
    });
  });

  draw();
}());
