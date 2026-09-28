# Medium post: *Evidence, Not Assertion*

[`evidence-not-assertion.md`](evidence-not-assertion.md) is the post: ten design ideas from
building MAYA, with six diagrams, code and configuration examples, and figures from the case
studies' real runs.

## Publishing it on Medium

Medium does not import Markdown with images, and it does not render diagram code, so:

1. **Paste the text** section by section into the Medium editor (or use an importer that
   accepts Markdown). Headings, bold, lists and quotes paste cleanly.
2. **Upload the six images** from [`img/`](img/) where the post references them:
   `01-chain.png`, `02-two-clocks.png`, `03-checksum-cycle.png`,
   `04-warrant-lifecycle.png`, `05-beside-the-platform.png`, `06-splits.png`. The alt text
   is the caption in the post.
3. **Code blocks**: Medium's code block (``` on a new line) keeps them monospaced; for syntax
   colour, paste them as GitHub gists instead.
4. **Tables**: Medium has no tables. Paste each as an image (a screenshot of the rendered
   Markdown) or rewrite it as a short list.

## Regenerating the diagrams

    .venv/bin/python docs/articles/medium/diagrams.py

writes each figure as SVG and, with Inkscape on the PATH, as PNG at 144 dpi.
