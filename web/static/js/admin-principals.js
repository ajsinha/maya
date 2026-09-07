/* MAYA — administering people, from the screen rather than from curl.
 *
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 *
 * This page listed everybody and then named the endpoints you had to run by
 * hand. Administering people is the one thing an operations manager does
 * daily, and this platform's own persona for that job is the administrator —
 * so a governance platform whose administrator cannot administer it from the
 * interface is one where somebody keeps a shell script, and a shell script is
 * where the second account for a forgotten password comes from.
 *
 * Nothing here decides anything. Every handler posts to the same API a script
 * would and renders what came back. The incompatible-roles check, the scope,
 * the segregation of duties and the evidence all happen where they already
 * did; a screen that re-implemented one of them would be a second
 * implementation, and it disagrees with the first eventually, in the direction
 * of permitting more.
 */
(function () {
  "use strict";

  function esc(text) {
    return String(text === undefined || text === null ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function refusal(xhr) {
    var r = window.MAYA.refusal.read(xhr);
    return '<div class="evidence-bad">Refused' +
      (r.code ? " — <code>" + esc(r.code) + "</code>" : "") + "</div>" +
      '<div class="small">' + r.lines.map(esc).join("<br>") + "</div>" +
      (r.remediation
        ? '<div class="text-muted small mt-1">' + esc(r.remediation) + "</div>"
        : "");
  }

  /* A comma-separated field as a list, with the empty string meaning "no
     restriction" rather than "one restriction that is blank" — which is the
     difference between the whole estate and nothing at all. */
  function list(value) {
    return String(value || "").split(",")
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });
  }

  function post(url, body, method) {
    return window.jQuery.ajax({
      url: url, method: method || "POST", contentType: "application/json",
      data: JSON.stringify(body)
    });
  }

  function say(where, html) {
    window.jQuery(where).html(html);
  }

  function reloadShortly() {
    window.setTimeout(function () { window.location.reload(); }, 1200);
  }

  window.jQuery(function ($) {
    /* ---- add somebody ------------------------------------------------- */
    $("#new-principal").on("submit", function (event) {
      event.preventDefault();
      var roles = $(".np-role:checked").map(function () {
        return this.value;
      }).get();
      if (!roles.length) {
        say("#np-result",
            '<div class="evidence-bad">Choose at least one role.</div>' +
            '<div class="text-muted small">A principal with no roles can sign ' +
            'in and do nothing, which reads as a permissions fault rather ' +
            'than as the empty grant it is.</div>');
        return;
      }
      var body = {
        username: $("#np-username").val().trim(),
        display_name: $("#np-display").val().trim(),
        kind: $("#np-kind").val(),
        roles: roles,
        legal_entities: list($("#np-entities").val()),
        domains: list($("#np-domains").val()),
        allow_conflicts: $("#np-conflicts").is(":checked")
      };
      var email = $("#np-email").val().trim();
      if (email) { body.email = email; }
      var password = $("#np-password").val();
      if (password) { body.password = password; }

      post("/api/v1/principals", body)
        .done(function (out) {
          say("#np-result", '<span class="evidence-ok">Added ' +
              esc(out.username || body.username) + "</span>");
          reloadShortly();
        })
        .fail(function (xhr) { say("#np-result", refusal(xhr)); });
    });

    /* ---- change somebody's roles -------------------------------------- */
    $(".edit-roles").on("click", function () {
      var username = this.getAttribute("data-username");
      var current = this.getAttribute("data-roles") || "";
      var answer = window.prompt(
        "Roles for " + username + ", comma separated.\n\n" +
        "An incompatible pair is refused unless it is a deliberate exception; " +
        "the refusal names the pair and why.", current);
      if (answer === null) { return; }
      post("/api/v1/principals/" + encodeURIComponent(username) + "/roles",
           {roles: list(answer), allow_conflicts: false}, "PUT")
        .done(reloadShortly)
        .fail(function (xhr) {
          var r = window.MAYA.refusal.read(xhr);
          if (r.code !== "incompatible_roles") {
            say("#np-result", refusal(xhr));
            return;
          }
          /* The one place a second question is worth asking: an incompatible
             pair is sometimes deliberate, and a small firm giving one person
             two hats visibly is better than a hybrid role that hides it. */
          if (window.confirm(r.lines.join("\n") +
                             "\n\nGrant it anyway, as a recorded exception?")) {
            post("/api/v1/principals/" + encodeURIComponent(username) + "/roles",
                 {roles: list(answer), allow_conflicts: true}, "PUT")
              .done(reloadShortly)
              .fail(function (x) { say("#np-result", refusal(x)); });
          } else {
            say("#np-result", refusal(xhr));
          }
        });
    });

    /* ---- set a password ----------------------------------------------- */
    $(".set-password").on("click", function () {
      var username = this.getAttribute("data-username");
      var password = window.prompt(
        "New password for " + username + ".\n\n" +
        "It is never logged and never reaches the evidence chain; the fact " +
        "that somebody set it does.");
      if (!password) { return; }
      post("/api/v1/principals/" + encodeURIComponent(username) + "/password",
           {password: password})
        .done(function () {
          say("#np-result", '<span class="evidence-ok">Password set for ' +
              esc(username) + "</span>");
        })
        .fail(function (xhr) { say("#np-result", refusal(xhr)); });
    });

    /* ---- suspend and reinstate ---------------------------------------- */
    $(".suspend").on("click", function () {
      var username = this.getAttribute("data-username");
      if (!window.confirm("Suspend " + username + "?\n\nThey keep their roles " +
                          "and stop being able to act. Reinstating is a " +
                          "separate act, so this is not a one-way door.")) {
        return;
      }
      post("/api/v1/principals/" + encodeURIComponent(username) + "/suspend", {})
        .done(reloadShortly)
        .fail(function (xhr) { say("#np-result", refusal(xhr)); });
    });

    $(".reinstate").on("click", function () {
      var username = this.getAttribute("data-username");
      post("/api/v1/principals/" + encodeURIComponent(username) + "/reinstate", {})
        .done(reloadShortly)
        .fail(function (xhr) { say("#np-result", refusal(xhr)); });
    });
  });
}());
