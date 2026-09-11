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

  /* Deletion. Not a transition, and not offered beside them: `retire`
     withdraws a model from use and keeps every reference readable, while this
     removes the row — and nineteen tables carry a `model_id`. The register
     refuses one that anything refers to and names what, so the refusal is
     rendered whole rather than summarised. */
  var deleteButton = document.getElementById("delete-model");
  if (deleteButton) {
    deleteButton.addEventListener("click", function () {
      var name = deleteButton.getAttribute("data-name");
      var reason = window.prompt(
        "Delete " + name + " permanently. Why?\n\n" +
        "The evidence chain survives this, so the reason is what makes the " +
        "acts it still describes readable. Refused if anything refers to the " +
        "model — retiring is almost always the right act instead.");
      if (!reason) { return; }
      A.remove("/api/v1/models/" + encodeURIComponent(name) +
               "?reason=" + encodeURIComponent(reason))
        .done(function () { window.location = "/dashboard"; })
        .fail(function (xhr) {
          document.getElementById("delete-msg").innerHTML = A.refusalHtml(xhr);
        });
    });
  }
}());

/* Decommissioning. Posted whole rather than field by field: the refusals are
   about the record being complete, and a form that validated the rationale
   before the consumer list would teach the wrong lesson about which of them
   matters. The consumer list is pre-filled with whoever reads this model, so
   the default act is *tell them*, and going ahead anyway is a tick somebody
   has to make. */
(function () {
  "use strict";
  var form = document.getElementById("decommission-form");
  if (!form) { return; }
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var A = window.mayaAlgebra;
    var urn = "maya://model/" + form.getAttribute("data-name");
    var notified = document.getElementById("dc-notified").value
      .split(",").map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });
    A.post("/api/v1/decommission?urn=" + encodeURIComponent(urn), {
      rationale: document.getElementById("dc-rationale").value,
      replacement: document.getElementById("dc-replacement").value,
      retention_class: document.getElementById("dc-retention").value,
      notified: notified,
      acknowledged: document.getElementById("dc-acknowledged").checked
    })
      .done(function () {
        A.accept("#decommission-result",
                 "Recorded, and the model is out of service. Nothing was " +
                 "archived and nothing was deleted.");
        window.setTimeout(function () { window.location.reload(); }, 1200);
      })
      .fail(function (xhr) { A.refuse("#decommission-result", xhr); });
  });
}());
