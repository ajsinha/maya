# 08 — The interface, in two tenses

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Annex to** [04 — Architecture](04-architecture.md).

---

This document is organised by **tense**, and that is not a stylistic choice.

Part one is present tense and describes only what runs. Part two is conditional and describes only
what does not. Nothing is mixed, because mixing them has already cost this platform a live security
defect.

The earlier version of this document carried a table saying *"Bearer token in `Authorization`. No
ambient cookie authority, so CSRF does not apply to the API."* That sentence was true of
[ADR-011](adr/ADR-011-decoupled-frontend.md)'s decoupled front end, which nobody has built. What runs
is a server-rendered Jinja interface whose pages call the same API **under a session cookie** — so
ambient cookie authority is exactly what it has, and the row read as a statement about the running
system. Three reviewers read it and believed it. The API had no CSRF defence for as long as that
sentence stood.

The lesson generalises past CSRF: **a control written in the future tense reads as a control, and the
tense is the part people skip.** So the split is structural here. A reader who stops at the end of
part one has read a complete and true description of the interface that exists.

| | |
|---|---|
| **Part one — built** | §1–§7. Server-rendered Jinja2 inside the FastAPI process. Bootstrap 5 and jQuery, both vendored. Twenty-two pages |
| **Part two — designed, not built** | §8–§10. The decoupled front end of ADR-011, and the screens specified for it |
| **Part three — brand** | §11–§12. Shipped assets and the rules on them, with which rules a test holds |

---

# Part one — what is built

## 1. One process, and the asymmetry inside it

There is one process. `routes/ui_routes.py` renders templates from `web/templates/` against services
it holds directly, and the browser's *writes* go back out through `/api/v1` over jQuery.

That asymmetry is the single most important fact about the built interface, and it is a defect rather
than a design:

> **Reads are in-process. Writes go through the public API.**
> `routes/ui_routes.py` makes **51 direct service calls** (`self.ctx["registry"]`,
> `self.ctx["evidence"]`, and twenty-three other services). No read a page performs is exercised
> through `/api/v1`.

The consequence is not tidiness. A Head of Model Risk planning management information on the public
API can find that the screens see things the API cannot, because nothing forces the two to agree on
reads. ADR-011 exists to close this and is not built. Until it is, the honest statement is the one
above rather than *"the UI consumes only the public API"*.

What the asymmetry does **not** cost is authorisation, and that is deliberate. A page asks the same
authoriser the API asks:

```python
# routes/base.py
def may_view(self, request, permission="model:read", model=None) -> bool:
    """Whether the signed-in person may see this, by the same rule the API
    applies. One authorisation policy, asked from two places."""
```

That method exists because of a real defect. `login_required` answers whether *somebody* is signed
in; it does not answer who they are or what they may see, and the pages once used it alone. A
validator scoped to one legal entity got a 403 from the API and correctly saw nothing on the
dashboard — then loaded the model page by URL and received its versions, alias history, warrant
grants and full evidence chain. **Listings filtered; directly-addressable pages did not.** Every page
that resolves one named object now calls `may_view` before rendering, and a refusal renders
`forbidden.html` — a page-shaped 403 that says the thing exists and is outside your scope, rather
than a 404 that pretends otherwise.

## 2. Every page there is

Twenty-two routes render a page. Seven are reachable without a session; fifteen are not.

### 2.1 Public

| Route | Template | What it is |
|---|---|---|
| `/` | `landing.html` | The argument, and a live count of registered models |
| `/about` | `about.html` | What this is and what it is not |
| `/help`, `/help/{slug}` | `help.html`, `help_topic.html` | 16 help topics, markdown on disk rendered at request time |
| `/tutorials`, `/tutorials/{slug}` | same two templates | Fifteen walkthroughs, the same renderer, one dictionary entry apart |
| `/login` | `login.html` | The only page that establishes a session |

Help and tutorials are **files under `content/`, not templates**. They are versioned, reviewable in
the same pull request as the behaviour they describe, and cannot ship in a release that changed
without them.

### 2.2 Behind a session

