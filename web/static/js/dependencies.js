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
    $("#deps-form").on("submit", function (event) {
      event.preventDefault();
      var kind = $("#dep-kind").val();
      var id = ($("#dep-id").val() || "").trim();
      if (!id) { return; }
      window.location = "/dependencies?kind=" + encodeURIComponent(kind) +
        "&id=" + encodeURIComponent(id);
    });
  });
}());
