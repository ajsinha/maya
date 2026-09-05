/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Typed composition: propose an edge and see it accepted or refused.
 *
 * The proposal goes to `POST /api/v1/model-relations`, which is the endpoint
 * that records the edge — there is no dry run and there should not be one. An
 * `input_to` edge is type-checked against the latest version at each end, and
 * the refusal names the fields that are missing or narrowed. Rendering that
 * refusal is all this file does with it; deciding whether the schemas compose
 * happens in `core.domain.lattice.refines` and nowhere else.
 */
(function () {
  "use strict";

  window.mayaAlgebraComposition = function () {
    var A = window.mayaAlgebra;

    /* What the chosen relation does, from the vocabulary the server sent with
       the options rather than from a copy of it kept here. */
    var kind = document.getElementById("relate-kind");
    function describeKind() {
      var option = kind.options[kind.selectedIndex];
      var composes = option.getAttribute("data-composes") === "1";
      document.getElementById("relate-meaning").innerHTML =
        A.escapeHtml(option.getAttribute("data-means")) +
        (composes
          ? ' — <strong>type-checked</strong>: the source\'s output must arrive ' +
            "where the target's input is read, or the edge is refused."
          : " — recorded, not type-checked.");
    }
    if (kind) { kind.addEventListener("change", describeKind); describeKind(); }

    var relate = document.getElementById("relate-form");
    if (relate) {
      relate.addEventListener("submit", function (event) {
        event.preventDefault();
        var f = A.fields(relate);
        A.post("/api/v1/model-relations", {
          from_urn: f.from_urn, to_urn: f.to_urn, kind: f.kind, note: f.note || ""
        }).done(function (edge) {
          document.getElementById("relate-result").innerHTML =
            '<span class="evidence-ok">Recorded</span> — ' +
            A.escapeHtml(edge.from_urn) + " " + A.escapeHtml(edge.kind) + " " +
            A.escapeHtml(edge.to_urn) +
            '<div class="text-muted" style="font-size:.76rem">' +
            A.escapeHtml(edge.means) + "</div>";
        }).fail(function (xhr) { A.refuse("#relate-result", xhr); });
      });
    }

    var composite = document.getElementById("composite-form");
    if (composite) {
      composite.addEventListener("submit", function (event) {
        event.preventDefault();
        var f = A.fields(composite);
        jQuery.ajax({
          url: "/api/v1/model-algebra/composite?from_urn=" +
               encodeURIComponent(f.from_urn) + "&to_urn=" + encodeURIComponent(f.to_urn)
        }).done(function (out) {
          document.getElementById("composite-result").innerHTML =
            '<div class="mono fw-semibold">' + A.escapeHtml(out.composite) + "</div>" +
            "<div class=\"mt-1\"><strong>Input schema</strong> — the source's inputs: " +
            A.schemaHtml(out.input_schema) + "</div>" +
            "<div><strong>Output schema</strong> — the target's outputs: " +
            A.schemaHtml(out.output_schema) + "</div>" +
            '<div class="text-muted mt-1" style="font-size:.76rem">' +
            A.escapeHtml(out.detail) + "</div>";
        }).fail(function (xhr) { A.refuse("#composite-result", xhr); });
      });
    }

    var radius = document.getElementById("radius-form");
    if (radius) {
      radius.addEventListener("submit", function (event) {
        event.preventDefault();
        var f = A.fields(radius);
        A.post("/api/v1/blast-radius", {urn: f.urn}).done(function (out) {
          var rows = out.reaches.map(function (r) {
            return "<tr><td>" + A.escapeHtml(r.name) + "</td><td>" +
                   A.escapeHtml(r.tier === null ? "—" : r.tier) +
                   '</td><td data-sort="' + r.distance + '">' + r.distance + "</td></tr>";
          }).join("");
          document.getElementById("radius-result").innerHTML =
            '<div class="text-muted">' + A.escapeHtml(out.detail) + "</div>" +
            (rows ? '<table class="table table-sm maya mt-2 mb-0"><thead><tr>' +
                    "<th>Model</th><th>Tier</th><th>Distance</th></tr></thead><tbody>" +
                    rows + "</tbody></table>" : "");
        }).fail(function (xhr) { A.refuse("#radius-result", xhr); });
      });
    }

    var shared = document.getElementById("shared-form");
    if (shared) {
      shared.addEventListener("submit", function (event) {
        event.preventDefault();
        var chosen = Array.prototype.slice.call(
          shared.querySelector("select[name=urns]").selectedOptions)
          .map(function (o) { return o.value; });
        A.post("/api/v1/shared-dependencies", {urns: chosen}).done(function (out) {
          var rows = out.shared.map(function (r) {
            return "<tr><td>" + A.escapeHtml(r.name) + "</td><td>" +
                   A.escapeHtml(r.relied_on_by.join(", ")) +
                   '</td><td data-sort="' + r.count + '">' + r.count + "</td></tr>";
          }).join("");
          document.getElementById("shared-result").innerHTML =
            '<div class="text-muted">' + A.escapeHtml(out.detail) + "</div>" +
            (rows ? '<table class="table table-sm maya mt-2 mb-0"><thead><tr>' +
                    "<th>Shared dependency</th><th>Relied on by</th><th>Count</th>" +
                    "</tr></thead><tbody>" + rows + "</tbody></table>" : "");
        }).fail(function (xhr) { A.refuse("#shared-result", xhr); });
      });
    }

    document.querySelectorAll(".unrelate").forEach(function (button) {
      button.addEventListener("click", function () {
        var reason = window.prompt(
          "Why is this edge being removed? An edge that disappears without a " +
          "reason is a dependency somebody stopped believing in.");
        if (!reason) { return; }
        A.post("/api/v1/model-relations/remove", {
          from_urn: button.getAttribute("data-from"),
          to_urn: button.getAttribute("data-to"),
          kind: button.getAttribute("data-kind"), reason: reason
        }).done(function () { window.location.reload(); })
          .fail(function (xhr) { A.refuse("#unrelate-result", xhr); });
      });
    });
  };
}());