| Route | Template | What it answers | Refuses when |
|---|---|---|---|
| `/dashboard` | `dashboard.html` | The register, the estate summary, my worklist, the chain's standing | — (the list is scope-filtered) |
| `/model/{name}` | `model.html` | Everything about one model — §3 | `model:read` out of scope |
| `/features` | `features.html` | The catalogue: defined, derived, served; the expression language; retrieval, alignment and composition, each described by the module that implements it | — |
| `/feature-views/{name}` | `feature_view.html` | One view, its versions, and each version restated | 404 |
| `/featuresets` | `featuresets.html` | Every set, its versions, the latest | — |
| `/featureset/{name}` | `featureset.html` | One set: the resolved definition, the assembly plan per version, the restatements | 404 |
| `/parameters/{semver}/{name}` | `parameters.html` | What one version may run on, and what stands behind each set | `model:read` |
| `/telemetry` | `telemetry.html` | Every version's telemetry, the ones that stopped sending first | — |
| `/telemetry/{semver}/{name}` | `telemetry_version.html` | One version's cohort, and how much of it is labelled | `monitor:read` |
| `/policies` | `policies.html` | The four gates in force, their fact vocabularies, the drafts, and the drift each publication caused | — |
| `/notifications` | `notifications.html` | Which channels work, what has been delivered, and what *you* would be sent | — |
| `/board-pack` | `board_pack.html` | What a committee would be shown — §4 | `report:read` |
| `/dossier/{name}` | `dossier.html` | Everything documented about a model, following the pins — §5 | `document:read` |
| `/models/new` | `new_model.html` | Register a model, or upload a version of one | — (the model list is scope-filtered) |
| `/document/{id}` | `document.html` | One compiled document, its anchors, its staleness and its citations | `document:read` on the subject model |

Two routing details are load-bearing. The model segment is a greedy `:path` converter because a URN
carries dots and slashes, so **the version comes before the model** on `/telemetry/{semver}/{name}`
and `/parameters/{semver}/{name}` — a greedy segment in front of a semver would swallow it. And the
render helper's HTTP-code keyword is spelled `http_status`, not `status`, because `status` is the
most natural name a page has for a model's status, a finding's status or a version's status: a caller
passing one got a silently empty template variable and a response code taken from a domain word.

## 3. The model page

The spine of the product, and the one page a reader should judge the interface by. Six hundred and
forty-seven lines of template, one model.

### 3.1 The model, as its type

The first card is not a summary. It is the definition:

```
                    P    ⊗    X    →    D(Y)

  P — what is fitted        X — what it reads       D(Y) — what comes back
  estimated_coefficients    years_in_business : int  pd : float
  estimated from a          dscr : float [-5, 20]    point_estimate
  historical sample

  [T2]  estimated_coefficients · statistical_estimation · runtime onnx
        — the class is derived from the two before it and is never declared.
```

Everything on it comes from the version's own record: `parameter_kind`, `fit_procedure`, the input
and output schemas with their declared ranges, the runtime off the kernel manifest. Nothing is typed
by hand, and the trainability class is shown **beside the two facts it is derived from** rather than
alone — which is the difference between a label and an explanation. A reader used to assemble this
from four cards.

`PARAMETER_MEANING` in `routes/ui_routes.py` renders each way of inhabiting `P` in a reader's words —
*"empty — there is nothing to fit"*, *"solved against market instruments, repeatedly"*, *"exists, and
cannot be reached from here"*. Short on purpose: the page is showing a type, not teaching the
taxonomy.

### 3.2 The cards, and what each one refuses to imply

