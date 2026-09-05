/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Filing a document, and reviewing one.
 *
 * The upload is multipart because that is how a file arrives. `csrf.js` puts
 * the session's token on it like any other state-changing request — the token
 * travels in a header, so a multipart body needs nothing special and nothing is
 * reimplemented here.
 *
 * Whether a document may be accepted is not this file's question: the register
 * refuses a self-review, and refuses a second review of something already
 * decided, and both refusals are rendered as they arrive.
 */
(function () {
  "use strict";

  window.mayaAlgebraDocuments = function (options) {
    var A = window.mayaAlgebra;

    var kind = document.getElementById("attach-kind");
    function describeKind() {
      document.getElementById("attach-kind-means").textContent =
        kind.options[kind.selectedIndex].getAttribute("data-means");
    }
    if (kind) { kind.addEventListener("change", describeKind); describeKind(); }

    var form = document.getElementById("attach-form");
    if (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var chosen = form.querySelector("select[name=semver]").value;
        var data = new FormData();
        data.append("urn", options.urn);
        data.append("kind", form.querySelector("select[name=kind]").value);
        data.append("title", form.querySelector("input[name=title]").value);
        data.append("note", form.querySelector("input[name=note]").value || "");
        /* Model level has to be asked for, and asking for it means saying so:
           the sentinel below is this page's way of offering the choice, and the
           API sees the flag the API defines. */
        if (chosen === "__model__") {
          data.append("model_level", "true");
        } else if (chosen) {
          data.append("semver", chosen);
        }
        var subject = form.querySelector("select[name=subject_type]").value;
        var subjectId = form.querySelector("input[name=subject_id]").value;
        if (subject) { data.append("subject_type", subject); }
        if (subjectId) { data.append("subject_id", subjectId); }
        data.append("file", form.querySelector("input[type=file]").files[0]);

        jQuery.ajax({url: "/api/v1/attachments", method: "POST", data: data,
                     processData: false, contentType: false})
          .done(function () { window.location.reload(); })
          .fail(function (xhr) { A.refuse("#attach-result", xhr); });
      });
    }

    document.querySelectorAll(".review").forEach(function (button) {
      button.addEventListener("click", function () {
        var accept = button.getAttribute("data-accept") === "1";
        A.post("/api/v1/attachments/" + button.getAttribute("data-id") + "/review", {
          accept: accept,
          note: window.prompt(accept ? "Note on accepting (optional)"
                                     : "Why is this being rejected?") || ""
        }).done(function () { window.location.reload(); })
          .fail(function (xhr) { A.refuse("#review-result", xhr); });
      });
    });
  };
}());
