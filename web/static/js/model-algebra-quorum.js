/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Version approval: open it, sign it, or try to approve it alone and be told why not.
 *
 * The single-signature button is wired to the ordinary approve endpoint and is
 * never suppressed. Where the tier demands a quorum the register refuses it with
 * `quorum_required` and names the endpoint that does the right thing, and that
 * refusal is the whole lesson — a button this page had hidden would have taught
 * nobody anything, and would have been this page deciding a governance question.
 */
(function () {
  "use strict";

  window.mayaAlgebraQuorum = function (options) {
    var A = window.mayaAlgebra;

    function box(button) {
      var body = button.closest(".card-body");
      return body ? body.querySelector(".quorum-msg") : null;
    }

    function report(button, html) {
      var node = box(button);
      if (node) { node.innerHTML = html; }
    }

    function reload() { window.location.reload(); }

    document.querySelectorAll(".open-approval").forEach(function (button) {
      button.addEventListener("click", function () {
        A.post("/api/v1/version-approvals", {
          urn: options.urn, semver: button.getAttribute("data-semver"),
          statement: window.prompt("Statement opening the approval (optional)") || ""
        }).done(reload).fail(function (xhr) { report(button, A.refusalHtml(xhr)); });
      });
    });

    document.querySelectorAll(".sign").forEach(function (button) {
      button.addEventListener("click", function () {
        A.post("/api/v1/version-approvals/" +
               button.getAttribute("data-approval") + "/sign", {
          role: button.getAttribute("data-role"),
          decision: button.getAttribute("data-decision"),
          statement: window.prompt("Statement (optional)") || ""
        }).done(reload).fail(function (xhr) { report(button, A.refusalHtml(xhr)); });
      });
    });

    document.querySelectorAll(".withdraw").forEach(function (button) {
      button.addEventListener("click", function () {
        A.post("/api/v1/version-approvals/" +
               button.getAttribute("data-approval") + "/withdraw", {})
          .done(reload).fail(function (xhr) { report(button, A.refusalHtml(xhr)); });
      });
    });

    document.querySelectorAll(".approve-directly").forEach(function (button) {
      button.addEventListener("click", function () {
        A.post("/api/v1/models/" + options.name + "/versions/" +
               button.getAttribute("data-semver") + "/approve", {})
          .done(function () { reload(); })
          .fail(function (xhr) { report(button, A.refusalHtml(xhr)); });
      });
    });
  };
}());
