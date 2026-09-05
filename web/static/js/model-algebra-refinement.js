/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Refinement between versions, and the alias move that acts on it.
 *
 * The two obligations — L-7 on the contract, L-12 on the schemas — are
 * discharged by the platform, in the same function the alias move discharges
 * them with. This file shows the verdict and the reason; it does not compare a
 * single bound or a single field itself, and the move button is never disabled
 * on a local reading of the answer: the move is refused by the register, which
 * is the only place that refusal means anything.
 */
(function () {
  "use strict";

  window.mayaAlgebraRefinement = function (options) {
    var A = window.mayaAlgebra;

    function clause(label, ok, reason) {
      return '<div class="sig ' + (ok ? "signed" : "declined") + '">' +
             '<span class="ic">' + (ok ? "✓" : "✕") + "</span>" +
             '<span class="flex-grow-1"><strong>' + A.escapeHtml(label) + "</strong>" +
             '<div class="who">' + A.escapeHtml(reason) + "</div></span></div>";
    }

    var ask = document.getElementById("substitution-form");
    if (ask) {
      ask.addEventListener("submit", function (event) {
        event.preventDefault();
        var f = A.fields(ask);
        A.post("/api/v1/model-algebra/substitution", {
          urn: options.urn, incumbent: f.incumbent, replacement: f.replacement
        }).done(function (out) {
          document.getElementById("substitution-result").innerHTML =
            '<div class="mono mb-2">' + A.escapeHtml(out.replacement) +
            " may replace " + A.escapeHtml(out.incumbent) + "?</div>" +
            clause("L-7 — the contract refines: assume no more, guarantee no less",
                   out.refinement.holds, out.refinement.reason) +
            clause("L-12 — the schemas vary correctly: contravariant in inputs, " +
                   "covariant in outputs", out.variance.ok, out.variance.reason) +
            '<div class="state-note mt-2">' + A.escapeHtml(out.detail) + "</div>";
        }).fail(function (xhr) { A.refuse("#substitution-result", xhr); });
      });
    }

    var move = document.getElementById("alias-form");
    if (move) {
      move.addEventListener("submit", function (event) {
        event.preventDefault();
        var f = A.fields(move);
        A.put("/api/v1/models/" + options.name + "/aliases", {
          environment: f.environment, alias: f.alias, semver: f.semver,
          justification: f.justification || ""
        }).done(function (out) {
          document.getElementById("alias-result").innerHTML =
            '<span class="evidence-ok">Moved</span> — ' +
            A.escapeHtml(out.environment) + "/" + A.escapeHtml(out.alias) +
            " now resolves to " + A.escapeHtml(out.version) +
            '<div class="text-muted" style="font-size:.76rem">refinement: ' +
            A.escapeHtml(out.refinement.reason) + " · variance: " +
            A.escapeHtml(out.variance.reason) + "</div>";
          window.setTimeout(function () { window.location.reload(); }, 1200);
        }).fail(function (xhr) { A.refuse("#alias-result", xhr); });
      });
    }
  };
}());
