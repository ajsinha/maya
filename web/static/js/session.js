/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * What happens when the session has lapsed under somebody mid-task.
 *
 * Nothing anywhere handled a 401 from a page. Fill in a form after the
 * eight-hour cookie expires and the answer was the API's own refusal — "sign
 * in, present HTTP Basic credentials, or send an API key as
 * `Authorization: Bearer maya_sk_…`" — rendered into a result div. That is
 * correct for a script and useless to a person in a browser, who cannot present
 * Basic credentials and has no API key; and reloading to sign in loses whatever
 * they had typed.
 *
 * Done once, here, for the same reason the CSRF token is: a control every
 * caller has to remember is one the next page will not have.
 *
 * It does NOT touch 403. A refusal about permissions is a real answer that the
 * page should render, and bouncing somebody to a sign-in they are already past
 * would hide it.
 */
(function () {
  "use strict";

  var LOGIN = "/login";
  var announced = false;

  function signInAgain() {
    if (announced) { return; }                 // one banner, however many calls
    announced = true;

    var banner = document.createElement("div");
    banner.setAttribute("role", "alert");
    banner.style.cssText =
      "position:fixed;left:0;right:0;top:0;z-index:3000;padding:.8rem 1rem;" +
      "background:#A51C30;color:#fff;font-size:.9rem;text-align:center;";
    banner.innerHTML =
      "Your session has expired. " +
      '<a href="#" id="maya-signin" style="color:#fff;text-decoration:underline">' +
      "Sign in again</a> — this page stays as it is until you do, so nothing " +
      "you have typed is lost.";
    document.body.appendChild(banner);

    document.getElementById("maya-signin").addEventListener("click", function (e) {
      e.preventDefault();
      /* `next` so signing in returns to the page they were on rather than the
         dashboard, which is the difference between resuming and starting
         again. */
      window.location = LOGIN + "?next=" +
        encodeURIComponent(window.location.pathname + window.location.search);
    });
  }

  if (window.jQuery) {
    window.jQuery(document).ajaxError(function (event, xhr) {
      if (xhr && xhr.status === 401) { signInAgain(); }
    });
  }

  if (window.fetch) {
    var original = window.fetch;
    window.fetch = function (input, options) {
      return original.call(window, input, options).then(function (response) {
        if (response && response.status === 401) { signInAgain(); }
        return response;
      });
    };
  }

  window.mayaSessionExpired = signInAgain;      // for a page that checks itself
}());
