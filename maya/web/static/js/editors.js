/*
 * editors.js — the embedded editors (spec §17).
 * CodeMirror 5 (single-file, vendored) is used rather than CodeMirror 6 because
 * CM6 ships only as ES modules that need a bundler, and MAYA has no build
 * pipeline (§16). Same capabilities for our needs: highlighting, indentation,
 * bracket matching.
 *   textarea[data-editor=python|stex]   upgraded to CodeMirror
 *   textarea[data-preview=<id>]         live LaTeX preview into #id within ~200 ms:
 *                                       \section → headings, $…$ and \[…\] via KaTeX,
 *                                       \mayaformula{…} shown as the model's rendered IR
 * If CodeMirror or KaTeX failed to load, the plain textarea and raw LaTeX remain.
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';

  function escapeHtml(s) {
    return s.replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; });
  }

  function math(tex, display) {
    if (!window.katex) { return '<code>' + escapeHtml(tex) + '</code>'; }
    try { return window.katex.renderToString(tex, { displayMode: display, throwOnError: false }); }
    catch (e) { return '<code>' + escapeHtml(tex) + '</code>'; }
  }

  function renderLatexDoc(src, formula) {
    var body = src.replace(/%.*$/gm, '');
    var m = body.match(/\\begin\{document\}([\s\S]*?)\\end\{document\}/);
    if (m) { body = m[1]; }
    body = body.replace(/\\mayaformula\{[^}]*\}/g, function () {
      return formula ? '\\[' + formula + '\\]' : '\\[\\text{(formula IR not set)}\\]';
    });
    var html = [];
    body.split(/\n\s*\n/).forEach(function (para) {
      var p = para.trim();
      if (!p) { return; }
      p = p.replace(/\\maketitle|\\tableofcontents/g, '');
      var sec = p.match(/^\\(sub)?section\*?\{([^}]*)\}([\s\S]*)$/);
      if (sec) {
        html.push((sec[1] ? '<h5>' : '<h4>') + escapeHtml(sec[2]) + (sec[1] ? '</h5>' : '</h4>'));
        p = sec[3].trim();
        if (!p) { return; }
      }
      var out = '', rest = p, re = /\\\[([\s\S]*?)\\\]|\$\$([\s\S]*?)\$\$|\$([^$]+)\$/;
      var mm;
      while ((mm = re.exec(rest))) {
        out += escapeHtml(rest.slice(0, mm.index).replace(/\\(textbf|emph|textit)\{([^}]*)\}/g, '$2'));
        out += mm[1] !== undefined ? math(mm[1], true) : mm[2] !== undefined ? math(mm[2], true) : math(mm[3], false);
        rest = rest.slice(mm.index + mm[0].length);
      }
      out += escapeHtml(rest.replace(/\\(textbf|emph|textit)\{([^}]*)\}/g, '$2'));
      html.push('<p>' + out + '</p>');
    });
    return html.join('\n');
  }

  function wirePreview(ta, cm) {
    var target = document.getElementById(ta.getAttribute('data-preview'));
    if (!target) { return; }
    var formula = target.getAttribute('data-formula') || '';
    var timer = null;
    function update() { target.innerHTML = renderLatexDoc(cm ? cm.getValue() : ta.value, formula); }
    function schedule() { clearTimeout(timer); timer = setTimeout(update, 180); }
    if (cm) { cm.on('change', schedule); } else { ta.addEventListener('input', schedule); }
    update();
  }

  document.querySelectorAll('textarea[data-editor]').forEach(function (ta) {
    var cm = null;
    if (window.CodeMirror) {
      cm = window.CodeMirror.fromTextArea(ta, {
        mode: ta.getAttribute('data-editor') === 'python' ? 'python' : 'stex',
        lineNumbers: true, indentUnit: 4, matchBrackets: true, lineWrapping: true,
        readOnly: ta.hasAttribute('readonly')
      });
      cm.on('change', function () { cm.save(); });
      // A CodeMirror inside a hidden tab measures zero width; refresh when shown.
      document.querySelectorAll('[data-bs-toggle="tab"]').forEach(function (btn) {
        btn.addEventListener('shown.bs.tab', function () { cm.refresh(); });
      });
      var sel = document.querySelector('select[data-toggle-show]');
      if (sel) { sel.addEventListener('change', function () { setTimeout(function () { cm.refresh(); }, 50); }); }
    }
    if (ta.hasAttribute('data-preview')) { wirePreview(ta, cm); }
  });
})();
