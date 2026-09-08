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
 *
 * TEXT SIZE works the same way and for the same reasons. It is a separate
 * control rather than a reliance on the browser's zoom, because zoom scales
 * the LAYOUT — a governance table at 150% zoom is a table nobody can see a row
 * of — where this scales only the type, against the root font size, so every
 * `rem` on every screen moves together and the proportions somebody designed
 * stay the proportions they see. Stored, so it survives the next machine.
 */
(function () {
  "use strict";

  var KEY = "maya.theme";
  var CHOICES = {light: 1, dark: 1, system: 1};
  var TEXT_KEY = "maya.text";
  var SIZES = {small: 1, normal: 1, large: 1, larger: 1, largest: 1};

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

  function storedText() {
    try {
      var value = window.localStorage.getItem(TEXT_KEY);
      return SIZES[value] ? value : "normal";
    } catch (err) {
      return "normal";
    }
  }

  function applyText(choice) {
    /* "normal" removes the attribute rather than setting it, so the default
       is the absence of a choice and the stylesheet's own value stands. A
       `data-text="normal"` would be a third thing to keep in step. */
    if (choice === "normal") {
      document.documentElement.removeAttribute("data-text");
    } else {
      document.documentElement.setAttribute("data-text", choice);
    }
  }

  function rememberText(choice) {
    try { window.localStorage.setItem(TEXT_KEY, choice); } catch (err) { /* fine */ }
  }

  apply(stored());
  applyText(storedText());

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

    function markText() {
      var current = storedText();
      $(".text-pick").each(function () {
        var mine = this.getAttribute("data-text") === current;
        $(this).attr("aria-current", mine ? "true" : null)
               .find(".tick").html(mine ? '<i class="bi bi-check2"></i>' : "");
      });
    }
    markText();

    $(".text-pick").on("click", function () {
      var choice = this.getAttribute("data-text");
      applyText(choice);
      rememberText(choice);
      markText();
    });
  });

  window.mayaTheme = {get: stored, set: function (choice) {
    if (!CHOICES[choice]) { return; }
    apply(choice); remember(choice);
  }};

  window.mayaText = {get: storedText, set: function (choice) {
    if (!SIZES[choice]) { return; }
    applyText(choice); rememberText(choice);
  }};
}());
