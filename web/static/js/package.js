/*
 * MAYA — Model & AI Lifecycle Assurance
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * The model package screen.
 *
 * Two things happen here and they are deliberately different acts. Previewing
 * asks the platform to build a pack, reads its manifest and its gaps file, and
 * throws the bytes away: nothing left, so nothing is recorded. Cutting one is a
 * form POST that navigates, because the answer is a file with a filename and a
 * browser can only take delivery of that from a response whose headers say so —
 * an XHR would hand back bytes nobody could save.
 *
 * The gaps shown are the packer's own words, read out of the pack it built. This
 * file works out nothing about what is missing.
 */
(function () {
  "use strict";

  var form = document.getElementById("pack-form");
  if (!form) { return; }
  var NAME = form.getAttribute("data-name");

  function esc(text) {
    return String(text === null || text === undefined ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function query() {
    /* What the caller narrowed the pack to. `attachments` is 0 or 1 and not a
     * boolean, in the query string as in the register. */
    var kinds = [];
    $(".doc-kind:checked").each(function () { kinds.push(this.value); });
    return "documents=" + encodeURIComponent(kinds.join(",")) +
           "&attachments=" + ($("#with-attachments").is(":checked") ? 1 : 0);
  }

  function refused(x) {
    var e = (x && x.responseJSON) || {};
    return '<div class="border rounded p-2" style="border-color:#A51C30!important">' +
      '<span class="evidence-bad">Refused</span> ' +
      (e.error ? "<code>" + esc(e.error) + "</code> " : "") + "&mdash; " +
      esc(e.detail || (x && x.statusText) || String(x)) +
      (e.remediation ? '<div class="text-muted mt-1">' + esc(e.remediation) +
                       "</div>" : "") + "</div>";
  }

  function stamp(seconds) {
    if (!seconds) { return "—"; }
    return new Date(Number(seconds) * 1000).toISOString().replace(".000Z", "Z");
  }

  $("#preview-pack").on("click", function () {
    $("#pack-result").html('<span class="text-muted">Building a pack to read ' +
      "its manifest…</span>");
    $.get("/packages/" + NAME + "/preview?" + query()).done(function (out) {
      var chain = out.chain || {};
      var html = '<dl class="maya-terms border rounded mb-2">' +
        "<div><dt>Would be called</dt><dd class='mono'>" + esc(out.filename) +
        "</dd></div>" +
        "<div><dt>Content digest</dt><dd class='mono'>" +
        esc(out.content_digest) + "<div class='text-muted'>over every file " +
        "except the manifest — the same for two packs of the same state, so " +
        "this is the number to compare against your last one</div></dd></div>" +
        "<div><dt>Pack digest</dt><dd class='mono'>" + esc(out.pack_digest) +
        "<div class='text-muted'>over the zip itself, which does differ every " +
        "time because the manifest carries the moment it was cut</div></dd></div>" +
        "<div><dt>Chain head</dt><dd>seq " + esc(chain.head_seq) +
        ", <span class='mono'>" + esc(chain.head_hash) + "</span>, verified " +
        esc(chain.verified) + "</dd></div>" +
        "<div><dt>Cut at</dt><dd>" + esc(stamp(out.built_at)) + " by " +
        esc(out.built_by) + "</dd></div>" +
        "<div><dt>Size</dt><dd>" + esc((out.bytes / 1e6).toFixed(2)) + " MB, " +
        esc((out.files || []).length) + " file(s)</dd></div>" +
        "<div><dt>Gaps</dt><dd>" + (out.gaps
          ? '<span class="evidence-bad">' + esc(out.gaps) + " recorded</span>"
          : '<span class="evidence-ok">none</span>') + "</dd></div></dl>";

      html += '<p class="kicker mb-1">' + esc(String(out.detail || "")).toUpperCase() +
        "</p>";
      html += '<table class="table table-sm maya"><thead><tr><th>File</th>' +
        "<th>Bytes</th><th>SHA-256</th></tr></thead><tbody>";
      (out.files || []).forEach(function (f) {
        html += "<tr><td class='mono' style='font-size:.74rem'>" + esc(f.name) +
          "</td><td data-sort='" + esc(f.bytes) + "'>" + esc(f.bytes) +
          "</td><td class='mono' style='font-size:.68rem'>" + esc(f.digest) +
          "</td></tr>";
      });
      html += "</tbody></table>";
      html += '<p class="text-muted" style="font-size:.72rem">' +
        "The zip holds one more member than this table: <code>manifest.json</code> " +
        "itself, which is written last and left out of its own file list for the " +
        "same reason it is left out of the content digest.</p>";
      html += '<p class="kicker mb-1">GAPS.MD, AS THE PACK WILL CARRY IT</p>' +
        '<pre class="mono" style="background:#F4F2EF;padding:.8rem;' +
        'border-radius:.25rem;white-space:pre-wrap">' +
        esc(out.gaps_markdown) + "</pre>";
      $("#pack-result").html(html);
      if (window.mayaEnhanceTables) { window.mayaEnhanceTables(); }
    }).fail(function (x) { $("#pack-result").html(refused(x)); });
  });

  form.addEventListener("submit", function () {
    /* The narrowing travels in the query string rather than in the body: the
     * body carries only the CSRF field csrf.js stamps onto the form, and a
     * route that read a body the middleware had already consumed is a class of
     * bug worth not having. */
    form.action = "/packages/" + NAME + "?" + query();
  });
}());
