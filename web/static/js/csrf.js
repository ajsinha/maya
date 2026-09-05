/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * Attach the session's CSRF token to every state-changing request.
 *
 * Done once, here, rather than at each of the several dozen call sites that
 * post from a page. A control every caller has to remember is a control that
 * will be missing from the one added next week, and the failure would look like
 * a permissions bug rather than an omission.
 *
 * Same-origin only. The token authorises OUR pages to act under an ambient
 * cookie; sending it to somebody else's host would hand them the thing it
 * exists to withhold.
 */
(function () {
  "use strict";

  var meta = document.querySelector('meta[name="csrf-token"]');
  var token = meta ? meta.getAttribute("content") : "";
  var SAFE = /^(GET|HEAD|OPTIONS)$/i;

  function sameOrigin(url) {
    if (!url) { return true; }                    // a relative path is ours
    if (/^https?:\/\//i.test(url) || url.indexOf("//") === 0) {
      var a = document.createElement("a");
      a.href = url;
      return a.host === window.location.host && a.protocol === window.location.protocol;
    }
    return true;
  }

  if (window.jQuery) {
    jQuery.ajaxSetup({
      beforeSend: function (xhr, settings) {
        if (!SAFE.test(settings.type || "GET") && sameOrigin(settings.url) && token) {
          xhr.setRequestHeader("X-MAYA-CSRF", token);
        }
      }
    });
  }

  // fetch() is not used by the pages today, but a page added later will reach
  // for it, and the wrapper means that page works rather than 403s in a way
  // whoever wrote it would spend an afternoon on.
  if (window.fetch) {
    var original = window.fetch;
    window.fetch = function (input, init) {
      var options = init || {};
      var method = options.method || (typeof input === "object" && input.method) || "GET";
      var url = (typeof input === "string") ? input : (input && input.url);
      if (!SAFE.test(method) && sameOrigin(url) && token) {
        var headers = new Headers(options.headers || (typeof input === "object" && input.headers) || {});
        headers.set("X-MAYA-CSRF", token);
        options = Object.assign({}, options, {headers: headers});
      }
      return original.call(window, input, options);
    };
  }

  // Any form that posts gets a hidden field, because a form submit carries no
  // headers. Done at load and again for anything added later by a page.
  function stampForms(root) {
    var forms = (root || document).querySelectorAll('form[method="post"], form[method="POST"]');
    Array.prototype.forEach.call(forms, function (form) {
      if (form.querySelector('input[name="csrf_token"]')) { return; }
      var field = document.createElement("input");
      field.type = "hidden";
      field.name = "csrf_token";
      field.value = token;
      form.appendChild(field);
    });
  }

  document.addEventListener("DOMContentLoaded", function () { stampForms(document); });
  window.mayaStampForms = stampForms;
}());
