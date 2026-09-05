/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Risk assessment: the facts go up, the derivation comes back.
 *
 * The tier is `tau(materiality, complexity)` and is computed by the tiering
 * engine. This file renders the engine's own rationale string rather than
 * assembling a sentence of its own — the rationale is what is persisted beside
 * the tier, and a screen that said something different from the record would be
 * the more convincing of the two.
 */
(function () {
  "use strict";

  window.mayaAlgebraRisk = function (options) {
    var A = window.mayaAlgebra;
    var form = document.getElementById("assess-form");
    if (!form) { return; }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var f = A.fields(form);
      A.post("/api/v1/models/" + options.name + "/assess", {
        exposure: Number(f.exposure), purpose_class: f.purpose_class,
        feature_count: Number(f.feature_count),
        uses_alternative_data: Number(f.uses_alternative_data),
        interpretable: Number(f.interpretable)
      }).done(function (out) {
        document.getElementById("assess-result").innerHTML =
          '<div class="d-flex align-items-baseline gap-2">' +
          '<span class="tier tier-' + out.tier + '">TIER ' + out.tier + "</span>" +
          '<span class="mono">materiality ' + A.escapeHtml(out.materiality) +
          " × complexity " + A.escapeHtml(out.complexity) + "</span></div>" +
          '<div class="state-note mt-2">' + A.escapeHtml(out.rationale) + "</div>" +
          '<div class="mt-2"><strong>Controls this tier requires</strong><br>' +
          out.required_controls.map(function (c) {
            return '<span class="chip">' + A.escapeHtml(c) + "</span> ";
          }).join("") + "</div>" +
          '<div class="text-muted mt-1" style="font-size:.72rem">ruleset ' +
          A.escapeHtml(out.ruleset_version) +
          " — the derivation is stored beside the tier, so a tier can be " +
          "re-read against the rules that produced it</div>";
        window.setTimeout(function () { window.location.reload(); }, 2500);
      }).fail(function (xhr) { A.refuse("#assess-result", xhr); });
    });
  };
}());
