/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * The warrant authoring screen.
 *
 * It posts and it renders. It decides nothing: no rule about whether an act is
 * permitted is evaluated here, and every red box below is the platform's own
 * refusal with the platform's own remediation. The one arithmetic it does is on
 * numbers the API already sent — seconds until an expiry, days since a
 * calibration — because a reader should not have to subtract two epochs to find
 * out they are about to run last quarter's fit.
 *
 * The CSRF token is attached by csrf.js for every request from this file.
 */
(function () {
  "use strict";

  var root = document.getElementById("warrant-root");
  if (!root) { return; }                       // no model chosen; only the laws
  var URN = root.getAttribute("data-urn");
  var NAME = root.getAttribute("data-name");
  var SECTIONS = JSON.parse(
    (document.getElementById("warrant-sections") || {}).textContent || "{}");
  var last = null;                             // the last document resolved

  // ---------------------------------------------------------------- helpers
  function esc(text) {
    return String(text === null || text === undefined ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function refused(x) {
    /* The API's refusal, whole: the code, what it says, and what to do.
     * `problems` appears only on the grammar validator, which reports every
     * problem at once rather than the first. */
    var e = (x && x.responseJSON) || {};
    var body = e.detail || (x && x.statusText) || String(x);
    var html = '<div class="border rounded p-2" style="border-color:#A51C30!important">' +
      '<span class="evidence-bad">Refused</span> ' +
      (e.error ? '<code>' + esc(e.error) + '</code> ' : "") +
      "&mdash; " + esc(body);
    if (e.remediation) {
      html += '<div class="text-muted mt-1">' + esc(e.remediation) + "</div>";
    }
    return html + "</div>";
  }

  function ok(text) {
    return '<span class="evidence-ok">' + esc(text) + "</span>";
  }

  function post(url, body) {
    return $.ajax({url: url, method: "POST", contentType: "application/json",
                   data: JSON.stringify(body)});
  }

  function fields(form) {
    return Object.fromEntries(new FormData(form));
  }

  function parsed(text, what, where) {
    /* JSON or a message. Never a silent default: a form that dropped an
     * unparseable block would record an object its author believed they had
     * filled in. */
    if (!text || !String(text).trim()) { return {}; }
    try {
      return JSON.parse(text);
    } catch (err) {
      $(where).html('<div class="evidence-bad">' + esc(what) +
        " is not valid JSON &mdash; " + esc(err.message) + "</div>");
      return null;
    }
  }

  function epoch(value) {
    /* A date field as seconds. Read as UTC midnight, deliberately: a training
     * window that shifted by the reader's timezone would be a different window
     * on two people's screens. */
    if (!value) { return null; }
    return Date.parse(value + "T00:00:00Z") / 1000;
  }

  function stamp(seconds) {
    if (seconds === null || seconds === undefined) { return "—"; }
    return new Date(Number(seconds) * 1000).toISOString().replace(".000Z", "Z");
  }

  function days(seconds) {
    return (Number(seconds) / 86400).toFixed(1) + " day(s)";
  }

  function value(v) {
    if (v === null || v === undefined) { return '<span class="text-muted">—</span>'; }
    if (typeof v === "object") {
      return '<pre class="mono mb-0" style="white-space:pre-wrap">' +
             esc(JSON.stringify(v, null, 2)) + "</pre>";
    }
    return esc(v);
  }

  function terms(pairs) {
    var html = '<dl class="maya-terms border rounded">';
    pairs.forEach(function (pair) {
      html += "<div><dt>" + esc(pair[0]) + "</dt><dd>" + pair[1] + "</dd></div>";
    });
    return html + "</dl>";
  }

  // --------------------------------------------------- rendering a warrant
  function pointOfP(doc) {
    /* The one thing a reader most often gets wrong: which numbers this run is
     * at. The age is the API's own `age_seconds`, not a subtraction invented
     * here. */
    var p = doc.parameters || {};
    var s = p.source || {};
    var rows = [["kind", esc(p.kind)], ["binding", esc(s.binding || "—")]];
    if (s.parameter_set) {
      rows.push(["parameter set", esc(s.name || "") + " v" + esc(s.version) +
                 ' <span class="mono">' + esc(s.parameter_set) + "</span>"]);
      rows.push(["digest", '<span class="mono">' + esc(s.digest) + "</span>"]);
    }
    if (s.uri) { rows.push(["artifact", '<span class="mono">' + esc(s.uri) + "</span>"]); }
    if (s.as_of !== undefined && s.as_of !== null) {
      rows.push(["calibrated as of", esc(stamp(s.as_of))]);
    }
    if (s.age_seconds !== undefined && s.age_seconds !== null) {
      rows.push(["which is", "<strong>" + esc(days(s.age_seconds)) +
                 "</strong> old at the moment this warrant was minted"]);
    }
    if (s.binding === "to_be_fitted") {
      rows.push(["note", "this warrant <em>produces</em> the parameter object; " +
                 "only a fit may leave the point of P unnamed"]);
    }
    return '<p class="kicker mb-1">THE POINT OF P THIS RUN IS AT</p>' + terms(rows);
  }

  function authority(doc) {
    var a = doc.authority || {};
    var r = a.revocation || {};
    return '<p class="kicker mb-1">AUTHORITY</p>' + terms([
      ["principal", esc(a.principal)],
      ["declared use", esc(a.declared_use)],
      ["environment", esc(a.environment)],
      ["granted at", esc(stamp(a.granted_at))],
      ["expires at", esc(stamp(a.expires_at)) + " &mdash; " +
        esc(Math.round((a.expires_at || 0) - (a.granted_at || 0))) + "s after issue"],
      ["grace", esc(a.grace_seconds) + "s of currency when MAYA is unreachable; " +
        "never an extension of ignorance about a withdrawal"],
      ["revocation", "epoch " + esc(r.epoch) + ", checking is " + esc(r.check)]
    ]);
  }

  function warrantHtml(doc) {
    var head = '<div class="d-flex flex-wrap gap-2 align-items-baseline mb-2">' +
      '<span class="evidence-ok">Signed</span>' +
      '<span class="chip">grammar v' + esc(doc.maya_warrant) + "</span>" +
      '<span class="chip mono">' + esc(doc.warrant_id) + "</span>" +
      '<span class="chip">' + esc((doc.operation || {}).verb) + "</span>" +
      '<span class="chip">' + esc((doc.subject || {}).version) + "</span>" +
      '<span class="chip">' + esc((doc.subject || {}).trainability_class) + "</span>" +
      "</div>";
    head += '<div class="row g-3 mb-2"><div class="col-lg-6">' + authority(doc) +
            '</div><div class="col-lg-6">' + pointOfP(doc) + "</div></div>";

    var order = Object.keys(SECTIONS);
    var body = "";
    order.forEach(function (key) {
      if (!(key in doc)) { return; }
      var section = doc[key];
      var inner = "";
      if (section && typeof section === "object" && !Array.isArray(section)) {
        Object.keys(section).forEach(function (field) {
          inner += "<div><dt>" + esc(field) + "</dt><dd>" +
                   value(section[field]) + "</dd></div>";
        });
        inner = '<dl class="maya-terms">' + inner + "</dl>";
      } else {
        inner = value(section);
      }
      body += '<div class="col-lg-6"><div class="card h-100">' +
        '<div class="card-header d-flex justify-content-between">' +
        "<span>" + esc(key) + "</span>" +
        '<span class="text-muted fw-normal" style="font-size:.72rem">' +
        esc(SECTIONS[key]) + "</span></div>" +
        '<div class="card-body py-2">' + inner + "</div></div></div>";
    });
    var missing = order.filter(function (k) { return !(k in doc); });
    if (missing.length) {
      body += '<div class="col-12"><div class="evidence-bad">Sections absent: ' +
        esc(missing.join(", ")) + " &mdash; an absent section is not an empty " +
        "one, and L-W0 refuses the document.</div></div>";
    }
    return head + '<div class="row g-3">' + body + "</div>";
  }

  function showWarrant(doc, where) {
    last = doc;
    $(where).html(warrantHtml(doc));
    if (window.mayaEnhanceTables) { window.mayaEnhanceTables(); }
  }

  // ------------------------------------------------------------ the grant
  $("#issue-grant").on("submit", function (e) {
    e.preventDefault();
    var f = fields(this);
    post("/api/v1/warrants", {
      urn: f.urn, environment: f.environment, principal: f.principal,
      declared_use: f.declared_use
    }).done(function (grant) {
      $("#grant-result").html(
        ok("Issued") + " &mdash; " + esc(grant.principal) + " may " +
        esc(grant.declared_use) + " in " + esc(grant.environment) +
        ", for " + esc(grant.ttl_seconds) + "s at a time with " +
        esc(grant.grace_seconds) + "s of grace." +
        '<div class="text-muted">Grant id <span class="mono">' + esc(grant.id) +
        "</span> &mdash; this is the id parameters name when they come back. " +
        '<a href="/warrants?model=' + encodeURIComponent(NAME) +
        '">Reload</a> to see it in the table.</div>');
      $("#record-warrant").val(grant.id);
    }).fail(function (x) { $("#grant-result").html(refused(x)); });
  });

  $(".use-grant").on("click", function () {
    var d = $(this).data();
    $('input[name="principal"]').val(d.principal);
    $('input[name="declared_use"]').val(d.use);
    $('input[name="environment"]').val(d.environment);
    $("#record-warrant").val(d.grant);
  });

  function grantFor(principal, environment) {
    /* The grant a fit was resolved against, found among the rows the server
     * rendered. `find` on the server's own data, not a rule: the register
     * holds at most one grant per (model, environment, principal). */
    var found = null;
    $(".use-grant").each(function () {
      var d = $(this).data();
      if (d.principal === principal && d.environment === environment) {
        found = String(d.grant);
      }
    });
    return found;
  }

  // ---------------------------------------------------------- the profiles
  $("#new-profile").on("submit", function (e) {
    e.preventDefault();
    var f = fields(this);
    var when = parsed(f.when, "The predicate", "#profile-result");
    var defaults = parsed(f.defaults, "The defaults", "#profile-result");
    if (when === null || defaults === null) { return; }
    post("/api/v1/warrant-profiles", {
      name: f.name, when: when, defaults: defaults, note: f.note || ""
    }).done(function () { location.reload(); })
      .fail(function (x) { $("#profile-result").html(refused(x)); });
  });

  $(".retire-profile").on("click", function () {
    var name = $(this).data("name");
    post("/api/v1/warrant-profiles/" + encodeURIComponent(name) + "/retire", {})
      .done(function () { location.reload(); })
      .fail(function (x) { $("#profile-result").html(refused(x)); });
  });

  $("#preview-profile").on("submit", function (e) {
    e.preventDefault();
    var f = fields(this);
    var request = parsed(f.request, "The request", "#preview-result");
    if (request === null) { return; }
    // The bare NAME, not the urn. `/warrant-profiles/preview` names its field
    // `urn` and then prefixes what it is given, so a real urn arrives as
    // `maya://model/maya://model/…` and is refused as an unregistered model.
    // Sending what the endpoint means rather than what it says.
    var body = {urn: NAME, environment: f.environment, request: request};
    if (f.semver) { body.semver = f.semver; }
    post("/api/v1/warrant-profiles/preview", body).done(function (out) {
      var html = "<div>" + ok(out.detail) + "</div>";
      html += '<table class="table table-sm maya mt-2"><thead><tr>' +
        "<th>Key</th><th>Filled from</th></tr></thead><tbody>";
      var applied = out.applied || {};
      var keys = Object.keys(applied);
      if (!keys.length) {
        html += '<tr><td colspan="2" class="text-muted">Nothing was filled in. ' +
          "Either no profile matched, or every value was already yours &mdash; " +
          "a profile never overrides a caller.</td></tr>";
      }
      keys.forEach(function (key) {
        html += "<tr><td class='mono'>" + esc(key) + "</td><td class='mono'>" +
          esc(applied[key]) + "</td></tr>";
      });
      html += "</tbody></table>";
      html += '<p class="kicker mb-1">THE FACTS IT WAS SELECTED ON</p>' +
        value(out.facts);
      html += '<p class="kicker mt-2 mb-1">THE REQUEST AS IT WOULD STAND</p>' +
        value(out.request);
      $("#preview-result").html(html);
      if (window.mayaEnhanceTables) { window.mayaEnhanceTables(); }
    }).fail(function (x) { $("#preview-result").html(refused(x)); });
  });

  // ------------------------------------------------------ score and fit
  $("#resolve-warrant").on("submit", function (e) {
    e.preventDefault();
    var f = fields(this);
    post("/api/v1/resolve?verb=" + encodeURIComponent(f.verb), {
      urn: f.urn, environment: f.environment, principal: f.principal,
      declared_use: f.declared_use
    }).done(function (doc) { showWarrant(doc, "#warrant-result"); })
      .fail(function (x) { $("#warrant-result").html(refused(x)); });
  });

  function versionsFor(select) {
    var listed = String($(select).find("option:selected").data("versions") || "");
    var options = "";
    listed.split(",").filter(Boolean).forEach(function (v) {
      options += "<option>" + esc(v) + "</option>";
    });
    $("#fit-version").html(options ||
      '<option value="">no published version</option>');
  }
  if ($("#fit-featureset").length) {
    $("#fit-featureset").on("change", function () { versionsFor(this); }).trigger("change");
  }

  $("#resolve-fit").on("submit", function (e) {
    e.preventDefault();
    var f = fields(this);
    post("/api/v1/fit-warrants", {
      urn: f.urn, environment: f.environment, principal: f.principal,
      declared_use: f.declared_use, featureset: f.featureset,
      featureset_version: Number(f.featureset_version),
      window: {from: epoch(f.window_from), to: epoch(f.window_to)},
      as_of: epoch(f.as_of)
    }).done(function (doc) {
      showWarrant(doc, "#fit-result");
      // Carry the binding across to the form that takes delivery, so the two
      // halves of the round trip cannot drift apart by a typo. The warrant id
      // that goes back is the GRANT's — the descriptor's is minted per request
      // and never stored — so it is looked up from the rows on this page.
      var input = ((doc.data || {}).inputs || [])[0] || {};
      $("#record-featureset").val(input.featureset || "");
      $("#record-featureset-version").val(input.version || "");
      $("#record-as-of").val(f.as_of);
      $('#record-parameters input[name="semver"]').val((doc.subject || {}).version);
      var grant = grantFor(f.principal, f.environment);
      if (grant) { $("#record-warrant").val(grant); }
      $("#fit-result").prepend(
        '<div class="state-note mb-2">An engine now trains from ' +
        esc(input.featureset) + "@v" + esc(input.version) +
        " and posts what it produced to <code>/api/v1/parameters</code>, naming " +
        (grant ? "grant <span class='mono'>" + esc(grant) + "</span>"
               : "the <strong>grant</strong> (not this descriptor's id)") +
        ". The form to the right is filled in with what it would send.</div>");
    }).fail(function (x) { $("#fit-result").html(refused(x)); });
  });

  // ------------------------------------------- the numbers come back
  $("#record-parameters").on("submit", function (e) {
    e.preventDefault();
    var f = fields(this);
    var values = parsed(f.values, "The values", "#record-result");
    var diagnostics = parsed(f.diagnostics, "The diagnostics", "#record-result");
    if (values === null || diagnostics === null) { return; }
    var body = {urn: URN, semver: f.semver, name: f.name, kind: f.kind,
                values: values, provenance: f.provenance,
                diagnostics: diagnostics};
    if (f.warrant_id) { body.warrant_id = f.warrant_id; }
    if (f.featureset) { body.featureset = f.featureset; }
    if (f.featureset_version) {
      body.featureset_version = Number(f.featureset_version);
    }
    if (f.as_of) { body.as_of = epoch(f.as_of); }
    post("/api/v1/parameters", body).done(function (row) {
      $("#record-result").html(
        ok("Recorded") + " &mdash; " + esc(row.name) + " v" + esc(row.version) +
        ", state <strong>" + esc(row.state) + "</strong>." +
        '<div class="text-muted">It changes what the model does, so somebody ' +
        "other than " + esc(row.created_by) + " has to approve it before a " +
        "warrant will name it. " +
        '<a href="/warrants?model=' + encodeURIComponent(NAME) +
        '">Reload</a> to see it below.</div>');
    }).fail(function (x) { $("#record-result").html(refused(x)); });
  });

  $(".review-set").on("click", function () {
    var id = $(this).data("set");
    var accept = String($(this).data("accept")) === "1";
    post("/api/v1/parameter-sets/" + encodeURIComponent(id) + "/review",
         {accept: accept, note: accept ? "approved from the warrant screen"
                                       : "rejected from the warrant screen"})
      .done(function () { location.reload(); })
      .fail(function (x) { $("#review-result").html(refused(x)); });
  });

  // -------------------------------------------------------- revocation
  $("#revoke-warrant").on("submit", function (e) {
    e.preventDefault();
    var f = fields(this);
    post("/api/v1/warrants/revoke", {urn: f.urn, reason: f.reason})
      .done(function (out) {
        $("#revoke-result").html(
          ok(out.revoked + " grant(s) withdrawn") + " &mdash; the epoch is now " +
          esc(out.epoch) + '. <div class="text-muted">Descriptors already out ' +
          "carry a lower epoch and are stale; grace does not extend past a " +
          "withdrawal a consumer has been told about. " +
          '<a href="/warrants?model=' + encodeURIComponent(NAME) +
          '">Reload</a>.</div>');
      }).fail(function (x) { $("#revoke-result").html(refused(x)); });
  });

  // -------------------------------------------------- boundary violations
  $("#execute-warrant").on("submit", function (e) {
    e.preventDefault();
    var f = fields(this);
    var inputs = parsed(f.inputs, "The inputs", "#execute-result");
    if (inputs === null) { return; }
    post("/api/v1/execute", {
      urn: f.urn, environment: f.environment, principal: f.principal,
      declared_use: f.declared_use, inputs: inputs
    }).done(function (out) {
      $("#execute-result").html(terms([
        ["prediction", value(out.prediction)],
        ["within the boundary", out.boundary_ok ? ok("yes")
          : '<span class="evidence-bad">no</span>'],
        ["violations", value(out.boundary_violations)],
        ["latency", esc(out.latency_ms) + " ms"],
        ["descriptor", '<span class="mono">' + esc(out.descriptor_id) + "</span>"]
      ]));
    }).fail(function (x) { $("#execute-result").html(refused(x)); });
  });

  // ------------------------------------------------------ the grammar
  $("#check-warrant").on("submit", function (e) {
    e.preventDefault();
    var document_ = parsed(fields(this).document, "The document", "#check-result");
    if (document_ === null) { return; }
    post("/api/v1/grammar/validate", document_).done(function (report) {
      var html = report.valid
        ? "<div>" + ok(report.detail) + "</div>"
        : '<div class="evidence-bad">' + esc(report.problem_count) +
          " problem(s), all of them, not just the first.</div>";
      if (!report.valid) {
        html += '<table class="table table-sm maya mt-2"><thead><tr>' +
          "<th>Law</th><th>Path</th><th>What is wrong</th><th>What to do</th>" +
          "</tr></thead><tbody>";
        (report.problems || []).forEach(function (p) {
          html += "<tr><td class='mono'>" + esc(p.law) + "</td>" +
            "<td class='mono'>" + esc(p.path) + "</td>" +
            "<td>" + esc(p.detail) + "</td>" +
            "<td class='text-muted'>" + esc(p.remediation) + "</td></tr>";
        });
        html += "</tbody></table>";
      }
      $("#check-result").html(html);
      if (window.mayaEnhanceTables) { window.mayaEnhanceTables(); }
    }).fail(function (x) { $("#check-result").html(refused(x)); });
  });

  $("#load-last").on("click", function () {
    if (!last) {
      $("#check-result").html('<div class="text-muted">Resolve a warrant first, ' +
        "then load it here and break it to see which law objects.</div>");
      return;
    }
    $('#check-warrant textarea[name="document"]').val(JSON.stringify(last, null, 2));
  });
}());
