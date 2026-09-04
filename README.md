![MAYA — Model & AI Lifecycle Assurance](assets/logo/maya-lockup.png)

# MAYA

**Evidence, not assertion.**

*One system of record for every model a bank runs — statistical, machine-learned, generative,
calibrated, vendor-supplied, expert-judgment, rule-based, and end-user-computed.*

[Documentation](#documentation) · [Mathematical Foundations](docs/00-mathematical-foundations.md) ·
[Requirements](docs/03-requirements.md) · [Architecture](docs/04-architecture.md) ·
[Detailed Design](docs/14-detailed-design.md) · [Roadmap](docs/10-roadmap.md)

---

## The name

**māyā** (माया) — in Indian philosophy, *māyā* is **appearance**: the representation that stands in
for reality, and is so easily mistaken for it. The word is usually translated "illusion", which is
too strong. Māyā is not falsehood. It is a *rendering* of the world — useful, often necessary, and
dangerous only when you forget that it is a rendering.

That is exactly what a model is. The 2026 supervisory guidance says so almost in the same words:

> *"Models are simplified representations of real-world relationships… based on assumptions that make
> them useful in estimating values and predicting events, but which also can have limitations and
> create model risk."*
> — SR 26-2, §III

Model risk, in the end, is what happens when an organisation forgets the difference between the map
and the territory. The platform is named for the thing it governs, and for the discipline of never
mistaking it for the world.

| | |
|---|---|
| **Name** | MAYA — from Sanskrit *māyā* (माया), *appearance*, *representation* |
| **Tagline** | Model & AI Lifecycle Assurance |
| **Slogan** | **Evidence, not assertion.** |
| **Principle** | A model is a representation of the world. Governance is knowing the difference. |

### The mark

![The MAYA mark — a square inscribed in a circle](assets/logo/maya-mark-128.png)

The mark is a **square inscribed in a circle**.

It is the oldest model there is. Archimedes estimated π by inscribing and circumscribing polygons and
tightening the bound as the number of sides grew — a tractable figure standing in for one that cannot
be computed directly. A polygon is a *simplified representation* of a circle: useful, workable, and
wrong by a knowable amount.

Which gives the mark its reading. The **gap** between the square and the circle is the model error.
The **four points** are where the model and the world agree. Add sides and the gap closes but never
vanishes — no model becomes the thing it represents.

That is māyā, and it is model risk, in one figure.

---

## The problem

A large universal bank runs **800–3,000 models** and **5,000–50,000 end-user-computing assets**. Industry
surveys put roughly a fifth of commercial banks and most investment banks above 1,000 models, with every
surveyed bank reporting growth and some reporting more than 50% growth in two years.

Almost none of them are the thing MLOps tools assume. The estate includes closed-form pricers that are
never trained, vol surfaces recalibrated every morning, logistic scorecards refitted annually, XGBoost
fraud models retrained weekly, vendor black boxes whose internals are contractually unavailable,
expert-judgment country scorecards set by committee, AML rule sets, and LLM applications drafting
regulatory narratives.

The market splits cleanly, and neither half is whole:

| | Governance depth | Artifact & execution depth |
|---|---|---|
| **GRC / MRM platforms**<br/>OpenPages · SAS MRM · ValidMind · ModelOp · Yields.io | Excellent workflow, documentation and reporting | **None.** Nothing can verify that the model in the workflow is the model in production. They store *assertions about* models. |
| **MLOps platforms**<br/>MLflow/Unity Catalog · Databricks · SageMaker · Vertex · Domino | **None.** No materiality, approved use, effective challenge, overlay or finding | Excellent lineage and telemetry — for the 20–40% of the estate that passes through them |

Buying both produces two inventories that disagree, and the disagreement is itself an audit finding.

## What MAYA does differently

Six capabilities absent from every product surveyed in [our market research](docs/01-industry-research.md#5-commercial-and-open-source-landscape):

1. **One inventory across all nine trainability classes** — a Monte-Carlo XVA engine, a FICO black box, an
   XGBoost fraud model, a SAR-drafting LLM and a pricing spreadsheet, each with class-appropriate evidence.
2. **An immutable evidence graph** that cryptographically binds the governance record to the artifact,
   dataset snapshot, feature contract and fitting run — so *"validated"* is verifiable, not a checkbox.
3. **Governed execution warrants on demand** — any engine resolves a URN to a signed, entitlement-bound,
   revocable execution contract, with alias-based champion/challenger routing and a global kill switch.
4. **Approved-use vs actual-use reconciliation** — SS1/23 asks for intended use *compared to actual use*;
   MAYA observes it from warrant telemetry.
5. **A post-model-adjustment register** — overlays with quantified magnitude, mandatory expiry, downstream
   propagation and recurrence-trend detection.
6. **Compiled, always-fresh documentation** — model development documents, validation reports, model cards,
   EU AI Act Annex IV packs and AI-BOMs, generated from evidence with staleness detection.

## The five pillars

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  1 · UNIVERSAL INVENTORY      2 · EVIDENCE GRAPH        3 · FEATURE PLATFORM    │
│  All 9 trainability classes   Immutable, hash-chained   Delta Lake offline store│
│  Vendor · EUC · GenAI · quant Artifact ↔ governance     Point-in-time correct   │
│  Multi-regime scoping         Reproducible to the byte  Feature contracts       │
│  Continuous discovery         BCBS 239 by construction  Skew & drift detection  │
├─────────────────────────────────────────────────────────────────────────────────┤
│  4 · GOVERNED EXECUTION                    5 · LIVING DOCUMENTATION             │
│  Signed warrants, issued on demand            Compiled from the evidence graph     │
│  champion / challenger / shadow aliases    MDD · validation report · model card │
│  Policy enforced at issuance and at call   EU AI Act Annex IV · AI-BOM          │
│  Kill switch ≤ 60 s · fails safe           Staleness detected, never assumed    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Some models are never trained — and that is a design decision, not a footnote

Every MLOps product assumes `train → register → deploy`. Most bank models do not fit. MAYA classifies
every model by **how its parameters come to exist**, and that choice selects the lifecycle, the evidence
schema and the monitoring metrics.

| Class | Parameters obtained by | Examples | "Fit" step | Monitored on |
|---|---|---|---|---|
| **T0** | Theory — none to obtain | Black–Scholes, SA-CCR, LCR/NSFR, RWA engines | *none* | Implementation regression |
| **T1** | Solving against market data | Yield curves, SABR/Heston surfaces, HJM | `calibrate` | Calibration error, arbitrage checks |
| **T2** | Statistical estimation | PD scorecards, LGD, PPNR, deposit beta | `estimate` | KS · AUC · PSI · calibration |
| **T3** | Machine learning | Fraud, AML, churn, uplift | `train` | Drift, decay, fairness |
| **T4** | Continuous self-update | Adaptive fraud thresholds, bandits | `train` + online | Parallel outcomes analysis |
| **T5** | Configuration of a foundation model | Credit memos, SAR narratives, copilots | `configure` | Groundedness, hallucination, cost |
| **T6** | Vendor — inaccessible | FICO, Actimize, Murex | *none visible* | Own-outcomes divergence |
| **T7** | Expert elicitation | Country risk, RCSA, ESG | `elicit` | Override rate, outcome analysis |
| **T8** | Authored logic | AML rules, credit cut-offs, EUC | *none* | Rule-fire distribution |

Asking a Black–Scholes implementation for its training set is a type error, and MAYA can say so precisely.
See [02 — Model Taxonomy](docs/02-model-taxonomy.md) for the full catalogue across eleven domains.

## Built on stated mathematics

The design rests on six pillars, each chosen because it delivers an engineering property — not for
elegance. The laws they imply are stated in [00 §12](docs/00-mathematical-foundations.md#12-the-laws-maya-enforces),
and that section says of each law whether it is executable today or is still a claim about a design —
because a document that says *all* the laws run in CI, when six of them do, is the sort of thing this
platform exists to catch.

| Pillar | Mathematics | Property it delivers |
|---|---|---|
| What *is* a model? | **Markov categories** + the **Para construction** | One interface for all nine classes; training is *one way* to inhabit the parameter object, not part of the definition |
| How do models compose? | **Symmetric monoidal categories**, string diagrams | Typed composite warrants; blast radius; aggregate risk as **lax** monoidality — the interaction premium regulators ask about becomes computable |
| What can we say about a black box? | **Assume–guarantee contracts**, **Galois connections**, probe-relative **Yoneda** | Operating boundaries checked at runtime; version substitution decided by refinement, not by meeting; model cards that are provably sound over-approximations |
| How is everything indexed? | **Fibrations** / Grothendieck construction | **New model classes require no schema migration** — supply a fibre, change nothing else |
| How do many regulators coexist? | **Institutions** (Goguen–Burstall abstract model theory) | **New regulators require no schema migration**; scope determinations are derivations with citations, not flags |
| How is evidence accounted for? | **Commutative semirings** (provenance) + lattices + bitemporal algebra | *One* evidence engine answers six different questions — sufficiency, minimal justification, corroboration, confidence, cost, currency — by swapping the semiring over a single traversal |

Full treatment, including what we deliberately **did not** adopt and why:
[00 — Mathematical Foundations](docs/00-mathematical-foundations.md).

## Regulatory grounding

Current as of **September 2026**, and deliberately built to survive the next change:

- **SR 26-2 / OCC Bulletin 2026-13 / FDIC** (17 April 2026) — supersedes SR 11-7 and SR 21-8. Principles-based
  and materiality-driven; narrows the model definition to exclude spreadsheets and deterministic rules; and
  explicitly places **generative and agentic AI outside scope** while expecting them to be governed.
- **PRA SS1/23** (amended April 2026) — a materially *broader* model definition, prescribed inventory
  attributes, two-axis tiering, and a first-class post-model-adjustment regime.
- **EU AI Act** — high-risk obligations from 2 August 2026; consumer credit scoring is Annex III(5)(b).
- Plus NIST AI RMF, ISO/IEC 42001, Basel (IRB, FRTB, SA-CCR, IRRBB), IFRS 9 / CECL, ECOA / Reg B and CFPB
  expectations, BCBS 239, and SOX.

A global bank must satisfy a *narrow* US scope and a *broad* UK scope over the same inventory,
simultaneously. That is why regulatory regimes are institutions rather than a column — and why SR 11-7
being replaced mid-design cost this architecture nothing.

## Architecture at a glance

**Target:** front end and backend as separate, concurrently running processes, the UI consuming the
same public API as any third-party client ([ADR-011](docs/adr/ADR-011-decoupled-frontend.md)).

**As built:** one process. The UI is server-rendered Jinja2 inside the FastAPI application and makes
41 direct in-process service calls, so *reads* do not go through the API — writes, from the browser
over jQuery, do. Anyone planning management information on the public API should know that the
screens can currently see things the API cannot.

```
     maya-web (separate process)        SDK / CLI     Execution engines
     Bootstrap 5 + jQuery, static            │                 │
                        │                    │                 │
                   ┌────┴────────────────────┴────┐            │
                   │   API gateway · OIDC · WAF   │            │
                   └────┬─────────────────────────┘            │
                        │                                      │
   ┌────────────────────┴──────────────────┐      ┌────────────┴────────────┐
   │   maya-api  (FastAPI monolith)        │      │      maya-warrants         │
   │  registry · features · lifecycle      │      │  resolve · sign · revoke│
   │  validation · overlays · evidence     │      │  p99 < 50 ms · 99.99%   │
   │  policy/regimes · risk · docs · IAM   │      │  survives control outage│
   └───┬──────────────┬──────────────┬─────┘      └────────────┬────────────┘
       │              │              │                         │
  ┌────┴────┐   ┌─────┴─────┐  ┌─────┴──────┐            ┌─────┴─────┐
  │Postgres │   │Delta Lake │  │Object store│            │   Redis   │
  │governance│  │features   │  │artifacts   │            │warrant cache │
  │ · RLS    │  │telemetry  │  │WORM tier   │            │           │
  └──────────┘  └───────────┘  └────────────┘            └───────────┘
                        │
              ┌─────────┴──────────┐        ┌──────────────────────────┐
              │ Celery workers     │        │ Sandbox fleet (gVisor)   │
              │ ingest · docs      │        │ artifact load · replay   │
              │ monitors · notify  │        │ never in the control plane│
              └────────────────────┘        └──────────────────────────┘
```

Details: [04 — Architecture](docs/04-architecture.md). Deployables, failure modes and scaling in §3, §14, §16.

## Warrants — running a model on demand

An execution engine holds nothing but a URN. Everything else is resolved, signed and policy-checked at
runtime.

```python
import maya

model = maya.load(
    "maya://model/credit.pd.smallbiz#champion",   # follows governed alias moves
    use="origination_decision",                   # must be an approved use
    entity="LE-US-01",
)

r = model.predict({"customer_id": "C-88213", "request_amount": 250_000})

r.prediction      # {'pd_12m': 0.0187, 'score': 712}
r.model_version   # '3.2.1'  — attributable, always
r.boundary_ok     # True     — input satisfies the contract's assumptions
r.reason_codes    # ['DSCR_LOW', 'THIN_FILE']  → Reg B adverse action

# Pin exactly, to reproduce a decision made months ago
maya.load("maya://model/credit.pd.smallbiz@3.1.0?calibration=2026-03-31")
```

A warrant is the product of four independent vocabularies — how the parameter object is inhabited ×
how the kernel is realised (**eighteen runtimes**, from QuantLib and ONNX to a spreadsheet and a
prompt bundle) × what is asked of it (**ten verbs**) × where its data comes from (**twelve
bindings**). `descriptor_only` is one of the eighteen and matters most in a bank: most of the estate
already runs inside engines nobody is going to replace. The captive engine implements four of the
seventeen; the rest are refused by name rather than approximated.

Moving `champion` from 3.2.1 to 3.3.0 requires the new version's contract to **refine** the old one and its
schemas to satisfy variance rules. Consumers are not redeployed and cannot be broken. Revocation takes
effect in under 60 seconds. If MAYA is down, already-authorised scoring keeps running — governance must not
become the bank's single point of failure.

Full protocol: [06 — Warrants & Execution](docs/06-warrants-and-execution.md).

## Documentation

All specification documents live in [`docs/`](docs/). The three anchors are marked ★.

| # | Document | What it is |
|---|---|---|
| **00** | [Mathematical Foundations](docs/00-mathematical-foundations.md) | Six pillars, nineteen laws with an honest statement of which are executable today, and what was deliberately not adopted |
| **01** | [Industry Research](docs/01-industry-research.md) | SR 26-2, SS1/23, EU AI Act; ~15 products surveyed; the six-capability gap |
| **02** | [Model Taxonomy](docs/02-model-taxonomy.md) | 200+ model families across eleven domains, with the T0–T8 trainability classification |
| **03** | [Requirements](docs/03-requirements.md) ★ | 13 personas, 220 numbered functional requirements plus 26 non-functional, regulatory traceability matrix |
| **04** | [Architecture](docs/04-architecture.md) ★ | Containers, bounded contexts, lifecycles, extensibility, deployment, failure modes |
| **05** | [Data Model](docs/05-data-model.md) | Postgres DDL, Delta Lake schemas, evidence graph, warrant projection, migrations |
| **06** | [Warrants & Execution](docs/06-warrants-and-execution.md) | URNs, signed descriptors, resolution, aliases, revocation floor, composites |
| **07** | [Feature Platform](docs/07-feature-platform.md) | Bitemporal store, point-in-time correctness, contracts, version-namespaced serving |
| **08** | [UI / UX](docs/08-ui-ux.md) | Decoupled front end, information architecture, key screens, brand and design system |
| **09** | [Security & Compliance](docs/09-security-compliance.md) | Threat model, artifact security, GenAI controls, fair lending, control library |
| **10** | [Roadmap](docs/10-roadmap.md) | Seven phases, team shape, delivery risks, build/buy record |
| **11** | [Adversarial Design Review](docs/11-adversarial-review.md) | 27 findings red-teamed against the design, with dispositions |
| **12** | [Implementation Plan](docs/12-implementation-plan.md) | Repo topology, module contracts, CI gates, workstreams, definitions of done |
| **13** | [AI, LLMs and Agents Inside the Platform](docs/13-ai-in-the-platform.md) | Where AI belongs in the system itself — and where it must not go |
| **14** | [Detailed System Design](docs/14-detailed-design.md) ★ | The level below the architecture: component interfaces, algorithms, transaction boundaries, error taxonomy, SLOs, capacity |
| **15** | [Featuresets and the Parameter Object](docs/15-featuresets-and-parameters.md) | A named, versioned presentation of X; derived features; and the fitted parameters an engine returns |
| **16** | [Features Composed, Shaped and Prepared](docs/16-features-composed-and-shaped.md) | Dimensionality, the composition monoid, sealing and ephemerality, ownership, and point-in-time retrieval |
| — | [Architecture Decision Records](docs/adr/INDEX.md) | Eleven ADRs |

**Reading paths**

- **Executive** — [01 §1](docs/01-industry-research.md), [01 §6](docs/01-industry-research.md), [10 §5](docs/10-roadmap.md), the research deck
- **Engineer** — [00 §2](docs/00-mathematical-foundations.md), [04](docs/04-architecture.md), **[14](docs/14-detailed-design.md)**, [05](docs/05-data-model.md), [06](docs/06-warrants-and-execution.md), [12](docs/12-implementation-plan.md)
- **Regulator / auditor** — [01 §2](docs/01-industry-research.md), [03 §10](docs/03-requirements.md), [09 §7](docs/09-security-compliance.md)
- **Sceptic** — [11](docs/11-adversarial-review.md), then [00 §13](docs/00-mathematical-foundations.md)
- **AI strategy** — [13](docs/13-ai-in-the-platform.md), then [09 §5](docs/09-security-compliance.md)

## Repository layout

```
maya/
├── README.md                        ← the only README; this file
├── core/                            the platform, split by responsibility
│   ├── domain/                      the algebra: kernels, schemas, contracts, identity
│   ├── registry/                    models, immutable versions, governed aliases
│   ├── features/                    features, views, featuresets, shapes, composition,
│   │                                lifecycle, retrieval policy, alignment, bulk transfer
│   ├── parameters/                  inhabitants of P: fitted, calibrated, declared
│   ├── execution/                   warrants, the grammar, the runtimes, the sandbox
│   ├── validation/  monitoring/     tests and findings; drift and delayed labels
│   ├── telemetry/                   two bitemporal streams, idempotent ingestion
│   ├── lifecycle/                   version approval by quorum, attestation, amendment
│   ├── authz/                       roles, scope, segregation of duties, OIDC, RS256
│   ├── policy/                      versioned gates: a rule is a predicate, with its cases
│   ├── docs/  attachments/          documentation compiled, and documentation filed
│   ├── overlays/                    post-model adjustments, time-boxed
│   ├── regimes/                     supervisory regimes as institutions
│   ├── assist/  baseline/           machine assistance; cold-start import
│   ├── scheduler/  notify/          idempotent jobs; digests, not a message per item
│   ├── estate/                      the worklist and the summary, derived not assigned
│   └── evidence/  risk/  content/   the chain; tiering; rendered help
│       config/                      YAML with a git-ignored local overlay
├── db/                              the only package that knows about storage
│   └── schema/                      two hand-written schemas, 43 tables, no migrations
├── routes/  web/                    the HTTP surface and the vendored interface
├── content/                         help and tutorials, rendered at request time
├── examples/warrants/               thirteen worked warrants across the model estate
├── docs/                            17 specification documents + ADRs
│   ├── 00 … 16-*.md                 the specification
│   ├── adr/INDEX.md                 eleven architecture decision records
│   ├── examples/                    the two FRED series the worked example uses
│   ├── research/                    the paper and the article (product-neutral)
│   ├── Models-as-Parametric-Kernels.pptx    27-slide research deck
│   ├── MAYA-System-Design.pptx              56-slide system design deck
│   └── MAYA-Model-and-Feature-Engineering.pptx
│                                     33-slide practitioner deck, with its data embedded
├── assets/logo/                     the mark, the lockup, and their variants
└── tools/deck/                      deck generator, logo generator, geometry audit
```

## Research output

The ideas behind this system are written up independently of the product:

| Artefact | Audience |
|---|---|
| **[Models as Parametric Kernels, Governance as Verified Automation](docs/research/models-as-parametric-kernels.pdf)** — 34-page paper, [LaTeX source](docs/research/models-as-parametric-kernels.tex) | Academic. Formal definitions; an impossibility theorem for aggregate risk; conservative-extension and satisfaction-condition results; and an **oracle criterion for where AI may do governance work** — each with a plain-language gloss and a worked banking example |
| **[Most of Your Models Were Never Trained](docs/research/most-of-your-models-were-never-trained.md)** | General technical readers |
| **[Models as Parametric Kernels](docs/Models-as-Parametric-Kernels.pptx)** — 27 slides | Conversation-starter deck mirroring the paper: the problem, the formal foundation, automation and its oracles, and six questions worth arguing about |

The paper, the article and the research deck are deliberately **product-neutral** — no MAYA name, no
branding — so the ideas can be judged on their own. The engineering material below carries the brand.

| Engineering artefact | Audience |
|---|---|
| **[MAYA — Detailed System Design](docs/MAYA-System-Design.pptx)** — 56 slides | Eight chapters: overview and design rules, core domain and registry, governance subsystems, data and features, execution and warrants, machine assistance, interfaces, cross-cutting and operations |
| **[14 — Detailed System Design](docs/14-detailed-design.md)** | The written form: interfaces, algorithms, transaction boundaries, concurrency, error taxonomy, SLOs, capacity model |

*Ashutosh Sinha, Independent Researcher.*

## Status

**Specification complete and adversarially reviewed. Every planned component is built.**

The register, the feature platform, warrants and their grammar, validation and
findings, the record lifecycle with quorum attestation, authorisation with
segregation of duties read from the evidence chain, monitoring with delayed
labels, compiled documentation, the overlay register, supervisory regimes as
institutions, machine assistance, and baseline import with compliance debt.

Build status, what is genuinely working, and the honest gaps are recorded in one
place and kept current there:

### → [12 — Implementation Plan §0, Build status](docs/12-implementation-plan.md#0-build-status)

That document also carries the repository topology, the CI-enforced module
boundaries, the front-end/backend contract, the test strategy and the phase
sequence. [10 — Roadmap](docs/10-roadmap.md) sets out the phases at programme
level, and [11 — Adversarial Design Review](docs/11-adversarial-review.md) records
the 27 findings red-teamed against the design before any code was written.

---

## Licence

Copyright © 2026 **Ashutosh Sinha** <ajsinha@gmail.com>. All rights reserved.

| Scope | Licence |
|---|---|
| Everything except `docs/research/` — specification, architecture, design, data model, protocols, source code, tooling, decks, brand assets | **Proprietary, All Rights Reserved** — see [LICENSE](LICENSE) |
| `docs/research/` — the paper and the article | **[CC BY-NC-ND 4.0](docs/research/LICENSE)** — share with attribution; no commercial use, no derivatives |

`MAYA`, the MAYA mark, "Model & AI Lifecycle Assurance" and "Evidence, not assertion." are used as
trademarks of the Author. Access to this repository grants no licence to use them.

Legal notices, third-party attributions, the treatment of quoted regulation, and the AI-assistance
disclosure are recorded in [NOTICE](NOTICE).

> **Not legal, regulatory or financial advice.** These are engineering and research documents produced
> in a personal capacity. Any encoding of a regulation here is a *claim about* that regulation, not the
> regulation. Regulatory obligations depend on jurisdiction, entity and facts, and change over time.
> Obtain qualified professional advice before acting. See [NOTICE §4](NOTICE).

Licensing enquiries and permission requests: **ajsinha@gmail.com**

---

## Contributing

Read [00 — Mathematical Foundations](docs/00-mathematical-foundations.md) before proposing changes to
`core/domain/`, and read the relevant [ADR](docs/adr/) before revisiting a settled decision. New
abstractions must pass the **rent test**: an abstraction earns its place only if it delivers a property we
would otherwise have to hand-build, hand-check or hand-migrate — and only if that property is stated as an
executable law.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
