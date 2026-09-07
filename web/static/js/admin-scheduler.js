/* MAYA — run the governance batch from the screen that reports on it.
 *
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 *
 * The page had no button and no form: its closing line told the administrator
 * to POST to an endpoint. `config/application.yaml` instructs the deployer to
 * "check /admin/scheduler afterwards to confirm it arrived" — so the one screen
 * the configuration names as the place to confirm the batch is running could
 * not run it, and an administrator who wanted to had to leave the product.
 */
(function () {
  "use strict";

  window.jQuery(function ($) {
    var $button = $("#run-all");
    if (!$button.length) { return; }
    var $out = $("#run-result");

    $button.on("click", function () {
      $button.prop("disabled", true);
      $out.attr("class", "ms-2 small text-muted").text("running…");
      $.ajax({
        url: "/api/v1/scheduler/run", method: "POST",
        contentType: "application/json", data: JSON.stringify({})
      }).done(function (body) {
        var failed = body.failed || 0;
        $out.attr("class", "ms-2 small " +
                  (failed ? "evidence-bad" : "evidence-ok"))
            .text(body.ran + " job" + (body.ran === 1 ? "" : "s") + " ran, " +
                  failed + " failed. Reloading…");
        window.setTimeout(function () { window.location.reload(); }, 900);
      }).fail(function (xhr) {
        var r = window.MAYA.refusal.read(xhr);
        $out.attr("class", "ms-2 small evidence-bad")
            .text(r.lines.join(" ") || "the run was refused");
        $button.prop("disabled", false);
      });
    });
  });
}());
