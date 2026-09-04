# ADR-011 — Decoupled front end consuming backend services

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **NOT BUILT** · **Date:** 2026-09 · **Supersedes:** [ADR-008](ADR-008-server-rendered-ui.md)

> **As built, and stated plainly because three reviewers read this document and believed it.**
> None of the decision below has been implemented. What runs is exactly [ADR-008](ADR-008-server-rendered-ui.md):
> a server-rendered Jinja2 application **inside the FastAPI process**. `routes/ui_routes.py` makes
> **41 direct in-process service calls** (`self.ctx["registry"]`, `self.ctx["evidence"]`, and so on);
> there is no second process, no CORS middleware, and no bearer-token flow. Writes from the browser
> do go through the public API over jQuery — reads do not.
>
> This matters beyond tidiness. The README and `docs/12` both state as fact that the UI consumes
> only the public API and that no privileged server-side path exists, and a Head of Model Risk who
> plans to build management information on that API would find the screens can see things the API
> cannot. Either route the UI through the API or withdraw the claim; until one of those happens,
> this note is the honest description.

## Context

[ADR-008](ADR-008-server-rendered-ui.md) specified a server-rendered Jinja2 application inside the
FastAPI process. The sponsor requires instead that **the UI and the backend run as separate, concurrent
processes, with the UI consuming backend services**, and that the system be modular and extensible
throughout.

Re-examined, the original decision undervalued three things. The API was not the only interface, so it
could rot behind a privileged server-side path that bypassed it — a real risk, and one that would have
surfaced late. Front end and backend could not be scaled, released or failed independently. And the UI
could not be replaced or supplemented (a mobile approval client, an embedded widget in another
application) without touching the backend.

## Decision

Two independently built, independently deployed, independently scaled processes.

- **`maya-web`** — static assets (HTML, Bootstrap 5, jQuery, ES modules) served by nginx or a CDN. No
  server-side rendering of application pages. Client-side routing over a hash-free history API.
- **`maya-api`** — FastAPI. The **only** interface, versioned at `/api/v1`, described by OpenAPI 3.1.
  The UI consumes a generated client; no privileged path exists.

Supporting decisions:

1. **Authentication.** OIDC Authorization Code with PKCE, performed by the browser. Access tokens are
   held **in memory only** — never `localStorage`, never `sessionStorage`. Refresh uses a
   `__Host-`-prefixed, `SameSite=Strict`, `HttpOnly`, `Secure` cookie against a minimal
   **token-broker** endpoint, which is the only cookie-bearing surface and is CSRF-protected. API calls
   carry bearer tokens, so there is no ambient cookie authority and CSRF does not apply to them.
2. **P4′ — the client renders decisions, it never derives them.** Every gate verdict, tier, obligation,
   eligibility flag and RAG status arrives from the API *with its rationale*. Endpoints return
   `allowed` plus `deny_reason[]`; they do not return the raw facts a client would need to compute a
   verdict. This preserves the one conclusion of ADR-008 that was unambiguously right.
3. **Evidence-grade output stays server-side.** Documents, reports, committee packs and examiner
   exports are rendered by the backend and returned as HTML or PDF. Anything that may be taken into a
   meeting or an examination is produced by the system of record, not assembled by a browser.
4. **Modularity.** The front end is organised as feature modules mirroring the backend's bounded
   contexts, each owning its routes, views and generated client slice. A module is added or removed
   without touching another.
5. **Contract testing in both pipelines.** The backend publishes the OpenAPI document as a build
   artifact; the front-end build fails if the generated client no longer matches; the backend build
   fails on an unapproved breaking change (Schemathesis plus a spec-diff gate).

## Consequences

**Positive**

- The API is exercised continuously by the product itself, so it cannot drift from what the UI needs.
- Independent scaling and release. A front-end deploy carries no database migration risk.
- Independent failure. A front-end outage stops human review; it does not stop warrant resolution,
  scheduled jobs, monitoring, or the SDK — which is a meaningful improvement in blast radius.
- Alternative clients (mobile approvals, embedded widgets, a terminal client) become possible at no
  additional backend cost.
- The static tier is trivially cacheable and cheap to serve.

**Negative, and how each is handled**

- **Authentication complexity moves into the browser.** Handled by the PKCE + in-memory + token-broker
  pattern above, which is the current standard for exactly this shape.
- **Two build pipelines and a versioning discipline.** Handled by contract tests in both directions and
  an explicit API deprecation policy (two minor versions of overlap, `Sunset` headers).
- **Risk of logic leaking into the client.** Handled by P4′ and by API design — if the client cannot
  obtain the inputs, it cannot compute the verdict. Enforced at review.
- **CORS and origin management.** Strict allow-list per environment; no wildcards; preflight cached.
- **Initial load and SEO.** Irrelevant here — an authenticated internal application with no public
  surface.

**Retained from ADR-008**

No client-side business logic; accessibility via semantic HTML; server-rendered, printable, archivable
documents. The stack constraint (Bootstrap 5, jQuery) is unchanged — it now runs against an API rather
than against templates.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
