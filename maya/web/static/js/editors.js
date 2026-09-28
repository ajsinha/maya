/*
 * editors.js — the embedded editors (spec §17).
 *
 * CodeMirror 5 (single-file, vendored) rather than CodeMirror 6, because CM6 ships
 * only as ES modules that need a bundler and MAYA has no build pipeline (§16).
 *   textarea[data-editor=python|stex]   upgraded to CodeMirror
 *   textarea[data-preview=<id>]         live LaTeX preview into #id within ~200 ms:
 *                                       \section → headings wherever they stand, lists,
 *                                       display maths, $…$ and \[…\] via KaTeX,
 *                                       \mayaformula{…} as the model's rendered IR,
 *                                       figures as images and \cite{…} numbered; a table
 *                                       or an unknown environment is named as skipped,
 *                                       and no command is ever shown as literal text
 *   [data-outline-for=<id>]             a section outline with a completeness mark
 *   [data-bib-for=<id>]                 the BibTeX pane
 *   [data-checks-for=<id>]              what the validation ladder would say, early
 *
 * What this file adds beyond highlighting, and why it is written here rather than
 * vendored: CodeMirror's own search and matchbrackets add-ons are not in the vendor
 * tree, and MAYA cannot fetch them at build time because there is no build. Both are
 * small, so both are written against CodeMirror's public API:
 *   bracket matching   the pair under the cursor is marked, an unmatched one flagged
 *   find and replace   Ctrl-F / Cmd-F, next, replace, replace all, with a count
 *   spell check        the browser's own dictionary, through a contenteditable input,
 *                      on prose only — a code editor underlining every identifier is
 *                      noise, not help
 *   figures            an image is embedded in the document itself as base64 comment
 *                      lines, so it versions, diffs and travels with the source
 *   bibliography       BibTeX kept in a `filecontents*` block, cited live in the preview
 *
 * A language server is a seam, not a feature: window.MayaEditors.languageServer may be
 * set to {diagnose(source) -> [{line, message}]} and the checks panel will use it.
 * The built-in default mirrors rung 4 of the §17.2 ladder (no filesystem, subprocess,
 * socket, eval or exec) so a designer sees it before the sandbox does. The sandbox,
 * not the browser, has the last word.
 *
 * If CodeMirror or KaTeX failed to load, the plain textarea and raw LaTeX remain.
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
 */
