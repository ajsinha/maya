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

    /* ---- define a role ------------------------------------------------ */
    $("#new-role").on("submit", function (event) {
      event.preventDefault();
      $.ajax({url: "/api/v1/roles", method: "POST",
              contentType: "application/json",
              data: JSON.stringify({
                name: $("#nr-name").val().trim(),
                description: $("#nr-description").val().trim(),
                permissions: list($("#nr-permissions").val())
              })})
        .done(reloadShortly)
        .fail(function (xhr) { say("#nr-result", refusal(xhr)); });
    });

    /* An inline field backed by the permission picker this page already has,
     * not a prompt. `unknown_permission`'s remediation says "check the
     * spelling against core.authz.common.PERMISSIONS" — a Python module, told
     * to an operations manager — and the datalist of every valid permission
     * was four elements away on the same screen. */
    $(".edit-role").on("click", function () {
      var role = this.getAttribute("data-role");
      var current = this.getAttribute("data-permissions") || "";
      var $row = $(this).closest("tr");
      if ($row.next(".perm-row").length) {
        $row.next(".perm-row").remove();
        return;
      }
      $(".perm-row").remove();
      var $editor = $(
        '<tr class="perm-row"><td colspan="' + $row.children("td").length + '">' +
        '<form class="ep-form row g-2 align-items-end small">' +
        '<div class="col-md-9"><label class="form-label mb-1" for="ep-perms">' +
        "Permissions for <strong>" + esc(role) + "</strong>, comma separated" +
        "</label>" +
        '<input id="ep-perms" class="form-control form-control-sm mono" ' +
        'list="every-permission" value="' + esc(current) + '"></div>' +
        '<div class="col-auto"><button class="btn btn-sm btn-danger py-0 px-3" ' +
        'style="font-size:.75rem">Set them</button></div>' +
        '<div class="col-12 text-muted" style="font-size:.72rem">Every one is ' +
        "checked against the closed set; a role granting something nothing " +
        "checks reads as authority and is not. The box suggests what exists." +
        "</div>" +
        '<div class="col-12" id="ep-msg" role="status" aria-live="polite"></div>' +
        "</form></td></tr>");
      $row.after($editor);
      $editor.find("#ep-perms").trigger("focus");

      $editor.find(".ep-form").on("submit", function (event) {
        event.preventDefault();
        $.ajax({url: "/api/v1/roles/" + encodeURIComponent(role), method: "PUT",
                contentType: "application/json",
                data: JSON.stringify(
                  {permissions: list($editor.find("#ep-perms").val())})})
          .done(reloadShortly)
          .fail(function (xhr) { $editor.find("#ep-msg").html(refusal(xhr)); });
      });
    });

    $(".remove-role").on("click", function () {
      var role = this.getAttribute("data-role");
      var held = Number(this.getAttribute("data-held") || 0);
      /* The register refuses this anyway — a role that stops existing while
         somebody holds it makes their next request resolve against a name that
         is not there. Asked here first so the answer arrives before the click
         rather than after it. */
      if (held > 0) {
        say("#nr-result",
            '<div class="evidence-bad">' + esc(role) + " is held by " + held +
            " principal(s).</div><div class=\"text-muted small\">Change their " +
            "roles first: a role that stops existing while somebody holds it " +
            "makes their next request resolve against a name that is not " +
            "there.</div>");
        return;
      }
      if (!window.confirm("Remove the role " + role + "?")) { return; }
      $.ajax({url: "/api/v1/roles/" + encodeURIComponent(role),
              method: "DELETE"})
        .done(reloadShortly)
        .fail(function (xhr) { say("#nr-result", refusal(xhr)); });
    });

    /* ---- change somebody's roles -------------------------------------- */
    /* Checkboxes in the row, not a comma-separated string in a prompt.
     *
     * The roles are already on this page as a checkbox list in the
     * "Add somebody" card; asking for the same thing as free text meant a typo
     * became `unknown_role` after the fact, and there was nowhere to put the
     * `allow_conflicts` question except a second dialog. */
    $(".edit-roles").on("click", function () {
      var username = this.getAttribute("data-username");
      var held = list(this.getAttribute("data-roles") || "");
      var $row = $(this).closest("tr");
      if ($row.next(".roles-row").length) {
        $row.next(".roles-row").remove();
        return;
      }
      $(".roles-row").remove();
      var boxes = $(".np-role").map(function () {
        var name = this.value;
        var on = held.indexOf(name) !== -1 ? " checked" : "";
        return '<label class="form-check form-check-inline small">' +
          '<input class="form-check-input er-role" type="checkbox" value="' +
          esc(name) + '"' + on + '> <span class="mono">' + esc(name) +
          "</span></label>";
      }).get().join("");
      var $editor = $(
        '<tr class="roles-row"><td colspan="' + $row.children("td").length + '">' +
        '<form class="er-form small">' +
        '<div class="mb-1">Roles for <strong>' + esc(username) + "</strong></div>" +
        boxes +
        '<div class="mt-2"><button class="btn btn-sm btn-danger py-0 px-3" ' +
        'style="font-size:.75rem">Set them</button></div>' +
        '<div class="mt-1" id="er-msg" role="status" aria-live="polite"></div>' +
        "</form></td></tr>");
      $row.after($editor);

      $editor.find(".er-form").on("submit", function (event) {
        event.preventDefault();
        var chosen = $editor.find(".er-role:checked").map(function () {
          return this.value;
        }).get();
        var $msg = $editor.find("#er-msg");
        post("/api/v1/principals/" + encodeURIComponent(username) + "/roles",
             {roles: chosen, allow_conflicts: false}, "PUT")
          .done(reloadShortly)
          .fail(function (xhr) {
            var r = window.MAYA.refusal.read(xhr);
            /* The escalation is offered ONLY for the one refusal it answers.
               Which is a question for the server, not for this file: the
               browser used to decide when `allow_conflicts` was appropriate. */
            if (r.code !== "incompatible_roles") {
              $msg.html(refusal(xhr));
              return;
            }
            $msg.html(refusal(xhr) +
              '<button class="btn btn-sm btn-outline-danger py-0 px-2 mt-2" ' +
              'style="font-size:.72rem" id="er-force">Grant anyway, as a ' +
              "documented exception</button>");
            $editor.find("#er-force").on("click", function () {
              post("/api/v1/principals/" + encodeURIComponent(username) + "/roles",
                   {roles: chosen, allow_conflicts: true}, "PUT")
                .done(reloadShortly)
                .fail(function (second) { $msg.html(refusal(second)); });
            });
          });
      });
    });

    /* ---- set a password ----------------------------------------------- */
    /* An inline form in the row, not `window.prompt`.
     *
     * A prompt shows the password in CLEAR TEXT — to anyone standing behind the
     * administrator, and to any screen recording — has no confirm field, and no
     * room to state the length rule, so the twelve-character floor arrived as a
     * 422 after the fact. It is also unstyleable and cannot be driven by a test.
     */
    var MIN_PASSWORD = 12;

    $(".set-password").on("click", function () {
      var username = this.getAttribute("data-username");
      var $row = $(this).closest("tr");
      if ($row.next(".pw-row").length) {          // a second click closes it
        $row.next(".pw-row").remove();
        return;
      }
      $(".pw-row").remove();
      var columns = $row.children("td").length;
      var $editor = $([
        '<tr class="pw-row"><td colspan="' + columns + '">',
        '<form class="pw-form row g-2 align-items-end small">',
        '<div class="col-auto"><label class="form-label mb-1" for="pw-a">',
        'New password for ', esc(username), '</label>',
        '<input id="pw-a" type="password" class="form-control form-control-sm" ',
        'autocomplete="new-password" required></div>',
        '<div class="col-auto"><label class="form-label mb-1" for="pw-b">Again',
        '</label><input id="pw-b" type="password" ',
        'class="form-control form-control-sm" autocomplete="new-password" required>',
        '</div>',
        '<div class="col-auto"><button class="btn btn-sm btn-danger py-0 px-3" ',
        'style="font-size:.75rem">Set it</button></div>',
        '<div class="col-12 text-muted" style="font-size:.72rem">At least ',
        MIN_PASSWORD, ' characters. It is never logged and never reaches the ',
        'evidence chain; the fact that you set it does.</div>',
        '<div class="col-12" id="pw-msg" role="status" aria-live="polite"></div>',
        '</form></td></tr>'
      ].join(""));
      $row.after($editor);
      $editor.find("#pw-a").trigger("focus");

      $editor.find(".pw-form").on("submit", function (event) {
        event.preventDefault();
        var first = $editor.find("#pw-a").val();
        var again = $editor.find("#pw-b").val();
        var $msg = $editor.find("#pw-msg");
        if (first !== again) {
          $msg.html('<span class="evidence-bad">The two do not match.</span>');
          return;
        }
        /* Stated here as well as enforced there. The rule lives in
           `core.authz.principals`; this is the same number said early, so
           nobody is refused after typing it twice. */
        if (first.length < MIN_PASSWORD) {
          $msg.html('<span class="evidence-bad">At least ' + MIN_PASSWORD +
                    ' characters.</span>');
          return;
        }
        post("/api/v1/principals/" + encodeURIComponent(username) + "/password",
             {password: first})
          .done(function () {
            $editor.remove();
            say("#np-result", '<span class="evidence-ok">Password set for ' +
                esc(username) + "</span>");
          })
          .fail(function (xhr) { $msg.html(refusal(xhr)); });
      });
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
