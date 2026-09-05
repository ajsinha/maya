# ADR-008 — Server-rendered Jinja2 + Bootstrap + jQuery, no SPA

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** ⚠️ **SUPERSEDED by [ADR-011](ADR-011-decoupled-frontend.md)** · **Date:** 2026-09

> **Superseded.** The sponsor requires the UI and backend to run as separate, concurrent processes with
> the UI consuming backend services. See [ADR-011](ADR-011-decoupled-frontend.md). The reasoning below is
> retained because ADR-011 preserves two of its conclusions — no client-side business logic, and
> server-rendered output for evidence-grade documents.

## Context
The mandated front-end stack is jQuery and Bootstrap. The temptation is to simulate an SPA in jQuery,
which historically produces an unmaintainable client-side state machine.

## Decision
**Server-rendered pages with progressive enhancement.** Every page renders fully on the server. jQuery
performs HTML-fragment swaps against server endpoints. **No business logic on the client** — tier,
status, gate eligibility and obligations are computed server-side and rendered.

The client stack is exactly what is in `web/static/vendor/`: **Bootstrap 5.3, Bootstrap Icons and
jQuery 3.7**, vendored, no CDN, no external call at page load.

## Consequences
- **+** One source of truth for governance decisions. The browser can never re-derive and disagree.
- **+** Pages are printable, screenshot-able and archivable as evidence — which matters in a regulated
  system more than it does in a consumer app.
- **+** Accessibility and progressive enhancement come nearly free from semantic HTML.
- **+** No build pipeline, no client-side dependency supply chain, smaller attack surface.
- **−** Interactions are less fluid than a modern SPA. Acceptable: this is a review-and-decide tool, not a
  design canvas.

### Correction, recorded rather than quietly edited
This ADR named DataTables, Chart.js and Cytoscape.js as part of the decision, and described "the one
genuinely interactive surface (the dependency graph)". **None of the three is vendored and there is no
graph page.** Tables are server-paginated through the keyset API, and every number is rendered as a
number.

It is worth leaving the correction visible, because the sentence was not wrong when written — it was a
decision recorded in the past tense that was then never taken. Adding a library later means vendoring it,
which is what the no-CDN rule makes explicit and what stopped this from happening by accident. The
current absences are listed as absences in [08 §UI limits](../08-ui-ux.md).
- **−** More server round trips. Mitigated by fragment-level caching and keyset pagination.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
