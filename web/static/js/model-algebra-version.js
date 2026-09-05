/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Version creation, with the trainability class derived by the server.
 *
 * Every keystroke that could change the class asks the register what the class
 * would be. The answer — the class, the branch of the derivation that fired,
 * the fibre it lands in, and whether the version would be refused — is rendered
 * exactly as it arrives. The create button is enabled on `ok` from that reply
 * and on nothing else: this file contains no rule about what makes a kernel
 * acceptable, and adding one here would put a second copy of the rule on a
 * screen where nobody would think to look for it.
 */
(function () {
  "use strict";

  window.mayaAlgebraVersion = function (options) {
    var A = window.mayaAlgebra;
    var form = document.getElementById("version-form");
    var button = document.getElementById("create-version");
    var gate = document.getElementById("create-gate");
    if (!form) { return; }

    function draft() {
      var f = A.fields(form);
      var input = A.parseField(f.input_schema, "input schema", "#version-result");
      var output = A.parseField(f.output_schema, "output schema", "#version-result");
      if (!input.ok || !output.ok) { return null; }
      return {
        parameter_kind: f.parameter_kind, fit_procedure: f.fit_procedure,
        output_kind: f.output_kind, adaptive: Number(f.adaptive),
        deterministic: Number(f.deterministic),
        input_schema: input.value || [], output_schema: output.value || []
      };
    }

    function renderFibre(fibre) {
      var box = document.getElementById("derived-fibre");
      if (!fibre) {
        box.innerHTML = '<span class="evidence-bad">This class has no fibre.</span> ' +
          "L-15 says every class has one, so the platform is reporting a gap in " +
          "itself rather than a problem with this kernel.";
        return;
      }
      function chips(list) {
        return (list && list.length)
          ? list.map(function (x) { return '<span class="chip">' + A.escapeHtml(x) + "</span> "; }).join("")
          : '<span class="text-muted">none</span>';
      }
      box.innerHTML =
        '<div class="mb-1"><strong>Evidence it owes</strong> ' + chips(fibre.evidence) + "</div>" +
        '<div class="mb-1"><strong>Monitors that can answer</strong> ' + chips(fibre.metrics) + "</div>" +
        '<div class="mb-1"><strong>Documents that compile</strong> ' + chips(fibre.templates) + "</div>" +
        '<div class="mb-1"><strong>States it may occupy</strong> ' + chips(fibre.lifecycle) + "</div>" +
        '<div class="mt-2"><em>Soundness</em> — ' + A.escapeHtml(fibre.soundness) + "</div>" +
        '<div><em>Outcomes</em> — ' + A.escapeHtml(fibre.outcomes) + "</div>" +
        '<div><em>Monitoring answers</em> — ' + A.escapeHtml(fibre.answers) + "</div>";
    }

    function render(verdict) {
      document.getElementById("derived-class").textContent = verdict.trainability_class;
      document.getElementById("derived-label").textContent =
        verdict.fibre ? verdict.fibre.label : "";
      document.getElementById("derived-detail").innerHTML =
        A.escapeHtml(verdict.detail) +
        (verdict.requires_fitting_evidence
          ? ". Fitting evidence is owed."
          : ". <strong>No fitting evidence is owed</strong> — asking this class " +
            "for a training set is a category error.");
      document.getElementById("derivation-steps").innerHTML =
        verdict.derivation.map(function (step) {
          return "<tr><td class=\"mono\" style=\"font-size:.72rem\">" +
                 A.escapeHtml(step.reads) + "</td><td style=\"font-size:.76rem\">" +
                 A.escapeHtml(step.says) + "</td></tr>";
        }).join("");
      document.getElementById("derived-refusal").innerHTML = verdict.refusal
        ? '<div class="evidence-bad">The register would refuse this version</div>' +
          '<div class="text-muted" style="font-size:.78rem">' +
          A.escapeHtml(verdict.refusal) + "</div>"
        : "";
      renderFibre(verdict.fibre);
      button.disabled = !verdict.ok;
      gate.textContent = verdict.ok
        ? "the register would accept this kernel"
        : "the register would refuse this kernel; the refusal is above";
    }

    function check() {
      var body = draft();
      if (!body) { return; }
      A.post("/api/v1/model-algebra/kernel", body)
        .done(render)
        .fail(function (xhr) {
          button.disabled = true;
          gate.textContent = "the check itself was refused";
          A.refuse("#derived-refusal", xhr);
        });
    }

    form.addEventListener("change", check);
    check();

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var f = A.fields(form);
      var kernel = draft();
      if (!kernel) { return; }
      var contract = A.parseField(f.contract, "operating contract", "#version-result");
      if (!contract.ok) { return; }
      var body = {semver: f.semver, kernel: kernel};
      if (contract.value) { body.contract = contract.value; }
      if (f.artifact_uri) { body.artifact_uri = f.artifact_uri; }
      if (f.artifact_digest) { body.artifact_digest = f.artifact_digest; }
      A.post("/api/v1/models/" + options.name + "/versions", body)
        .done(function () { window.location.reload(); })
        .fail(function (xhr) { A.refuse("#version-result", xhr); });
    });
  };
}());
