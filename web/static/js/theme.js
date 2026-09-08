/*
 * MAYA — light, dark, or whatever the machine says.
 *
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Three states rather than two. "System" is the default and is a POSITION, not
 * the absence of a choice: somebody who has set their machine to switch at
 * dusk should not have to correct this platform twice a day, and a two-way
 * toggle cannot express that.
 *
 * The stylesheet does the work. `data-theme` on <html> selects a block of
 * custom properties and every colour on every screen resolves through one of
 * them, so this file sets one attribute and stores one string.
 *
 * Applied in <head>, before the first paint — see the inline snippet in
 * base.html. Waiting for DOMContentLoaded would show a white page to somebody
 * who chose dark, which is the flash this whole indirection exists to avoid.
 */
(function () {
  "use strict";

  var KEY = "maya.theme";
  var CHOICES = {light: 1, dark: 1, system: 1};

  function stored() {
    try {
      var value = window.localStorage.getItem(KEY);
      return CHOICES[value] ? value : "system";
    } catch (err) {
      return "system";            // private browsing, or storage disabled
    }
  }

  function apply(choice) {
    if (choice === "system") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", choice);
    }
  }

  function remember(choice) {
    try { window.localStorage.setItem(KEY, choice); } catch (err) { /* fine */ }
  }

  apply(stored());

  window.jQuery(function ($) {
    function mark() {
      var current = stored();
      $(".theme-pick").each(function () {
        var mine = this.getAttribute("data-theme") === current;
        $(this).attr("aria-current", mine ? "true" : null)
               .find(".tick").html(mine ? '<i class="bi bi-check2"></i>' : "");
      });
    }
    mark();

    $(".theme-pick").on("click", function () {
      var choice = this.getAttribute("data-theme");
      apply(choice);
      remember(choice);
      mark();
    });
  });

  window.mayaTheme = {get: stored, set: function (choice) {
    if (!CHOICES[choice]) { return; }
    apply(choice); remember(choice);
  }};
}());
