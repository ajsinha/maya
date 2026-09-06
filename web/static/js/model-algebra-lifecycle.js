/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * The lifecycle buttons, and the refusals they are supposed to produce.
 *
 * Every button posts to the endpoint that performs the move; none of them is
 * hidden or disabled on a guess about whether the move is legal. That is
 * deliberate rather than lazy: `illegal_transition` names what you *may* do
 * from here, and `record_frozen` names amendment as the way out — both of which
 * teach something a greyed-out button does not. The buttons come from
 * `flow.available_transitions`, which the state machine computed.
 */
(function () {
  "use strict";

  window.mayaAlgebraLifecycle = function (options) {
    var A = window.mayaAlgebra;
    var base = "/api/v1/models/" + options.name;

    /* Which acts need a reason, and what to call it. A reason is not paperwork:
       a record returned or retired without one is a decision nobody can ask
       about afterwards. */
    var asks = {
      "return": {path: "/return", question: "Why is this being returned?", field: "reason"},
      "amend": {path: "/amend", question: "What is changing, and why?", field: "reason"},
      "retire": {path: "/retire", question: "Why is this model being retired?", field: "reason"}
    };

    function say(html) {
      var box = document.getElementById("flow-msg");
      if (box) { box.innerHTML = html; }
    }

    document.querySelectorAll("[data-action]").forEach(function (button) {
      button.addEventListener("click", function () {
        var act = button.getAttribute("data-action");
        var url = base + "/" + act;
        var body = {};
        if (asks[act]) {
          var answer = window.prompt(asks[act].question);
          if (!answer) { return; }
          url = base + asks[act].path;
          body[asks[act].field] = answer;
        } else if (act === "attest" || act === "decline") {
          var role = window.prompt(
            "Sign as which role? A signature under a borrowed hat is not a quorum.");
          if (!role) { return; }
          url = base + "/attest";
          body = {role: role, decision: act === "decline" ? "decline" : "attest",
                  statement: window.prompt("Statement (optional)") || ""};
        }
        say("Working…");
        A.post(url, body)
          .done(function () { window.location.reload(); })
          .fail(function (xhr) { say(A.refusalHtml(xhr)); });
      });
    });

    var update = document.getElementById("update-form");
    if (update) {
      update.addEventListener("submit", function (event) {
        event.preventDefault();
        var f = A.fields(update);
        var fields = {};
        fields[f.field] = f.value;
        A.patch(base, {fields: fields})
          .done(function () {
            A.accept("#update-result", "Revised — the record was open to change");
            window.setTimeout(function () { window.location.reload(); }, 1000);
          })
          .fail(function (xhr) { A.refuse("#update-result", xhr); });
      });
    }
  };
}());