| Card | What it shows | The refusal built into it |
|---|---|---|
| Approval & attestation | The lifecycle as a stepper, the open amendment, each required role's signature or absence | The record is stamped **FROZEN** or **OPEN TO CHANGE**, so nobody has to infer whether an edit is possible |
| Versions | Semver, class, fit procedure, status, manifest digest | The digest is shown, truncated but present: a version is identified by what it is, not by its number |
| Features | The **view versions each model version is pinned to**, per version | Not "the model's features". A contract binds per model version, which is the granularity serving reads at |
| Post-model adjustments | Reference, kind, status, renewals, magnitude as a percentage of base | An overlay past its window says **window elapsed**; a renewal past the limit is flagged, because an overlay renewed indefinitely is an unversioned model change |
| Documentation | Coverage as *filled/sections*, citation count, staleness with the number of events since | Staleness is **computed**, not remembered |
| Version approval | How many signatures each version owes, and which roles | Quorum is shown as a requirement even when it is unmet, so an approval that has not happened does not look like one that has |
| Parameters | Each set, its version, how `P` was inhabited, its state | A set is `awaiting approval` until somebody approves it, and the empty state says a version with no approved parameters cannot run *unless its parameter object is terminal* |
| Documents on file | What people wrote, as against what MAYA compiled | Rejected documents stay listed. The papers that did not pass are the ones a supervisor asks about |
| Monitoring | Monitor, test key, threshold, last observation with sample size | The empty state says what monitoring is *for*: a breach raises a finding, and a blocking finding refuses warrant resolution |
| Validation | Kind, validators, status, outcome | — |
| Alias history | Every move with its refinement result and its variance result | A promotion carries its proofs on the same row. An alias move is a proof obligation, not a deployment |
| Findings | Severity, title, owner; blocking ones in red | When anything is blocking, the card says warrant resolution and alias moves are refused — the consequence, beside the cause |
| Regimes | Per regime: satisfied or *n* unmet, out of how many | When regimes disagree it says so, and says the disagreement is a fact about the estate rather than a defect |
| Warrants | Grants, principal, declared use, revocation state; a **Generate** button that resolves one live and prints the JSON | The resolved warrant is shown whole, with the endpoint to validate it against, because a warrant a reader cannot read is a warrant they take on trust |
| Evidence | Every node's kind and sequence, with the chain hash | — |

Two side-rail cards are doors rather than displays: **Open the dossier** (§5) and **Cut a pack**, an
export pack digested member by member for somebody who will never be given a login.

## 4. The board pack

`/board-pack` renders what a committee would be shown **before it is recorded**. Everything above the
last card is a preview; recording it fixes what the committee was shown, and a pack on record is kept
as it was read — a minute referring to the March pack needs the March pack, and one recomputed today
is a different document with the same name.

Three things on it are worth naming because they are refusals rather than features:

- **"Not measured" is its own card, in red, above the numbers.** An indicator that was not computed
  is not zero and not clean. Zero is a measurement; an absent service is not; and reporting one as
  the other tells a committee the estate is healthy when it is unobserved.
- **Exceptions come before the totals.** A committee asks three questions in order — are we inside
  our limits, what is outside them, what moved — and a report that answers only the first is a
  dashboard, which is why nobody reads the pack.
- **"Why there is no single number" is a card on the page.** Aggregate model risk does not compose
  into one figure, and the page says so where the figure would otherwise go.

The **Record it** button is rendered only when the principal holds `report:cut`. Whether to offer a
control is the platform's decision rather than the template's: a page that hides a control it cannot
explain is better than one that offers an action the caller may not take.

## 5. The dossier

`/dossier/{name}` walks the documentation graph from a model and renders it as a tree — versions,
their parameter sets, the featureset versions those were fitted from, and the features in them.

The page's argument is on the page: documentation is a graph, not a list. It arrives at different
moments about different objects, and it is filed against what it is **about**. A training record
names `sb_core@v1` and never `sb_core`, because a document filed against the set would describe
something that has since moved.

Every node with nothing filed says **"nothing filed — expected …"**, and the gaps are also counted
and tabulated. That is the whole point of the page:

> A page that silently omits what it could not find reads as complete, and a reader cannot tell a
> thin model from a thin page unless the page says which it is.

## 6. The rules the built interface actually holds

Six, each with the failure it prevents.

1. **No governance logic in a page.** Tier, gate verdicts, staleness, quorum, RAG standing and
   regime determinations are computed by services and rendered. A browser that could re-derive a
   verdict is a browser that can disagree with the system of record, and then two answers exist to a
   question that must have one.

