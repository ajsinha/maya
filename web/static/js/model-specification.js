/*
 * MAYA — the model specification editor.
 *
 * Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
 * Proprietary and confidential. See LICENSE and NOTICE at the repository root.
 *
 * LaTeX in, rendered mathematics out, filed as a document somebody signs for.
 *
 * What this deliberately does NOT do is store the mathematics beside the
 * kernel. `/api/v1/mathematics` derives the equation from the syntax tree the
 * platform evaluates and stores nothing, precisely so the equation, the code
 * and the answer cannot disagree. A specification is a different artifact — it
 * is prose ABOUT the model, with an author and a reviewer — and the way to keep
 * the two honest is for the prose to QUOTE the derived equation rather than
 * restate it. Hence "Insert the derived equation", which pastes what MAYA
 * computes and marks where it came from.
 *
 * The renderer is KaTeX, vendored under /static/vendor. Nothing here calls out.
 */
(function () {
  "use strict";

  var CONFIG = JSON.parse(
    document.getElementById("maya-spec-config").textContent);

  var SNIPPETS = {
    section: "\n\\section{A heading}\n\n",
    display: "\n$$\n  y = f(x)\n$$\n\n",
    align: "\n$$\n\\begin{aligned}\n  a &= b + c \\\\\n  d &= e - f\n\\end{aligned}\n$$\n\n",
    table: "\n\\begin{tabular}{lr}\n  Term & Value \\\\\n  \\hline\n  alpha & 1.00 \\\\\n  beta  & 2.00 \\\\\n\\end{tabular}\n\n",
    figure: "\n% A chart or diagram: file it as an attachment first, then refer\n% to it by name here. MAYA renders the reference; the image travels with\n% the model in its export pack.\n\\begin{figure}\n  \\caption{What the figure shows}\n  \\label{fig:one}\n\\end{figure}\n\n"
  };

  function esc(text) {
    return String(text === undefined || text === null ? "" : text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  /* A very small LaTeX subset, rendered for PREVIEW only.
   *
   * Not a TeX engine and not pretending to be one: this typesets the
   * mathematics with KaTeX and gives the surrounding prose enough structure to
   * read. The download is the real source, and any TeX toolchain will build it
   * properly — which is the honest division, because a half-implemented TeX
   * that silently differs from the real one is exactly the second description
   * this platform argues against. */
  function render(source) {
    var errors = [];
    var maths = [];

    // Pull the mathematics out first, so prose substitution cannot corrupt it.
    var text = source.replace(/\$\$([\s\S]*?)\$\$/g, function (_, body) {
      maths.push({body: body, display: true});
      return "\u0000MATH" + (maths.length - 1) + "\u0000";
    }).replace(/\$([^$\n]+?)\$/g, function (_, body) {
      maths.push({body: body, display: false});
      return "\u0000MATH" + (maths.length - 1) + "\u0000";
    });

    text = esc(text)
      .replace(/^%.*$/gm, "")
      .replace(/\\section\*?\{([^}]*)\}/g, "<h2>$1</h2>")
      .replace(/\\subsection\*?\{([^}]*)\}/g, "<h3>$1</h3>")
      .replace(/\\textbf\{([^}]*)\}/g, "<strong>$1</strong>")
      .replace(/\\emph\{([^}]*)\}|\\textit\{([^}]*)\}/g, "<em>$1$2</em>")
      .replace(/\\texttt\{([^}]*)\}/g, '<code class="mono">$1</code>')
      .replace(/\\begin\{itemize\}/g, "<ul>").replace(/\\end\{itemize\}/g, "</ul>")
      .replace(/\\begin\{enumerate\}/g, "<ol>").replace(/\\end\{enumerate\}/g, "</ol>")
      .replace(/\\item\s*/g, "<li>")
      .replace(/\\caption\{([^}]*)\}/g, '<div class="text-muted small">$1</div>')
      .replace(/\\(begin|end)\{(figure|tabular|document|aligned)\}[^\n]*/g, "")
      .replace(/\\label\{[^}]*\}/g, "")
      .replace(/\\documentclass[^\n]*/g, "")
      .replace(/\n{2,}/g, "</p><p>");

    text = "<p>" + text + "</p>";

    text = text.replace(/\u0000MATH(\d+)\u0000/g, function (_, index) {
      var item = maths[Number(index)];
      try {
        return window.katex.renderToString(item.body.trim(), {
          displayMode: item.display, throwOnError: true, strict: false
        });
      } catch (err) {
        errors.push(err.message.split("\n")[0]);
        return '<span class="evidence-bad mono" style="font-size:.8rem">' +
          esc(item.body.trim()) + "</span>";
      }
    });
    return {html: text, errors: errors, count: maths.length};
  }

  window.jQuery(function ($) {
    var $source = $("#tex-source");
    var $preview = $("#tex-preview");
    var $status = $("#tex-status");

    function draw() {
      var out = render($source.val() || "");
      $preview.html(out.html);
      if (out.errors.length) {
        $status.attr("class", "small evidence-bad")
               .text(out.errors.length + " expression" +
                     (out.errors.length === 1 ? "" : "s") +
                     " will not typeset: " + out.errors[0]);
      } else {
        $status.attr("class", "small text-muted")
               .text(out.count + " expression" + (out.count === 1 ? "" : "s"));
      }
    }

    var pending = null;
    $source.on("input", function () {
      window.clearTimeout(pending);
      pending = window.setTimeout(draw, 180);
    });
    draw();

    function insert(text) {
      var el = $source[0];
      var at = el.selectionStart || 0;
      var value = el.value;
      el.value = value.slice(0, at) + text + value.slice(el.selectionEnd || at);
      el.selectionStart = el.selectionEnd = at + text.length;
      el.focus();
      draw();
    }

    $("[data-snippet]").on("click", function () {
      insert(SNIPPETS[this.getAttribute("data-snippet")] || "");
    });

    /* The derived equation, quoted rather than retyped — and marked, so a
       reader knows which half of this document MAYA computed. */
    $("#insert-derived").on("click", function () {
      var latex = this.getAttribute("data-latex");
      var expression = this.getAttribute("data-expression");
      var target = this.getAttribute("data-target");
      insert("\n% Derived by MAYA from the version's kernel. Do not edit: it is\n" +
             "% regenerated from the expression the platform evaluates, so an\n" +
             "% edit here would be a second description of one model.\n" +
             "$$\n  \\mathrm{" + target + "} = " + latex + "\n$$\n" +
             "\\texttt{" + expression + "}\n\n");
    });

    /* ---- file it ------------------------------------------------------- */
    $("#spec-form").on("submit", function (event) {
      event.preventDefault();
      var $out = $("#spec-result");
      var body = new FormData();
      var title = $("#spec-title").val();
      body.append("urn", CONFIG.urn);
      body.append("kind", $("#spec-kind").val());
      body.append("title", title);
      if ($("#spec-semver").val()) { body.append("semver", $("#spec-semver").val()); }
      body.append("file", new Blob([$source.val()], {type: "text/x-tex"}),
                  title.replace(/[^A-Za-z0-9._-]+/g, "-").toLowerCase() + ".tex");

      $out.html('<span class="text-muted">filing…</span>');
      $.ajax({url: "/api/v1/attachments", method: "POST",
              data: body, processData: false, contentType: false})
        .done(function (filed) {
          $out.html('<span class="evidence-ok">Filed as ' + esc(filed.title) +
                    "</span> <span class='text-muted'>&mdash; awaiting review; " +
                    "digest " + esc(filed.digest.slice(0, 22)) + "…</span>");
          window.setTimeout(function () { window.location.reload(); }, 1500);
        })
        .fail(function (xhr) {
          var r = window.MAYA.refusal.read(xhr);
          $out.html('<span class="evidence-bad">' +
                    esc(r.lines.join(" ") || "refused") + "</span>" +
                    (r.remediation
                      ? '<div class="text-muted small">' + esc(r.remediation) + "</div>"
                      : ""));
        });
    });

    /* ---- open something already filed ---------------------------------- */
    $(".load-spec").on("click", function () {
      var id = this.getAttribute("data-id");
      $.ajax({url: "/api/v1/attachments/" + encodeURIComponent(id) + "/content",
              dataType: "text"})
        .done(function (text) { $source.val(text); draw(); $source.focus(); })
        .fail(function (xhr) {
          $("#spec-result").html('<span class="evidence-bad">' +
            esc(window.MAYA.refusal.read(xhr).lines.join(" ")) + "</span>");
        });
    });

    /* ---- take it away --------------------------------------------------- */
    $("#download-tex").on("click", function () {
      var blob = new Blob([$source.val()], {type: "text/x-tex"});
      var url = window.URL.createObjectURL(blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = (CONFIG.name || "model").replace(/[^A-Za-z0-9._-]+/g, "-")
        .toLowerCase() + "-specification.tex";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    });

    $("#print-pdf").on("click", function () { window.print(); });
  });
}());
