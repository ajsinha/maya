/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * The feature authoring screens: define, load, ask, and read back.
 *
 * They decide NOTHING. Every question about whether a definition is sound,
 * whether a row is admissible, whether a fill rule reaches into the future or
 * whether a person may act is answered by the API and rendered here. A client
 * that re-implemented any of it would be a second implementation of a
 * governance rule, and a second implementation disagrees with the first
 * eventually, in the direction of permitting more — because that is the
 * direction in which nobody files a bug.
 *
 * So a Define button is enabled by the server saying the draft is sound, and
 * disabled again the moment anything changes. The one thing this file decides
 * is which endpoint to call, which is not a governance question.
 *
 * The CSRF token is attached by csrf.js, for every jQuery and fetch call here.
 * Nothing below reimplements it.
 */
(function () {
  "use strict";

  var CFG = window.MAYA_FEATURE_AUTHOR || {};
  var CLOCKS = CFG.clocks || {entity: "entity_id", valid_time: "event_ts",
                              ingest_time: "ingest_ts"};
  var API = "/api/v1";

  // ------------------------------------------------------------------ atoms
  function esc(s) {
    return String(s === undefined || s === null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function num(value) {
    return (value === undefined || value === null || value === "") ? null
      : Number(value);
  }

  /* A refusal, in full: the code, what it says, and what to do about it.
   * Never summarised — the remediation is the half a caller can act on, and a
   * screen that dropped it would turn an answer back into a 400. */
  function refusal(xhr) {
    /* This one did `JSON.stringify(detail)` for a non-string, which is better
       than "[object Object]" and still unreadable: a person met a raw pydantic
       error array where a sentence naming their field belongs. */
    var r = window.MAYA.refusal.read(xhr);
    return '<span class="evidence-bad">' + esc(r.code || "refused") + "</span>" +
      " &mdash; " + r.lines.map(esc).join("<br>") +
      (r.remediation
        ? '<div class="text-muted mt-1">' + esc(r.remediation) + "</div>" : "");
  }

  function lines(text) {
    var out = [], bad = null;
    (text || "").split("\n").forEach(function (line, i) {
      if (!line.trim()) { return; }
      try { out.push(JSON.parse(line)); }
      catch (e) { if (bad === null) { bad = "line " + (i + 1) + " is not JSON"; } }
    });
    if (bad) { throw new Error(bad); }
    return out;
  }

  function fields(form) {
    return Object.fromEntries(new FormData(form));
  }

  function commas(text) {
    return (text || "").split(",").map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length; });
  }

  function post(url, body) {
    return $.ajax({url: url, method: "POST", contentType: "application/json",
                   data: JSON.stringify(body)});
  }

  function table(headers, rows) {
    return "<table class='table maya mb-2 small'><thead><tr>" +
      headers.map(function (h) { return "<th>" + esc(h) + "</th>"; }).join("") +
      "</tr></thead><tbody>" +
      (rows.length ? rows.map(function (r) {
        return "<tr>" + r.map(function (c) { return "<td>" + c + "</td>"; }).join("") +
               "</tr>";
      }).join("")
        : "<tr><td colspan='" + headers.length +
          "' class='text-muted'>nothing to show</td></tr>") +
      "</tbody></table>";
  }

  function debounce(fn, wait) {
    var timer = null;
    return function () {
      if (timer) { window.clearTimeout(timer); }
      timer = window.setTimeout(fn, wait || 250);
    };
  }

  // ============================================================== define page
  function definePage() {
    var checks = {primitive: null, derived: null, composed: null};

    function primitiveDraft() {
      var f = fields(document.getElementById("primitive"));
      var draft = {kind: "primitive", name: f.name || "", entity: f.entity || "",
                   dtype: f.dtype, description: f.description || ""};
      if (f.shape) { draft.shape = f.shape; }
      if (f.components) { draft.components = commas(f.components); }
      if (f.defaults) {
        try { draft.defaults = JSON.parse(f.defaults); }
        catch (e) { return {error: "the default policy is not JSON — " + e.message}; }
      }
      return draft;
    }

    function derivedDraft() {
      var f = fields(document.getElementById("derived"));
      return {kind: "derived", name: f.name || "", dtype: f.dtype,
              description: f.description || "", expression: f.expression || "",
              evaluator: f.evaluator, on_error: f.on_error,
              inputs: f.evaluator === CFG.external ? commas(f.inputs) : []};
    }

    function composedDraft() {
      var f = fields(document.getElementById("composed"));
      var draft = {kind: "composed", name: f.name || "", entity: f.entity || "",
                   dtype: f.dtype, description: f.description || "",
                   composes: commas(f.composes)};
      if (f.operations) {
        try { draft.operations = JSON.parse(f.operations); }
        catch (e) { return {error: "the operations are not JSON — " + e.message}; }
      }
      return draft;
    }

    function verdictOf(which, draft) {
      var $out = $("#" + which + "-verdict"), $go = $("#" + which + "-submit");
      $go.prop("disabled", true);
      if (draft.error) {
        $out.html('<span class="evidence-bad">' + esc(draft.error) + "</span>");
        return;
      }
      if (!draft.name) { $out.empty(); return; }
      checks[which] = draft;
      post(API + "/features/check", draft).done(function (r) {
        if (checks[which] !== draft) { return; }   // a later keystroke won
        $out.html(renderVerdict(r));
        // Enabled by the SERVER's verdict, never by anything decided here.
        $go.prop("disabled", false);
      }).fail(function (xhr) {
        if (checks[which] !== draft) { return; }
        $out.html(refusal(xhr));
        $go.prop("disabled", true);
        if (which === "derived") { $("#meet").html(""); }
      });
    }

    function renderVerdict(r) {
      var html = '<span class="evidence-ok">the platform accepts this draft</span>' +
                 " &mdash; " + esc(r.detail);
      if (r.kind === "composed") {
        html += '<div class="mt-2">' +
          table(["Component", "Came from", "Overrode"],
                (r.provenance || []).map(function (p) {
                  return ["<code>" + esc(p.member) + "</code>", esc(p.from),
                          p.overrode
                            ? esc(p.overrode)
                            : '<span class="text-muted">nothing</span>'];
                })) +
          '<p class="small mb-0">Resolves to ' + esc(r.dimensionality.kind) +
          " &mdash; " + esc(r.dimensionality.detail) + "</p></div>";
      }
      if (r.kind === "derived") {
        html += '<div class="text-muted mt-1">reads ' +
          esc((r.inputs || []).join(", ") || "no feature") +
          (r.reads_clock ? " and the row's own clock" : "") +
          " &middot; grain " + esc(r.entity) +
          " &middot; would be definition v" + esc(r.definition_version) +
          " &middot; certification " + esc(r.certification) + "</div>";
        renderMeet(r);
      }
      if ((r.possible_duplicates || []).length) {
        html += '<div class="mt-2"><span class="open-badge">possible duplicates</span>' +
          '<div class="text-muted mt-1">' +
          r.possible_duplicates.map(function (d) {
            return esc(d.name) + (d.owner ? " (" + esc(d.owner) + ")" : "");
          }).join(" &middot; ") +
          " &mdash; the fourth <code>customer_income_v2_final</code> is a " +
          "discovery problem, and renaming is cheap now and expensive later." +
          "</div></div>";
      }
      if ((r.not_checked || []).length) {
        html += '<div class="text-muted mt-2" style="font-size:.72rem">' +
          "Not answered by this check: " +
          r.not_checked.map(function (n) { return esc(n); }).join("; ") +
          ".</div>";
      }
      return html;
    }

    function renderMeet(r) {
      var order = r.certification_order || CFG.certificationOrder || [];
      var inputs = r.certification_of_inputs || [];
      if (!inputs.length) {
        $("#meet").html('<p class="text-muted small mb-0">This draft reads no ' +
          "feature, so there is no meet to take.</p>");
        return;
      }
      var rows = inputs.map(function (i) {
        var rank = order.indexOf(i.certification);
        return ["<code>" + esc(i.name) + "</code>", esc(i.certification),
                rank < 0 ? '<span class="text-muted">outside the order, so it '
                           + 'ranks bottom</span>' : String(rank)];
      });
      $("#meet").html(
        table(["Input", "Certification", "Rank"], rows) +
        '<p class="small mb-0"><strong>' + esc(r.name) + "</strong> would be " +
        '<span class="chip">' + esc(r.certification) + "</span> " +
        '<span class="text-muted">— the weakest of them, and no more.</span></p>');
    }

    var checkPrimitive = debounce(function () {
      verdictOf("primitive", primitiveDraft());
    });
    var checkDerived = debounce(function () {
      verdictOf("derived", derivedDraft());
    });
    var checkComposed = debounce(function () {
      verdictOf("composed", composedDraft());
    });

    $("#primitive").on("input change", checkPrimitive);
    $("#derived").on("input change", checkDerived);
    $("#composed").on("input change", checkComposed);
    $("#d-evaluator").on("change", function () {
      // Offered, not enforced: the declared list is refused on an internal
      // definition by the server, and hiding the box entirely would teach
      // nobody why the two evaluators differ.
      $("#d-inputs-wrap").prop("hidden", $(this).val() !== CFG.external);
    }).trigger("change");

    $("#primitive").on("submit", function (e) {
      e.preventDefault();
      var f = fields(this), $out = $("#primitive-result");
      var body = {name: f.name, entity: f.entity, dtype: f.dtype,
                  description: f.description || "", owner: f.owner || "",
                  business_definition: f.business_definition || "",
                  source_system: f.source_system || "",
                  sensitivity: f.sensitivity || "internal",
                  proxy_risk: f.proxy_risk || "none",
                  pii: !!f.pii, protected_basis: !!f.protected_basis,
                  ephemeral: !!f.ephemeral};
      if (f.shape) { body.shape = f.shape; }
      if (f.components) { body.components = commas(f.components); }
      if (f.ttl_days) { body.ttl_days = num(f.ttl_days); }
      if (f.defaults) {
        try { body.defaults = JSON.parse(f.defaults); }
        catch (err) {
          $out.html('<span class="evidence-bad">the default policy is not JSON</span> &mdash; ' +
                    esc(err.message));
          return;
        }
      }
      post(API + "/features", body).done(function (r) {
        var name = r.feature.name;
        $out.html('<span class="evidence-ok">defined</span> &mdash; ' +
          '<a href="/feature/' + encodeURIComponent(name) + '">' + esc(name) +
          "</a> is <code>" + esc(r.feature.certification) + "</code>; it has no " +
          "values yet. <a href='/features/load'>Load some</a>.");
        $("#primitive-submit").prop("disabled", true);
      }).fail(function (xhr) { $out.html(refusal(xhr)); });
    });

    $("#derived").on("submit", function (e) {
      e.preventDefault();
      var f = fields(this), $out = $("#derived-result");
      var body = {name: f.name, expression: f.expression, dtype: f.dtype,
                  description: f.description || "", evaluator: f.evaluator,
                  on_error: f.on_error, note: f.note || "",
                  inputs: f.evaluator === CFG.external ? commas(f.inputs) : []};
      post(API + "/derived-features", body).done(function (r) {
        $out.html('<span class="evidence-ok">defined</span> &mdash; ' +
          '<a href="/feature/' + encodeURIComponent(r.name) + '">' + esc(r.name) +
          "</a> at definition v" + esc(r.definition_version) + ", reading " +
          esc((r.inputs || []).join(", ")) + ".");
        $("#derived-submit").prop("disabled", true);
      }).fail(function (xhr) { $out.html(refusal(xhr)); });
    });

    $("#composed").on("submit", function (e) {
      e.preventDefault();
      var f = fields(this), $out = $("#composed-result");
      var body = {name: f.name, entity: f.entity, dtype: f.dtype,
                  description: f.description || "", owner: f.owner || "",
                  composes: commas(f.composes).map(function (n) {
                    return {name: n};
                  })};
      if (f.operations) {
        try { body.operations = JSON.parse(f.operations); }
        catch (err) {
          $out.html('<span class="evidence-bad">the operations are not JSON</span> &mdash; ' +
                    esc(err.message));
          return;
        }
      }
      post(API + "/features", body).done(function (r) {
        var name = r.feature.name;
        $out.html('<span class="evidence-ok">composed</span> &mdash; ' +
          '<a href="/feature/' + encodeURIComponent(name) + '">' + esc(name) +
          "</a>");
        $("#composed-submit").prop("disabled", true);
      }).fail(function (xhr) { $out.html(refusal(xhr)); });
    });

    $("#trial-run").on("click", function () {
      var $out = $("#trial-out"), rows;
      try { rows = lines($("#trial-rows").val()); }
      catch (e) {
        $out.html('<span class="evidence-bad">' + esc(e.message) + "</span>");
        return;
      }
      var f = fields(document.getElementById("derived"));
      post(API + "/features/trial", {expression: f.expression || "",
                                     on_error: f.on_error, rows: rows})
        .done(function (r) {
          var body = r.rows.map(function (row) {
            return [esc(row.row), esc(row[CLOCKS.entity]),
                    row.value === null ? '<span class="text-muted">null</span>'
                                       : esc(row.value),
                    esc(row[CLOCKS.ingest_time]),
                    esc(row.knowable_at) +
                      (row.clock_moved ? ' <span class="evidence-bad">moved</span>' : ""),
                    row.refused ? '<span class="evidence-bad">refused</span>' : "",
                    '<span class="text-muted">' + esc(row.detail || "") + "</span>"];
          });
          $out.html(
            table(["Row", CLOCKS.entity, "Value", "Row's " + CLOCKS.ingest_time,
                   "Knowable at", "", "Why"], body) +
            '<p class="small mb-1">' + esc(r.detail) + "</p>" +
            '<p class="text-muted mb-0" style="font-size:.72rem">' +
            esc(r.clock_rule) + "</p>");
        }).fail(function (xhr) { $out.html(refusal(xhr)); });
    });
  }

  // ================================================================ load page
  function loadPage() {
    // The media type per extension comes from the server's own transfer table,
    // rendered into the page. A copy kept here would be the one that drifts.
    var MEDIA = {};
    (CFG.uploads || []).forEach(function (u) { MEDIA[u.format] = u.media_type; });
    var EXTENSION = {csv: "csv", jsonl: "ndjson", ndjson: "ndjson",
                     parquet: "parquet", arrow: "arrow"};

    function loaded(r, view) {
      var quality = r.quality_report || {};
      var rows = Object.keys(quality).map(function (name) {
        return ["<code>" + esc(name) + "</code>", esc(quality[name].null_rate),
                esc(quality[name].distinct)];
      });
      var html = '<span class="evidence-ok">loaded</span> &mdash; ' +
        esc(view) + " v" + esc(r.version) + " holds " +
        esc(r.row_count) + " rows, pinned at Delta v" + esc(r.delta_version) +
        ".<div class='text-muted mt-1'>The two clocks on these rows are <code>" +
        esc(r.valid_time_column) + "</code> (when the fact was true) and <code>" +
        esc(r.ingest_time_column) + "</code> (when the platform learned it). " +
        "Nothing an earlier version serves has changed.</div>" +
        "<div class='mt-2'>" + table(["Feature", "Null rate", "Distinct"], rows) +
        "</div>";
      $("#load-result").html(html);
      readBack(view, r.version);
    }

    function readBack(view, version) {
      $.getJSON(API + "/feature-views/" + encodeURIComponent(view) +
                "/versions/" + version + "/data?format=json&limit=25")
        .done(function (r) {
          var names = [];
          (r.rows || []).forEach(function (row) {
            Object.keys(row).forEach(function (k) {
              if (names.indexOf(k) < 0) { names.push(k); }
            });
          });
          var body = (r.rows || []).map(function (row) {
            return names.map(function (k) {
              var clock = (k === CLOCKS.valid_time || k === CLOCKS.ingest_time);
              return (clock ? '<span style="color:var(--crimson)">' : "") +
                     esc(row[k]) + (clock ? "</span>" : "");
            });
          });
          $("#load-result").append(
            '<p class="small mt-2 mb-1"><strong>Read back from the pinned ' +
            'version</strong> &mdash; the two clocks in red.</p>' +
            table(names, body) +
            '<p class="text-muted mb-0" style="font-size:.72rem">' +
            esc(r.detail || "") + " <a href='/features/point-in-time'>Ask a " +
            "point-in-time question of them</a>.</p>");
        }).fail(function (xhr) { $("#load-result").append(refusal(xhr)); });
    }

    $("#new-view").on("submit", function (e) {
      e.preventDefault();
      var f = fields(this), $out = $("#view-result");
      var chosen = $("#v-features").val() || [];
      post(API + "/feature-views", {
        name: f.name, entity: f.entity, owner: f.owner,
        description: f.description || "", features: chosen
      }).done(function (r) {
        $out.html('<span class="evidence-ok">created</span> &mdash; ' + esc(r.name) +
          " lives at <code>" + esc(r.delta_table) + "</code> and has no versions " +
          "yet. Reloading&hellip;");
        window.setTimeout(function () { location.reload(); }, 900);
      }).fail(function (xhr) { $out.html(refusal(xhr)); });
    });

    $("#load-file-go").on("click", function (e) {
      e.preventDefault();
      var view = $("#load-view").val(), $out = $("#load-result");
      var file = document.getElementById("load-file").files[0];
      if (!view) {
        $out.html('<span class="evidence-bad">choose a view first</span>');
        return;
      }
      if (!file) {
        $out.html('<span class="evidence-bad">choose a file first</span>');
        return;
      }
      var ext = (file.name.split(".").pop() || "").toLowerCase();
      var media = MEDIA[EXTENSION[ext]];
      if (!media) {
        $out.html('<span class="evidence-bad">MAYA does not read a <code>.' +
          esc(ext) + "</code> file</span> &mdash; the formats it accepts are " +
          "listed above.");
        return;
      }
      $out.html('<span class="text-muted">loading ' + esc(file.name) + "&hellip;</span>");
      // The raw-body endpoint an execution engine uses, not a convenience
      // beside it: the interface exercises the contract.
      fetch(API + "/feature-views/" + encodeURIComponent(view) + "/data", {
        method: "POST", headers: {"Content-Type": media}, body: file
      }).then(function (response) {
        return response.json().then(function (body) {
          return {ok: response.ok, body: body};
        });
      }).then(function (r) {
        if (!r.ok) {
          $out.html(refusal({responseJSON: r.body, statusText: "refused"}));
          return;
        }
        loaded(r.body, view);
      }).catch(function (err) {
        $out.html('<span class="evidence-bad">' + esc(err) + "</span>");
      });
    });

    $("#paste-go").on("click", function (e) {
      e.preventDefault();
      var view = $("#load-view").val(), $out = $("#load-result");
      var text = $("#paste-rows").val();
      if (!view) {
        $out.html('<span class="evidence-bad">choose a view first</span>');
        return;
      }
      if ($("#paste-format").val() === "csv") {
        fetch(API + "/feature-views/" + encodeURIComponent(view) + "/data", {
          method: "POST", headers: {"Content-Type": MEDIA.csv}, body: text
        }).then(function (response) {
          return response.json().then(function (body) {
            return {ok: response.ok, body: body};
          });
        }).then(function (r) {
          if (!r.ok) {
            $out.html(refusal({responseJSON: r.body, statusText: "refused"}));
            return;
          }
          loaded(r.body, view);
        }).catch(function (err) {
          $out.html('<span class="evidence-bad">' + esc(err) + "</span>");
        });
        return;
      }
      var rows;
      try { rows = lines(text); }
      catch (parseError) {
        $out.html('<span class="evidence-bad">' + esc(parseError.message) + "</span>");
        return;
      }
      post(API + "/feature-views/" + encodeURIComponent(view) + "/materialise",
           {rows: rows})
        .done(function (r) { loaded(r, view); })
        .fail(function (xhr) { $out.html(refusal(xhr)); });
    });
  }

  // ======================================================== point-in-time page
  function pointInTimePage() {
    var VIEWS = {};
    (CFG.views || []).forEach(function (v) { VIEWS[v.name] = v.versions || []; });

    function versionOptions(viewSelect, versionSelect) {
      var versions = VIEWS[$(viewSelect).val()] || [];
      $(versionSelect).html(versions.map(function (v) {
        return '<option value="' + v.version + '">v' + v.version + " &mdash; " +
               v.row_count + " rows</option>";
      }).join("") || '<option value="">no versions</option>');
    }

    $("#asof-view").on("change", function () {
      versionOptions("#asof-view", "#asof-version");
    }).trigger("change");
    $("#as-view").on("change", function () {
      versionOptions("#as-view", "#as-version");
    }).trigger("change");

    $("#asof").on("submit", function (e) {
      e.preventDefault();
      var $out = $("#asof-out");
      var view = $("#asof-view").val(), version = $("#asof-version").val();
      if (!view || !version) {
        $out.html('<span class="evidence-bad">there is no materialised version ' +
                  "to ask of</span>");
        return;
      }
      post(API + "/feature-views/" + encodeURIComponent(view) + "/versions/" +
           version + "/as-of",
           {label_ts: num($("#asof-label").val()),
            as_of: num($("#asof-as-of").val()),
            entity_id: $("#asof-entity").val() || null})
        .done(function (r) {
          var html = '<p class="small mb-2">Reading <code>' + esc(r.namespace) +
            "</code> at Delta v" + esc(r.delta_version) + ". The event clock is " +
            "bounded by <strong>" + esc(r.label_ts) + "</strong> and the ingest " +
            "clock by <strong>" + esc(r.knowable_by) + "</strong> = min(&#8467;, a).</p>";
          if (!r.entities.length) {
            html += '<p class="text-muted small">No rows.</p>';
          }
          r.entities.forEach(function (entity) {
            var rows = entity.candidates.map(function (c) {
              return [esc(c[CLOCKS.valid_time]), esc(c[CLOCKS.ingest_time]),
                      c.admissible
                        ? '<span class="evidence-ok">admissible</span>'
                        : '<span class="evidence-bad">refused</span>',
                      '<span class="text-muted">' + esc(c.detail) + "</span>"];
            });
            var read = entity.read;
            html += '<p class="small mb-1"><strong>' + esc(entity[CLOCKS.entity]) +
              "</strong> &mdash; " + esc(entity.detail) + "</p>" +
              table([CLOCKS.valid_time, CLOCKS.ingest_time, "Verdict", "Why"], rows) +
              (read ? '<p class="small mb-3">The read returns the row true at ' +
                      esc(read[CLOCKS.valid_time]) + " and known at " +
                      esc(read[CLOCKS.ingest_time]) + ".</p>"
                    : '<p class="small mb-3 text-muted">The read returns nothing ' +
                      "for this entity.</p>");
          });
          html += '<p class="text-muted mb-0" style="font-size:.72rem"><code>' +
            esc(r.operator) + "</code> &mdash; " + esc(r.rows_examined) +
            " rows examined." + (r.truncated ? " The read was capped." : "") + "</p>";
          $out.html(html);
        }).fail(function (xhr) { $out.html(refusal(xhr)); });
    });

    $("#assemble").on("submit", function (e) {
      e.preventDefault();
      var $out = $("#assemble-out"), spine;
      try { spine = lines($("#as-spine").val()); }
      catch (parseError) {
        $out.html('<span class="evidence-bad">' + esc(parseError.message) + "</span>");
        return;
      }
      var body = {
        name: $("#as-name").val(), spine: spine, as_of: num($("#as-as-of").val()),
        views: [{view: $("#as-view").val(),
                 version: num($("#as-version").val())}],
        valid_time_bound: $("#as-valid").is(":checked"),
        transaction_time_bound: $("#as-txn").is(":checked")
      };
      post(API + "/training-sets", body).done(function (r) {
        var report = r.pit_report || {};
        $out.html(
          '<span class="' + (r.pit_verified ? "evidence-ok" : "evidence-bad") +
          '">' + (r.pit_verified ? "verified" : "not verified") + "</span> &mdash; " +
          esc(r.row_count) + " rows written to <code>" + esc(r.delta_table) +
          "</code> at Delta v" + esc(r.delta_version) + "." +
          '<div class="text-muted mt-1">' + esc(report.layer) + ": " +
          esc(report.detail) + " (" + esc(report.checked) + " rows independently " +
          "recomputed)</div>" +
          ((report.leakage || []).length
            ? '<div class="evidence-bad mt-1">suspected leakage in ' +
              esc(report.leakage.join(", ")) + "</div>" : "") +
          ((report.violations || []).length
            ? '<div class="evidence-bad mt-1">' + esc(report.violations.length) +
              " rows disagreed with the independent recomputation</div>" : ""));
      }).fail(function (xhr) { $out.html(refusal(xhr)); });
    });

    $("#align").on("submit", function (e) {
      e.preventDefault();
      var $out = $("#align-out"), rows;
      try { rows = lines($("#al-rows").val()); }
      catch (parseError) {
        $out.html('<span class="evidence-bad">' + esc(parseError.message) + "</span>");
        return;
      }
      post(API + "/features/alignment-trial", {
        rows: rows, axis: $("#al-axis").val(), rule: $("#al-rule").val(),
        grid: $("#al-grid").val(), step: num($("#al-step").val()),
        carry_limit: num($("#al-limit").val())
      }).done(function (r) {
        var columns = [CLOCKS.entity, r.axis].concat(r.columns)
                        .concat([CLOCKS.ingest_time]);
        var body = r.rows.map(function (row) {
          return columns.map(function (k) {
            return (k === CLOCKS.ingest_time
                    ? '<span style="color:var(--crimson)">' : "") +
                   (row[k] === null || row[k] === undefined
                     ? '<span class="text-muted">null</span>' : esc(row[k])) +
                   (k === CLOCKS.ingest_time ? "</span>" : "");
          });
        });
        $out.html(
          '<p class="small mb-1"><code>' + esc(r.rule) + "</code> &mdash; " +
          esc(r.means) + "</p>" +
          '<p class="small mb-2">' +
          (r.point_in_time_safe
            ? '<span class="evidence-ok">safe for training</span>'
            : '<span class="evidence-bad">reaches into the future</span>') +
          " &mdash; " + esc(r.detail) + "</p>" +
          table(columns, body) +
          '<p class="text-muted mb-0" style="font-size:.72rem">The ' +
          esc(CLOCKS.ingest_time) + " column is when each filled value actually " +
          "became knowable. Nothing here is refused; the point-in-time read " +
          "excludes what it should, by the ordinary rule.</p>");
      }).fail(function (xhr) { $out.html(refusal(xhr)); });
    });
  }

  // ============================================================= feature page
  function featurePage() {
    var name = encodeURIComponent(CFG.name || "");

    function acted($out, message) {
      return function () {
        $out.html('<span class="evidence-ok">' + message + "</span>" +
                  '<div class="text-muted">Reloading&hellip;</div>');
        window.setTimeout(function () { location.reload(); }, 900);
      };
    }

    $("#certify").on("submit", function (e) {
      e.preventDefault();
      var $out = $("#certify-out");
      post(API + "/features/" + name + "/certify?level=" +
           encodeURIComponent($("#cert-level").val()), {})
        .done(acted($out, "recorded"))
        .fail(function (xhr) { $out.html(refusal(xhr)); });
    });

    $("#seal").on("submit", function (e) {
      e.preventDefault();
      var $out = $("#seal-out");
      post(API + "/features/" + name + "/seal", {note: $("#seal-note").val() || ""})
        .done(acted($out, "sealed"))
        .fail(function (xhr) { $out.html(refusal(xhr)); });
    });

    $("#transfer").on("submit", function (e) {
      e.preventDefault();
      var $out = $("#transfer-out");
      post(API + "/features/" + name + "/transfer",
           {to: $("#transfer-to").val() || "", reason: $("#transfer-why").val() || ""})
        .done(acted($out, "handed on"))
        .fail(function (xhr) { $out.html(refusal(xhr)); });
    });

    $("#destroy").on("click", function () {
      var $out = $("#destroy-out");
      $.ajax({url: API + "/features/" + name, method: "DELETE"})
        .done(function () {
          $out.html('<span class="evidence-ok">destroyed</span> &mdash; the rows ' +
            "are gone and the record of the destruction is not. " +
            "<a href='/features'>Back to the catalogue</a>");
        })
        .fail(function (xhr) { $out.html(refusal(xhr)); });
    });
  }

  // ------------------------------------------------------------------ start
  $(function () {
    if (CFG.page === "define") { definePage(); }
    if (CFG.page === "load") { loadPage(); }
    if (CFG.page === "point-in-time") { pointInTimePage(); }
    if (CFG.page === "feature") { featurePage(); }
  });
}());