2. **Scope is applied to pages, not only to listings.** §1. A directly-addressable page that skips
   the check is a filtered listing with a hole in it.

3. **Every asset is vendored.** `web/static/vendor/` holds Bootstrap 5, Bootstrap Icons and jQuery —
   675 KB across six files, no CDN, no external fetch. A governance platform that cannot be deployed air-gapped is
   one somebody works around.

4. **The table script is written, not vendored.** `web/static/js/tables.js` gives every table search,
   sort and paging. Sorting is always available, because a reader who wants the worst finding first
   should not have to count rows; search and paging appear at eight rows, because a pager under four
   is noise and noise is what stops people reading a page. Numbers sort as numbers and dates as
   dates, so a Gini of 0.61 does not sort below 0.7 as a string would.

5. **Every table has a header row, with no exemption**, held by `tests/test_ui_tables.py`. There was
   briefly an opt-out for "key/value reference lists", and the exemption was the wrong answer to the
   right observation: those were not tables. A term beside its definition is a description list, and
   rendering it as a two-column table with no header is layout-by-table — a screen reader announces
   *"table, two columns"* and then offers no headers to orient by, which is worse than no markup at
   all. They are `<dl class="maya-terms">` now.

6. **Every page carries a CSRF token, and no page has to remember it.** `base.html` renders the
   session token into a `<meta>` tag; `web/static/js/csrf.js` attaches it to every non-safe jQuery
   request, wraps `fetch` for the page somebody writes next week, and stamps a hidden field into
   every `method="post"` form. Same-origin only — sending the token to another host would hand over
   the thing it exists to withhold. The server side is [09 §2](09-security-compliance.md).

## 7. What the built interface does not do

Named, because a reader planning around this deserves the list rather than a discovery.

| | |
|---|---|
| **No print stylesheet** | Bootstrap's own `@media print` block is all there is. §12's claim of a dated, watermarked print rendering is not built |
| **No `[why?]` affordance** | Tiering stores its derivation (`core/risk/tiering.py`), and no page opens it. The derivation exists; the door does not |
| **No dependency graph screen** | Cytoscape.js is not vendored and there is no graph page. The `input_to` edges are typed and stored; nothing draws them |
| **No validation workbench** | No replay, no challenger runner, no independent recode, no slice explorer. Validation appears on the model page as a table of episodes |
| **No charts** | Chart.js is not vendored. Every number is rendered as a number |
| **No discovery, examiner or admin screen** | Principals, connectors and examiner packs are API-only |
| **Accessibility is partial** | Semantic HTML and the description-list fix are real; ARIA is on one template. Full keyboard operation, visible focus and 4.5:1 contrast are stated in `NFR-USE-002` and are not tested anywhere |
| **`/models/new` is two forms, not a wizard** | Register a model, or upload a version, side by side, plus a note on registering what already runs in an execution engine. It carries the artifact format list with **`executes_on_load` marked against each format**, so the warning is attached to the choice rather than left in a document somebody read once |

---

# Part two — what is designed and is not built

Everything below this line is conditional. None of it runs.

## 8. ADR-011 — the decoupled front end

[ADR-011](adr/ADR-011-decoupled-frontend.md) is accepted and **not built**. It would replace part one
entirely: `maya-web` as static assets served by nginx or a CDN, `maya-api` as FastAPI, no
server-rendered application page, and the public API as the only interface.

