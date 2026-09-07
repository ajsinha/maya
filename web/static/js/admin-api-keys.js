/* MAYA — issuing and revoking API keys from the screen.
 *
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 *
 * The one screen here that shows a secret, and it shows it once. What comes
 * back from `POST /api-keys` is the only time the key exists outside the
 * caller's memory — it is stored as a hash and cannot be recovered — so this
 * puts it where somebody can copy it, says plainly that it will not be shown
 * again, and never writes it anywhere else.
 *
 * Nothing here decides anything: the scope check, the lifetime bound and the
 * suspension check all happen in the register, and this renders what came back.
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

  function list(value) {
    return String(value || "").split(",")
      .map(function (s) { return s.trim(); })
      .filter(function (s) { return s.length > 0; });
  }

  window.jQuery(function ($) {
    $("#new-key").on("submit", function (event) {
      event.preventDefault();
      var body = {
        username: $("#nk-username").val(),
        name: $("#nk-name").val().trim(),
        scopes: list($("#nk-scopes").val()),
        lifetime_days: Number($("#nk-days").val() || 90)
      };
      $.ajax({url: "/api/v1/api-keys", method: "POST",
              contentType: "application/json", data: JSON.stringify(body)})
        .done(function (out) {
          /* Deliberately NOT followed by a reload. Reloading would take the
             secret off the screen before somebody had copied it, and there is
             no second chance — which is the whole property being relied on. */
          $("#nk-result").html(
            '<div class="evidence-ok">Issued. This is the only time the secret ' +
            'is shown.</div>' +
            '<div class="mt-2 p-2 mono" style="border:1px solid var(--edge);' +
            'border-radius:3px;word-break:break-all;font-size:.78rem">' +
            esc(out.secret) + "</div>" +
            '<div class="text-muted small mt-1">Put it where the service will ' +
            'read it from, then reload this page. It is stored as a hash and ' +
            'cannot be recovered.</div>' +
            '<button class="btn btn-sm btn-outline-secondary py-0 px-2 mt-2" ' +
            'style="font-size:.72rem" id="nk-done">I have copied it</button>');
          $("#nk-done").on("click", function () { window.location.reload(); });
        })
        .fail(function (xhr) { $("#nk-result").html(refusal(xhr)); });
    });

    $(".revoke-key").on("click", function () {
      var id = this.getAttribute("data-key");
      var name = this.getAttribute("data-name");
      var reason = window.prompt(
        "Revoke '" + name + "'. Why?\n\n" +
        "An unexplained revocation during an incident is indistinguishable " +
        "from one during a tidy-up.");
      if (!reason) { return; }
      $.ajax({url: "/api/v1/api-keys/" + encodeURIComponent(id) + "/revoke",
              method: "POST", contentType: "application/json",
              data: JSON.stringify({reason: reason})})
        .done(function () { window.location.reload(); })
        .fail(function (xhr) { $("#nk-result").html(refusal(xhr)); });
    });
  });
}());
