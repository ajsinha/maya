/* MAYA — the dependency view.
 *
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 *
 * A form that navigates. The answer comes from `GET /references`, which is the
 * same index a delete consults — so what this screen says is safe to remove and
 * what the register will actually allow cannot differ.
 */
(function () {
  "use strict";
  window.jQuery(function ($) {
    /* The suggestions follow the Kind select. There was no change handler at
       all, so landing here and switching to "feature" left the box offering
       model urns — on a screen where a name that does not match anything used
       to answer "nothing refers to this". */
    $("#dep-kind").on("change", function () {
      $("#dep-id").attr("list", "dep-suggestions-" + $(this).val());
    });

    $("#deps-form").on("submit", function (event) {
      event.preventDefault();
      var kind = $("#dep-kind").val();
      var id = ($("#dep-id").val() || "").trim();
      /* Clicking Look with the box empty did nothing at all — no message, no
         navigation, which reads as a broken button rather than a question with
         no subject. */
      if (!id) {
        $("#deps-result").html(
          '<div class="card mb-3"><div class="card-body py-3 small">' +
          '<span class="evidence-bad">Name something to look up.</span> ' +
          '<span class="text-muted">Type a model urn, a feature or a ' +
          'featureset — the box suggests what exists.</span></div></div>');
        $("#dep-id").trigger("focus");
        return;
      }
      window.location = "/dependencies?kind=" + encodeURIComponent(kind) +
        "&id=" + encodeURIComponent(id);
    });
  });
}());