| Element | Designed |
|---|---|
| Processes | Two, built and deployed and scaled independently. A front-end release carries no migration risk |
| The interface | `/api/v1` only. No privileged server-side path, so the API cannot drift from what real clients need — the defect §1 records |
| Login | OIDC authorization code with **PKCE**, initiated by the browser |
| Access token | **Memory only.** Never `localStorage`, never `sessionStorage`; lost on tab close, by design |
| Refresh | A `__Host-`-prefixed, `SameSite=Strict`, `HttpOnly`, `Secure` cookie against `/auth/refresh` — the only cookie-bearing surface, and CSRF-protected |
| API calls | Bearer token in `Authorization`. Under **that** architecture there is no ambient cookie authority, and CSRF would not apply to the API. It is not that architecture today |
| Step-up | Alias moves, revocations, overrides and break-glass re-authenticate with an intent statement, returned as `403 step_up_required` |
| CORS | A strict per-environment origin allow-list. No wildcards |
| Modules | Feature modules mirroring the backend's bounded contexts, each owning its routes, views and client slice |
| Contract testing | The backend publishes its OpenAPI document; the front-end build fails if the generated client no longer matches |

**P4′ would survive the change.** *The client renders decisions, it never derives them* — endpoints
return `allowed` plus `deny_reason[]`, never the raw facts a client would need to recompute a verdict.
If the client cannot obtain the inputs, it cannot drift from the backend's answer. That is the one
conclusion of [ADR-008](adr/ADR-008-server-rendered-ui.md) that ADR-011 keeps, and part one holds it
today by rendering server-side.

## 9. Screens specified and not built

Each of these was designed against a real need. None exists.

| Screen | What it would answer | The need it comes from |
|---|---|---|
| **Dependency / blast-radius explorer** | *What breaks if I change this feeder model, and who do I have to tell?* Selected node, downstream depth, tier filter, and a generated notification list | Aggregate risk is legible only as a graph, and `input_to` is a typed composition rather than a drawing |
| **Validation workbench** | Plan completeness per section, evidence per test, replay in the sandbox, challenger fitting, independent recode, slice explorer, sensitivity sweep | Validators are the scarcest resource in model risk, and clerical work is what they spend it on |
| **Discovery triage** | Unregistered models found by connectors, with the artifact each proposal points at | Inventory completeness is the top adoption risk. Scope it narrowly: a queue with poor precision is worse than no queue, because it creates the appearance of coverage |
| **Use reconciliation** | Approved use against actual use, as exceptions | An approved model used for an unapproved purpose is T3 in the threat model |
| **Examiner portal** | Read-only, as-at-date, request packs | The export pack does this today, without a login |
| **Campaigns** | Periodic revalidation and attestation cycles, with SLA | The scheduler runs the jobs; nothing shows the cycle |
| **Admin** | Classes, lifecycles, policies, templates, tests, users, connectors | Principals and policies are API-only today |
| **Schema-driven metadata form** | A model class adds a fibre on the backend and its capture form appears with no front-end change — a T1 pricing model asked for calibration instruments and tolerance, a T5 asked for autonomy mode and eval set | The fibration reaching the UI. `/models/new` renders a fixed form today |

## 10. Conventions the API would have to offer

The decoupled client would depend on these. Some exist; the column says which.

| Convention | Purpose | Today |
|---|---|---|
| `problem+json`-shaped errors | One error shape, rendered consistently; `deny_reason` and remediation surfaced inline | **Built** — every refusal returns `error` / `detail` / `remediation` at the top level, mapped in one table (`routes/base.py`) |
| Server-Sent Events on `/events` | Live task inbox, breach alerts, job progress, without polling | Not built |
| Keyset pagination with `next_cursor` | Stable paging over 50,000 models | Not built; listings return whole |
| `ETag` + `If-Match` on mutations | Optimistic concurrency, so a conflict is a dialog rather than a silent overwrite | Not built |
| `Idempotency-Key` on `POST` | Safe retry on a flaky network | Not built |
| `?expand=` and `?fields=` | One request per screen instead of N+1 chatter | Not built |
| `/derivations/{id}` on every derived value | Powers the universal `[why?]` affordance (`P8`) | Not built as an endpoint; tiering stores its derivation |

---

# Part three — brand

## 11. The elements

| Element | Value | Where it appears |
|---|---|---|
| **Name** | MAYA — Sanskrit *māyā* (माया), *appearance* / *representation* | Everywhere |
| **Tagline** | Model & AI Lifecycle Assurance | Page footer, document headers |
| **Slogan** | **Evidence, not assertion.** | The navbar, the footer, export-pack covers, the About page |
| **Principle** | *A model is a representation of the world. Governance is knowing the difference.* | About, onboarding, examiner covers |
| **Mark** | A square inscribed in a circle | Navbar, favicon, export packs, decks |

