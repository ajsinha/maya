/* Typeset the mathematics a rendered document marks with .maya-math, using the vendored KaTeX.
 * A formula KaTeX cannot read is left as its source text rather than hidden.
 * Copyright (c) 2026 Ashutosh Sinha. All rights reserved. */
(function () {
  if (!window.katex) { return; }
  document.querySelectorAll('.maya-math').forEach(function (el) {
    try {
      window.katex.render(el.textContent, el, { displayMode: el.classList.contains('display'), throwOnError: false });
    } catch (e) { /* keep the source visible */ }
  });
}());