(function () {
  'use strict';

  var FIGURE_LIMIT = 200 * 1024;   // a chart, not a photograph
  var CHUNK = 76;                  // base64 characters per comment line

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function math(tex, display) {
    if (!window.katex) { return '<code>' + escapeHtml(tex) + '</code>'; }
    try { return window.katex.renderToString(tex, { displayMode: display, throwOnError: false }); }
    catch (e) { return '<code>' + escapeHtml(tex) + '</code>'; }
  }

  // ---- figures: the image travels inside the document ---------------------------
  // % maya-figure <name>
  // %~<base64…>            (one or more lines)
  // % maya-figure-end
  var FIG_START = /^%\s*maya-figure\s+(\S+)\s*$/;
  var FIG_DATA = /^%~(.*)$/;
  var FIG_END = /^%\s*maya-figure-end\s*$/;
  var MIMES = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif', svg: 'image/svg+xml', webp: 'image/webp' };

  function mimeOf(name) {
    return MIMES[String(name).split('.').pop().toLowerCase()] || 'application/octet-stream';
  }

  function figures(src) {
    var out = {}, name = null, buf = [];
    String(src).split('\n').forEach(function (line) {
      var start = line.match(FIG_START);
      if (start) { name = start[1]; buf = []; return; }
      if (name && FIG_END.test(line)) {
        out[name] = 'data:' + mimeOf(name) + ';base64,' + buf.join('');
        name = null;
        return;
      }
      var data = name && line.match(FIG_DATA);
      if (data) { buf.push(data[1]); }
    });
    return out;
  }

  function figureBlock(name, base64) {
    var lines = ['% maya-figure ' + name];
    for (var i = 0; i < base64.length; i += CHUNK) { lines.push('%~' + base64.slice(i, i + CHUNK)); }
    lines.push('% maya-figure-end');
    var stem = name.replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9_-]/g, '_');
    // \IfFileExists so the document builds wherever it is taken: where the typesetter
    // writes the embedded image out, the figure appears; where it does not, the build
    // succeeds and prints a labelled box saying where the image is. The capability
    // degrades, the document does not break (§13.4.3).
    lines.push('\\begin{figure}[h]', '\\centering',
      '\\IfFileExists{' + name + '}%',
      '  {\\includegraphics[width=0.8\\textwidth]{' + name + '}}%',
      '  {\\fbox{\\parbox{0.8\\textwidth}{\\centering Figure \\texttt{' +
        name.replace(/_/g, '\\_') + '} is embedded in this document’s source; ' +
        'this build could not write it out.}}}',
      '\\caption{' + stem.replace(/_/g, ' ') + '}', '\\label{fig:' + stem + '}',
      '\\end{figure}', '');
    return lines.join('\n');
  }

  // ---- BibTeX: kept in the document, cited live in the preview -------------------
  var BIB_BLOCK = /\\begin\{filecontents\*?\}(?:\[[^\]]*\])?\{refs\.bib\}([\s\S]*?)\\end\{filecontents\*?\}/;

  function bibOf(src) {
    var m = String(src).match(BIB_BLOCK);
    return m ? m[1].trim() : '';
  }

  function parseBib(text) {
    var entries = [], re = /@(\w+)\s*\{\s*([^,]+),([\s\S]*?)\n\s*\}/g, m;
    while ((m = re.exec(text))) {
      var fields = {}, fre = /(\w+)\s*=\s*[{"]([\s\S]*?)["}]\s*,?\s*(?=\n|$)/g, f;
      while ((f = fre.exec(m[3]))) { fields[f[1].toLowerCase()] = f[2].replace(/\s+/g, ' ').trim(); }
      entries.push({ key: m[2].trim(), type: m[1].toLowerCase(), fields: fields });
    }
    return entries;
  }

  function bibLine(e) {
    var f = e.fields;
    var bits = [f.author, f.title ? '<em>' + escapeHtml(f.title) + '</em>' : '', f.journal || f.booktitle || f.publisher, f.year];
    return bits.filter(Boolean).map(function (b) {
      return b.indexOf('<em>') === 0 ? b : escapeHtml(b);
    }).join(', ') + '.';
  }

  function withBib(src, bib) {
    var block = '\\begin{filecontents*}[overwrite]{refs.bib}\n' + bib.trim() + '\n\\end{filecontents*}';
    if (BIB_BLOCK.test(src)) { return src.replace(BIB_BLOCK, block); }
    var tail = '\n\n\\bibliographystyle{plain}\n\\bibliography{refs}\n';
    return block + '\n' + src.replace(/\s*$/, '') + (src.indexOf('\\bibliography{') > -1 ? '\n' : tail);
  }

  // ---- the preview --------------------------------------------------------------
  // The preview's promise to the reader: it never shows a backslash command as text.
  // A specification is read by a validator and an auditor, and a stray \section in the
  // pane reads as a broken document rather than as an unsupported construct, so what
  // cannot be typeset here is either reduced to its words or named as skipped.

  // An escaped character is set aside before anything else looks at the text: without
  // this, \$ opens inline maths and the rest of the paragraph is swallowed as a formula.
  var ESCAPABLE = '%&_#${}';
  var MARK = '\u0001';

  function setAside(text) {
    return text.replace(/\\([%&_#$\{\}])/g, function (_, c) {
      return MARK + ESCAPABLE.indexOf(c) + MARK;
    });
  }

  function restore(text, asLatex) {
    return text.replace(/\u0001(\d)\u0001/g, function (_, d) {
      var c = ESCAPABLE.charAt(parseInt(d, 10));
      return asLatex ? '\\' + c : (c === '&' ? '&amp;' : c);
    });
  }

  // A command's argument is brace-counted rather than taken as [^}]*, because a section
  // title or an emphasis may itself contain braces.
  function braceArg(s, at) {
    var depth = 0, i = at;
    while (i < s.length) {
      var c = s.charAt(i);
      if (c === '\\') { i += 2; continue; }
      if (c === '{') { depth += 1; }
      else if (c === '}') {
        depth -= 1;
        if (depth === 0) { return { text: s.slice(at + 1, i), end: i + 1 }; }
      }
      i += 1;
    }
    return { text: s.slice(at + 1), end: s.length };   // unbalanced: take what there is
  }

  // Commands whose argument is typesetting machinery rather than something to read. The
  // preamble ones matter because a fragment without \begin{document} is a legal source
  // for this pane, and \usepackage{amsmath} must not appear as the word "amsmath".
  var DROPPED = {
    label: 1, index: 1, vspace: 1, hspace: 1, begin: 1, end: 1, documentclass: 1,
    usepackage: 1, geometry: 1, title: 1, author: 1, date: 1, newcommand: 1,
    renewcommand: 1, providecommand: 1, setlength: 1, addtolength: 1, pagestyle: 1,
    thispagestyle: 1, hypersetup: 1, bibliographystyle: 1, bibliography: 1,
    input: 1, include: 1, nocite: 1
  };
  var ARITY = {
    setlength: 2, addtolength: 2, newcommand: 2, renewcommand: 2, providecommand: 2,
    href: 2, textcolor: 2
  };
  var CODEISH = { texttt: 1, url: 1, path: 1, lstinline: 1 };

  // Plain text between commands. Braces that survive here are grouping ({\bf x}), a tie
  // is the space it stands for, and a lone backslash is dropped so none reaches the page.
  function plain(text) {
    return escapeHtml(text.replace(/~/g, '\u00a0').replace(/[{}]/g, '').replace(/\\/g, ''));
  }

  // Every command left in a run of prose. A known one renders, an unknown one is reduced
  // to its argument, and one with no argument disappears. That last pair of rules is the
  // point of the exercise: whatever the source invents, the reader sees words.
  function prose(text) {
    var out = '', at = 0, re = /\\(?:([a-zA-Z]+)\*?|(.))/g, m;
    while ((m = re.exec(text))) {
      out += plain(text.slice(at, m.index));
      at = re.lastIndex;
      if (m[2] !== undefined) {
        // \\, \, and \; are spacing, with nothing in them to read; \\[6pt] carries a skip
        if (m[2] === '\\' && text.charAt(at) === '[') {
          var close = text.indexOf(']', at);
          if (close > -1) { at = close + 1; }
        }
        re.lastIndex = at;
        continue;
      }
      var name = m[1], arity = ARITY[name] || 1, args = [], i = at;
      while (args.length < arity) {
        var j = i;
        if (text.charAt(j) === '[') {
          var end = text.indexOf(']', j);
          if (end < 0) { break; }
          j = end + 1;                              // an optional argument, as in \newcommand
        }
        if (text.charAt(j) !== '{') { break; }
        var arg = braceArg(text, j);
        args.push(arg.text);
        i = arg.end;
      }
      at = i;
      re.lastIndex = at;
      if (/^(eq)?ref$/.test(name) || name === 'pageref') { out += '[' + plain(args[0] || '') + ']'; }
      else if (DROPPED[name]) { continue; }
      else if (CODEISH[name]) { out += '<code>' + prose(args[0] || '') + '</code>'; }
      else if (name === 'href') { out += prose(args[1] === undefined ? args[0] || '' : args[1]); }
      else { out += prose(args[0] === undefined ? '' : args[0]); }
    }
    return out + plain(text.slice(at));
  }

  var MATHS = /\\\[([\s\S]*?)\\\]|\$\$([\s\S]*?)\$\$|\\\(([\s\S]*?)\\\)|\$([^$]+)\$/;

  function inlineHtml(text, citation) {
    var src = setAside(String(text).replace(/\\cite[tp]?(?:\[[^\]]*\])?\{([^}]*)\}/g,
      function (_, keys) { return citation(keys); }));
    var out = '', rest = src, m;
    while ((m = MATHS.exec(rest))) {
      out += prose(rest.slice(0, m.index));
      var tex = m[1] !== undefined ? m[1] : m[2] !== undefined ? m[2]
        : m[3] !== undefined ? m[3] : m[4];
      out += math(restore(tex, true), m[4] === undefined);
      rest = rest.slice(m.index + m[0].length);
    }
    return restore(out + prose(rest), false);
  }

  // KaTeX with errors thrown rather than drawn, so a caller can fall back to something
  // simpler instead of showing the reader a red error where the maths should be.
  function strictMath(tex) {
    if (!window.katex) { return null; }
    try { return window.katex.renderToString(tex, { displayMode: true, throwOnError: true }); }
    catch (e) { return null; }
  }

  // ---- environments -------------------------------------------------------------
  var LIST = { itemize: 'ul', enumerate: 'ol', description: 'ul' };
  var MATHS_ENV = {
    equation: 1, align: 1, gather: 1, multline: 1, alignat: 1, eqnarray: 1,
    displaymath: 1, split: 1, aligned: 1, gathered: 1
  };
  // Environments that only arrange what is inside them: the contents are prose and go
  // back into the paragraph stream rather than becoming a block of their own.
  var TRANSPARENT = { center: 1, flushleft: 1, flushright: 1, quote: 1, quotation: 1, abstract: 1, sloppypar: 1 };
  var VERBATIM = { verbatim: 1, lstlisting: 1, minted: 1, alltt: 1 };
  var ENV = /\\begin\{([A-Za-z]+\*?)\}(?:\[[^\]]*\])?((?:(?!\\begin\{)[\s\S])*?)\\end\{\1\}/;
  var ENV_LIMIT = 500;

  function listHtml(name, inner, inline) {
    var tag = LIST[name];
    // \item is the separator, so whatever precedes the first one is the environment's
    // own preamble and has nothing to do with the items.
    var items = inner.split(/\\item\b/).slice(1);
    return '<' + tag + '>' + items.map(function (item) {
      var term = '';
      var body = item.replace(/^\s*\[([^\]]*)\]/, function (_, t) { term = t; return ''; });
      return '<li>' + (term ? '<strong>' + inline(term) + '</strong> ' : '') +
        inline(body.trim()) + '</li>';
    }).join('') + '</' + tag + '>';
  }

  // KaTeX knows align and gather itself, so it is handed the whole environment first:
  // the alignment is information the reader wants. Where it refuses — an environment it
  // does not implement — the stripped body is still displayed maths.
  function mathsEnvHtml(inner, whole) {
    var labels = /\\label\{[^}]*\}/g;
    return strictMath(whole.replace(labels, '')) || math(inner.replace(labels, ''), true);
  }

  // A table, a float, or an environment nobody here implements: the reader is told what
  // was left out and where it does appear, rather than shown the source of it.
  function skippedHtml(name) {
    var what = /^(tabular|tabularx|longtable|table|tabbing)/.test(name) ? 'table' : name.replace(/\*$/, '');
    return '<p class="small-muted">' + escapeHtml(what) + ' — rendered in the PDF build</p>';
  }

  // Innermost first, so a table inside a float or a list inside a list is taken apart
  // from the inside out; each pass removes one begin/end pair, so the loop terminates.
  function takeEnvironments(body, slot, inline) {
    var passes = 0, m;
    while (passes < ENV_LIMIT && (m = ENV.exec(body))) {
      var name = m[1], inner = m[2], replacement;
      if (LIST[name]) { replacement = slot(listHtml(name, inner, inline)); }
      else if (MATHS_ENV[name.replace(/\*$/, '')]) { replacement = slot(mathsEnvHtml(inner, m[0])); }
      else if (VERBATIM[name]) { replacement = slot('<pre><code>' + escapeHtml(inner.replace(/^\n/, '')) + '</code></pre>'); }
      else if (TRANSPARENT[name]) { replacement = '\n\n' + inner + '\n\n'; }
      else { replacement = slot(skippedHtml(name)); }
      body = body.slice(0, m.index) + replacement + body.slice(m.index + m[0].length);
      passes += 1;
    }
    return body;
  }

  // ---- headings -----------------------------------------------------------------
  var LEVELS = { chapter: 4, section: 4, subsection: 5, subsubsection: 6, paragraph: 6, subparagraph: 6 };
  var HEADING = /\\(chapter|subsubsection|subsection|section|subparagraph|paragraph)\*?/;

  // A section command counts wherever it stands, not only at the head of a paragraph and
  // not only once in it: a source that writes one straight after a sentence, with no
  // blank line between, used to print the command itself into the reader's face.
  function headings(p) {
    var parts = [], at = 0, re = new RegExp(HEADING.source, 'g'), m;
    while ((m = re.exec(p))) {
      if (p.charAt(re.lastIndex) !== '{') { continue; }   // \paragraph with no title is prose
      var arg = braceArg(p, re.lastIndex);
      parts.push({ text: p.slice(at, m.index) });
      parts.push({ level: LEVELS[m[1]], title: arg.text });
      at = arg.end;
      re.lastIndex = arg.end;
    }
    parts.push({ text: p.slice(at) });
    return parts;
  }

  function renderLatexDoc(src, formula) {
    var figs = figures(src);
    var bib = parseBib(bibOf(src));
    var cited = [];
    var body = String(src).replace(BIB_BLOCK, '').replace(/^%.*$/gm, '');
    var m = body.match(/\\begin\{document\}([\s\S]*?)\\end\{document\}/);
    if (m) { body = m[1]; }
    body = body.replace(/\\mayaformula\{[^}]*\}/g, function () {
      return formula ? '\\[' + formula + '\\]' : '\\[\\text{(formula IR not set)}\\]';
    });
    var html = [];

    // A block that is not prose is rendered once, kept aside, and stood for in the source
    // by a marker with blank lines around it, so it becomes a paragraph of its own.
    function slot(rendered) {
      return '\n\n@@BLOCK' + (html.push(rendered) - 1) + '@@\n\n';
    }

    function citation(keys) {
      return '[' + keys.split(',').map(function (k) {
        var key = k.trim(), at = -1;
        bib.forEach(function (e, i) { if (e.key === key) { at = i; } });
        if (at < 0) { return '?' + escapeHtml(key); }
        if (cited.indexOf(key) < 0) { cited.push(key); }
        return String(at + 1);
      }).join(', ') + ']';
    }

    // A marker can end up inside a run of prose — a table inside a list item, say — so it
    // is resolved here rather than only where paragraphs are split.
    function inline(text) {
      return inlineHtml(text, citation).replace(/@@BLOCK(\d+)@@/g, function (_, n) {
        return html[parseInt(n, 10)] || '';
      });
    }

    var FIGURE = /\\begin\{figure\*?\}(?:\[[^\]]*\])?[\s\S]*?\\end\{figure\*?\}/g;
    body = body.replace(FIGURE, function (block) {
      var name = (block.match(/\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}/) || [])[1] || '';
      var cap = (block.match(/\\caption\{([^}]*)\}/) || [])[1] || name;
      var src2 = figs[name];
      return slot('<figure>' + (src2
        ? '<img src="' + src2 + '" alt="' + escapeHtml(cap) + '">'
        : '<div class="fig-missing">' + escapeHtml(name) + ' — not embedded in this document</div>') +
        '<figcaption>' + escapeHtml(cap) + '</figcaption></figure>');
    });
    body = takeEnvironments(body, slot, inline);

    var pieces = [];
    body.split(/\n\s*\n/).forEach(function (para) {
      var p = para.trim();
      if (!p) { return; }
      p = p.replace(/\\maketitle|\\tableofcontents|\\bibliographystyle\{[^}]*\}|\\bibliography\{[^}]*\}/g, '');
      if (!p.trim()) { return; }
      headings(p).forEach(function (part) {
        if (part.title !== undefined) {
          var tag = 'h' + part.level;
          pieces.push('<' + tag + '>' + inline(part.title) + '</' + tag + '>');
          return;
        }
        var text = part.text.trim();
        if (!text) { return; }
        var only = text.match(/^@@BLOCK(\d+)@@$/);
        if (only) { pieces.push(html[parseInt(only[1], 10)]); return; }
        // A paragraph of nothing but preamble or spacing commands has no reader in it.
        var rendered = inline(text);
        if (rendered.trim()) { pieces.push('<p>' + rendered + '</p>'); }
      });
    });
    if (bib.length) {
      pieces.push('<h4>References</h4><ol class="bib-list">' + bib.map(function (e) {
        return '<li id="bib-' + escapeHtml(e.key) + '">' + bibLine(e) + '</li>';
      }).join('') + '</ol>');
    }
    return pieces.join('\n');
  }

  // ---- outline (§17.1 "a section outline with completeness indicators") ----------
  function outline(src) {
    var body = String(src).replace(/^%.*$/gm, '');
    var re = /\\(subsubsection|subsection|section|paragraph)\*?\{([^}]*)\}/g, found = [], m;
    while ((m = re.exec(body))) {
      found.push({ level: LEVELS[m[1]] - 3, title: m[2], at: m.index, end: re.lastIndex });
    }
    return found.map(function (s, i) {
      var next = i + 1 < found.length ? found[i + 1].at : body.length;
      var text = body.slice(s.end, next).replace(/\\[a-zA-Z]+\*?(\{[^}]*\})?/g, ' ').trim();
      return {
        level: s.level, title: s.title, words: text ? text.split(/\s+/).length : 0,
        line: body.slice(0, s.at).split('\n').length - 1
      };
    });
  }

  // ---- the ladder, early: rung 4's static ban, in the browser --------------------
  var BANNED = [
    [/(^|[^.\w])open\s*\(/, 'open() — the filesystem is not available to an artifact'],
    [/\bsubprocess\b/, 'subprocess — no process may be started'],
    [/\bsocket\b/, 'socket — the sandbox has no network'],
    [/(^|[^.\w])eval\s*\(/, 'eval() — refused by rung 4'],
    [/(^|[^.\w])exec\s*\(/, 'exec() — refused by rung 4'],
    [/__import__/, '__import__ — imports are declared, not computed'],
    [/\bos\.system\b/, 'os.system — no shell']
  ];

  function builtInDiagnose(source) {
    var out = [];
    String(source).split('\n').forEach(function (line, i) {
      if (/^\s*#/.test(line)) { return; }
      BANNED.forEach(function (rule) {
        if (rule[0].test(line)) { out.push({ line: i + 1, message: rule[1] }); }
      });
    });
    return out;
  }

  function diagnose(source) {
    var server = window.MayaEditors && window.MayaEditors.languageServer;
    if (server && typeof server.diagnose === 'function') {
      try { return server.diagnose(source) || []; } catch (e) { return builtInDiagnose(source); }
    }
    return builtInDiagnose(source);
  }

  // ---- bracket matching (the add-on is not vendored, so: the public API) ---------
  var PAIRS = { '(': ')', '[': ']', '{': '}' }, CLOSERS = { ')': '(', ']': '[', '}': '{' };
  var SCAN_LIMIT = 20000;

  function findMatch(cm, pos, ch) {
    var forward = !!PAIRS[ch];
    var want = forward ? PAIRS[ch] : CLOSERS[ch];
    var depth = 0, line = pos.line, col = pos.ch, scanned = 0;
    while (line >= 0 && line < cm.lineCount() && scanned < SCAN_LIMIT) {
      var text = cm.getLine(line);
      while (forward ? col < text.length : col >= 0) {
        var c = text.charAt(col);
        if (c === ch) { depth += 1; }
        else if (c === want) {
          depth -= 1;
          if (depth === 0) { return { line: line, ch: col }; }
        }
        col += forward ? 1 : -1;
        scanned += 1;
      }
      line += forward ? 1 : -1;
      col = forward ? 0 : (line >= 0 && line < cm.lineCount() ? cm.getLine(line).length - 1 : 0);
    }
    return null;
  }

  function matchBrackets(cm) {
    var marks = [];
    function clear() { marks.forEach(function (m) { m.clear(); }); marks = []; }
    function mark(pos, cls) {
      marks.push(cm.markText(pos, { line: pos.line, ch: pos.ch + 1 }, { className: cls }));
    }
    cm.on('cursorActivity', function () {
      clear();
      var cur = cm.getCursor(), text = cm.getLine(cur.line) || '';
      var at = null, ch = null;
      [cur.ch, cur.ch - 1].forEach(function (i) {
        if (at !== null || i < 0) { return; }
        var c = text.charAt(i);
        if (PAIRS[c] || CLOSERS[c]) { at = i; ch = c; }
      });
      if (at === null) { return; }
      var here = { line: cur.line, ch: at };
      var other = findMatch(cm, here, ch);
      if (!other) { mark(here, 'cm-maya-bracket-bad'); return; }
      mark(here, 'cm-maya-bracket');
      mark(other, 'cm-maya-bracket');
    });
  }

  // ---- find and replace ---------------------------------------------------------
  function findPanel(cm) {
    var bar = document.createElement('div');
    bar.className = 'cm-find';
    bar.hidden = true;
    bar.innerHTML =
      '<input class="form-control form-control-sm" data-find placeholder="Find" aria-label="Find">' +
      '<input class="form-control form-control-sm" data-replace placeholder="Replace with" aria-label="Replace with">' +
      '<button class="btn btn-sm btn-outline-secondary" type="button" data-find-next>Next</button>' +
      '<button class="btn btn-sm btn-outline-secondary" type="button" data-find-one>Replace</button>' +
      '<button class="btn btn-sm btn-outline-secondary" type="button" data-find-all>Replace all</button>' +
      '<span class="small-muted" data-find-count aria-live="polite"></span>' +
      '<button class="btn btn-sm btn-outline-secondary ms-auto" type="button" data-find-close aria-label="Close find">×</button>';
    cm.getWrapperElement().parentNode.insertBefore(bar, cm.getWrapperElement());
    var find = bar.querySelector('[data-find]');
    var repl = bar.querySelector('[data-replace]');
    var count = bar.querySelector('[data-find-count]');

    function hits() {
      var needle = find.value;
      if (!needle) { return []; }
      var text = cm.getValue().toLowerCase(), q = needle.toLowerCase(), out = [], i = text.indexOf(q);
      while (i > -1) { out.push(i); i = text.indexOf(q, i + Math.max(1, q.length)); }
      return out;
    }
    function report(at) {
      var n = hits().length;
      count.textContent = !find.value ? '' : n === 0 ? 'no match'
        : (at === undefined ? n + ' match(es)' : (at + 1) + ' of ' + n);
    }
    function next() {
      var found = hits();
      if (!found.length) { report(); return; }
      var from = cm.indexFromPos(cm.getCursor('to'));
      var at = 0;
      found.forEach(function (i, k) { if (i >= from && found[at] < from) { at = k; } });
      if (found[at] < from) { at = 0; }
      cm.setSelection(cm.posFromIndex(found[at]), cm.posFromIndex(found[at] + find.value.length));
      cm.scrollIntoView(null, 60);
      report(at);
    }
    function replaceOne() {
      if (!find.value) { return; }
      if (cm.getSelection().toLowerCase() === find.value.toLowerCase()) {
        cm.replaceSelection(repl.value, 'around');
      }
      next();
    }
    function replaceAll() {
      var found = hits(), n = found.length;
      for (var i = n - 1; i >= 0; i -= 1) {
        cm.replaceRange(repl.value, cm.posFromIndex(found[i]), cm.posFromIndex(found[i] + find.value.length));
      }
      count.textContent = n + ' replaced';
    }
    function open() {
      bar.hidden = false;
      var sel = cm.getSelection();
      if (sel && sel.indexOf('\n') < 0) { find.value = sel; }
      find.focus();
      find.select();
      report();
    }
    function close() { bar.hidden = true; cm.focus(); }

    bar.querySelector('[data-find-next]').addEventListener('click', next);
    bar.querySelector('[data-find-one]').addEventListener('click', replaceOne);
    bar.querySelector('[data-find-all]').addEventListener('click', replaceAll);
    bar.querySelector('[data-find-close]').addEventListener('click', close);
    find.addEventListener('input', function () { report(); });
    find.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); next(); }
      if (ev.key === 'Escape') { close(); }
    });
    repl.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') { close(); } });
    cm.setOption('extraKeys', Object.assign({}, cm.getOption('extraKeys'), {
      'Ctrl-F': open, 'Cmd-F': open, 'Ctrl-H': open, 'Esc': close
    }));
    return { open: open, close: close, element: bar };
  }

  // ---- wiring -------------------------------------------------------------------
  function debounce(fn, ms) {
    var timer = null;
    return function () { clearTimeout(timer); timer = setTimeout(fn, ms); };
  }

  function editorApi(ta, cm) {
    return {
      get: function () { return cm ? cm.getValue() : ta.value; },
      set: function (v) { if (cm) { cm.setValue(v); cm.save(); } else { ta.value = v; } },
      insert: function (text) {
        if (!cm) { ta.value += '\n' + text; return; }
        cm.replaceRange(text, cm.getCursor());
        cm.save();
      },
      goto: function (line) {
        if (!cm) { return; }
        cm.setCursor({ line: line, ch: 0 });
        cm.scrollIntoView({ line: line, ch: 0 }, 80);
        cm.focus();
      },
      onChange: function (fn) {
        if (cm) { cm.on('change', fn); } else { ta.addEventListener('input', fn); }
      }
    };
  }

  function wirePreview(api, ta) {
    var target = document.getElementById(ta.getAttribute('data-preview'));
    if (!target) { return; }
    var formula = target.getAttribute('data-formula') || '';
    function update() { target.innerHTML = renderLatexDoc(api.get(), formula); }
    api.onChange(debounce(update, 180));
    update();
  }

  function wireOutline(api, id) {
    var panel = document.querySelector('[data-outline-for="' + id + '"]');
    if (!panel) { return; }
    function update() {
      var sections = outline(api.get());
      if (!sections.length) {
        panel.innerHTML = '<p class="small-muted mb-0">No sections yet.</p>';
        return;
      }
      panel.innerHTML = '<ul class="list-unstyled mb-0 outline-list">' + sections.map(function (s) {
        var mark = s.words === 0
          ? '<span class="pill warn"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i>empty</span>'
          : '<span class="pill ok"><i class="bi bi-check2" aria-hidden="true"></i>' + s.words + ' words</span>';
        return '<li class="lvl' + s.level + '"><button type="button" class="btn btn-link btn-sm p-0" ' +
          'data-outline-line="' + s.line + '">' + escapeHtml(s.title) + '</button> ' + mark + '</li>';
      }).join('') + '</ul>';
    }
    panel.addEventListener('click', function (ev) {
      var btn = ev.target.closest('[data-outline-line]');
      if (btn) { api.goto(parseInt(btn.getAttribute('data-outline-line'), 10)); }
    });
    api.onChange(debounce(update, 250));
    update();
  }

  function wireFigures(api, id) {
    var input = document.querySelector('[data-figure-for="' + id + '"]');
    if (!input) { return; }
    var note = document.querySelector('[data-figure-note="' + id + '"]');
    function say(text) { if (note) { note.textContent = text; } }
    input.addEventListener('change', function () {
      var file = input.files && input.files[0];
      if (!file) { return; }
      if (file.size > FIGURE_LIMIT) {
        say('That figure is ' + Math.round(file.size / 1024) + ' kB. A figure travels inside the ' +
          'document, so it has to stay under ' + (FIGURE_LIMIT / 1024) + ' kB — export the chart smaller.');
        input.value = '';
        return;
      }
      var reader = new FileReader();
      reader.onload = function () {
        var base64 = String(reader.result).split(',')[1] || '';
        api.insert('\n' + figureBlock(file.name, base64));
        say(file.name + ' is in the document: the figure environment is at your cursor and the ' +
          'image travels with the source, so it versions and diffs with it. A PDF build that ' +
          'cannot write the image out prints a labelled box in its place rather than failing.');
        input.value = '';
      };
      reader.readAsDataURL(file);
    });
  }

  function wireBib(api, id) {
    var pane = document.querySelector('[data-bib-for="' + id + '"]');
    if (!pane) { return; }
    var box = pane.querySelector('textarea');
    var file = pane.querySelector('input[type=file]');
    var note = pane.querySelector('[data-bib-note]');
    var apply = pane.querySelector('[data-bib-apply]');
    if (!box || !apply) { return; }
    box.value = bibOf(api.get());
    apply.addEventListener('click', function () {
      var bib = box.value.trim();
      if (!bib) { return; }
      api.set(withBib(api.get(), bib));
      var n = parseBib(bib).length;
      if (note) {
        note.textContent = n + ' entry/entries are now in the document, with ' +
          '\\bibliography{refs}; \\cite{key} is numbered in the preview and built by BibTeX in the PDF.';
      }
    });
    if (file) {
      file.addEventListener('change', function () {
        var chosen = file.files && file.files[0];
        if (!chosen) { return; }
        var reader = new FileReader();
        reader.onload = function () { box.value = String(reader.result); };
        reader.readAsText(chosen);
      });
    }
  }

  function wireChecks(api, id) {
    var panel = document.querySelector('[data-checks-for="' + id + '"]');
    if (!panel) { return; }
    function update() {
      var found = diagnose(api.get());
      panel.innerHTML = found.length
        ? '<ul class="list-unstyled mb-0 small">' + found.map(function (d) {
          return '<li><span class="pill bad"><i class="bi bi-x-circle" aria-hidden="true"></i>line ' +
            d.line + '</span> ' + escapeHtml(d.message) + '</li>';
        }).join('') + '</ul>'
        : '<p class="small-muted mb-0">Nothing the static ban would refuse. The sandbox still has the last word.</p>';
    }
    api.onChange(debounce(update, 300));
    update();
  }

  window.MayaEditors = window.MayaEditors || {};
  Object.assign(window.MayaEditors, {
    renderLatexDoc: renderLatexDoc, figures: figures, figureBlock: figureBlock,
    outline: outline, parseBib: parseBib, bibOf: bibOf, withBib: withBib,
    diagnose: diagnose, builtInDiagnose: builtInDiagnose, instances: {}
  });

  document.querySelectorAll('textarea[data-editor]').forEach(function (ta) {
    var mode = ta.getAttribute('data-editor') === 'python' ? 'python' : 'stex';
    var cm = null, finder = null;
    if (window.CodeMirror) {
      cm = window.CodeMirror.fromTextArea(ta, {
        mode: mode, lineNumbers: true, indentUnit: 4, lineWrapping: true,
        readOnly: ta.hasAttribute('readonly'),
        // Prose is spell-checked by the browser's own dictionary, which needs the
        // contenteditable input; code is not, because underlining every identifier
        // teaches a designer to ignore the underlines.
        inputStyle: mode === 'stex' ? 'contenteditable' : 'textarea',
        spellcheck: mode === 'stex', autocorrect: false, autocapitalize: false
      });
      cm.on('change', function () { cm.save(); });
      matchBrackets(cm);
      if (!ta.hasAttribute('readonly')) { finder = findPanel(cm); }
      // A CodeMirror inside a hidden tab measures zero width; refresh when shown.
      document.querySelectorAll('[data-bs-toggle="tab"]').forEach(function (btn) {
        btn.addEventListener('shown.bs.tab', function () { cm.refresh(); });
      });
      var sel = document.querySelector('select[data-toggle-show]');
      if (sel) { sel.addEventListener('change', function () { setTimeout(function () { cm.refresh(); }, 50); }); }
    }
    var api = editorApi(ta, cm);
    api.openFind = function () { if (finder) { finder.open(); } };
    if (ta.id) { window.MayaEditors.instances[ta.id] = api; }
    if (ta.hasAttribute('data-preview')) { wirePreview(api, ta); }
    if (ta.id) {
      wireOutline(api, ta.id);
      wireFigures(api, ta.id);
      wireBib(api, ta.id);
      wireChecks(api, ta.id);
    }
  });

  // A .py file chosen from disk fills the editor beside it; the form still submits the text,
  // so a file and a paste are the same thing to the server. Nothing is uploaded until then.
  var MAX_SOURCE_BYTES = 1024 * 1024;
  document.querySelectorAll('input[type=file][data-load-into]').forEach(function (input) {
    input.addEventListener('change', function () {
      var id = input.getAttribute('data-load-into'), file = input.files && input.files[0];
      var status = document.querySelector('[data-load-status="' + id + '"]');
      function say(msg) { if (status) { status.textContent = msg; } }
      if (!file) { return; }
      if (file.size > MAX_SOURCE_BYTES) { say(file.name + ' is over 1 MB; paste the part MAYA needs instead.'); input.value = ''; return; }
      var reader = new FileReader();
      reader.onload = function () {
        var api = window.MayaEditors.instances[id], ta = document.getElementById(id);
        if (api) { api.set(String(reader.result)); } else if (ta) { ta.value = String(reader.result); }
        say('Loaded ' + file.name + '. Review it, then submit.');
      };
      reader.onerror = function () { say('Could not read ' + file.name + '.'); };
      reader.readAsText(file);
      input.value = '';
    });
  });

  document.querySelectorAll('[data-find-for]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var api = window.MayaEditors.instances[btn.getAttribute('data-find-for')];
      if (api) { api.openFind(); }
    });
  });
})();