![MAYA mark](../assets/logo/maya-mark-128.png)

Archimedes bounded π by inscribing and circumscribing polygons: a tractable figure standing in for
one that cannot be computed directly. The **gap** between the square and the circle is the model
error; the **four points** are where the model and the world agree. Add sides and the gap closes but
never vanishes — no model becomes the thing it represents.

That reading is worth knowing because it is the argument the whole platform makes, which is also why
the slogan is used where the product is making that claim and not decoratively. It belongs on the
sign-in screen, on the cover of an examiner pack, and in About. It does not belong on every page
header, where it becomes wallpaper and stops meaning anything.

Assets are in [`assets/logo/`](../assets/logo/): `maya-mark.svg` (primary), `maya-mark-white.svg`
(knockout for crimson), `maya-mark-mono.svg` (inherits `currentColor`), and `maya-lockup.svg` (mark,
wordmark, tagline, slogan). The interface serves `maya-mark-64.png` from `web/static/img/`.

| Rule | Detail |
|---|---|
| Clear space | One quarter of the mark's width on every side |
| Minimum size | 20 px for the mark; 180 px for the lockup. Below 20 px, the favicon crop |
| Colour | Crimson `#A51C30` on light; white knockout on crimson; `currentColor` mono elsewhere |
| Never | Recolour, rotate, **close the gap**, add effects, stretch, or place the mark on a busy image |
| Dark mode | The mono mark inherits the foreground; the lockup uses the white knockout |

## 12. The design system

Defined in one `<style>` block in `web/templates/base.html`, deliberately: a second stylesheet is a
second place a colour can be defined, and the two drift.

| Element | Standard | Held by |
|---|---|---|
| **Palette** | `--crimson #A51C30` · `--ink #1C1C1E` · `--slate #4A4F57` · `--muted #7A7F87` · `--rule #D8D4CF` · `--parch #F6F3EF` | Convention |
| **Type** | Georgia for headings and statistics; the system sans for body; Consolas for anything a machine produced — a digest, a URN, a permission, a warrant | Convention |
| **Tier badges** | `TIER 1` crimson · `TIER 2` bronze · `TIER 3` slate · `TIER 4` grey · `UNTIERED` parchment. Always with the number | Convention |
| **Evidence colours** | `.evidence-ok` green, `.evidence-bad` crimson — used for *verdicts*, never for decoration | Convention |
| **Tables** | Search, sort and paging on every table; a header row on every table | **`tests/test_ui_tables.py`** |
| **Empty states** | Every empty state explains why it is empty and what the thing is for. The features card with no contract says how to bind one; the parameters card says what a version with no approved parameters may still do | Convention |
| **Refusals** | A refused page renders `forbidden.html` and says the record exists and is outside your scope. A refused action renders the API's `detail` and its `remediation`, not "an error occurred" | Convention |
| **Density** | Compact by default. Banks look at hundreds of rows | Convention |

Everything in the "convention" rows is a rule somebody can break without a test failing. That is
stated rather than implied, for the same reason as the rest of this document.

---

## 13. Traceability

| Section | Satisfies |
|---|---|
| §1 One process | [ADR-008](adr/ADR-008-server-rendered-ui.md); the gap against [ADR-011](adr/ADR-011-decoupled-frontend.md) |
| §1 Scope on pages | `FR-SEC-002`; [09 §2.4](09-security-compliance.md) |
| §6.6 CSRF token | [09 §2](09-security-compliance.md) |
| §6.5 Tables | `NFR-USE-002`, partially — the header rule is tested, the rest is not |
| §7 Not built | [12 §0](12-implementation-plan.md#0-build-status) is the authoritative build record |
| §8–§10 | [ADR-011](adr/ADR-011-decoupled-frontend.md); [11 — Adversarial Review](11-adversarial-review.md), the front-end section |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
