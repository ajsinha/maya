![MAYA — Model & AI Lifecycle Assurance](assets/logo/maya-lockup.png)

# MAYA

**Evidence, not assertion.**

*One system of record for every model a bank runs — statistical, machine-learned, generative,
calibrated, vendor-supplied, expert-judgment, rule-based, and end-user-computed.*

[The idea](#the-idea) · [What is built](#what-is-built) · [Try it](#try-it) ·
[Documentation](#documentation) · [Research](#research) · [Layout](#repository-layout)

---

## The name

**māyā** (माया) — in Indian philosophy, *māyā* is **appearance**: the representation that stands in
for reality and is so easily mistaken for it. The usual translation, "illusion", is too strong. Māyā
is not falsehood. It is a *rendering* of the world — useful, often necessary, and dangerous only when
you forget that it is a rendering.

That is exactly what a model is. The supervisory guidance says so in almost the same words:

> *"Models are simplified representations of real-world relationships… based on assumptions that make
> them useful in estimating values and predicting events, but which also can have limitations and
> create model risk."*
> — SR 26-2, §III

Model risk is what happens when an organisation forgets the difference between the map and the
territory. The platform is named for the thing it governs, and for the discipline of never mistaking
it for the world.

| | |
|---|---|
| **Name** | MAYA — from Sanskrit *māyā* (माया), *appearance*, *representation* |
| **Tagline** | Model & AI Lifecycle Assurance |
| **Slogan** | **Evidence, not assertion.** |
| **Principle** | A model is a representation of the world. Governance is knowing the difference. |

### The mark

![The MAYA mark — a square inscribed in a circle](assets/logo/maya-mark-128.png)

A **square inscribed in a circle** — the oldest model there is. Archimedes estimated π by inscribing
and circumscribing polygons and tightening the bound as the sides multiplied: a tractable figure
standing in for one that cannot be computed directly.

The **gap** between the square and the circle is the model error. The **four points** are where the
model and the world agree. Add sides and the gap closes but never vanishes — no model becomes the
thing it represents.

That is māyā, and it is model risk, in one figure.

---

## The problem

A bank's model estate is not one kind of thing. It is a pricing library with no parameters to fit, a
scorecard estimated on eight thousand rows, a term-structure model recalibrated every morning, a
network with twenty million weights, a language model somebody else hosts, a vendor black box under
licence, and four thousand spreadsheets. Model risk management is expected to cover all of it with
one process.

So the tooling asks *is it AI?* — and that question separates nothing useful. It puts a Black–Scholes
pricer and a linear regression in different buckets while putting a regression and a large language
model in the same one. Everything downstream inherits the confusion: a validation checklist with
fields that make no sense for half the estate, an inventory whose categories nobody can apply
consistently, and controls that are ceremony for some models and absent for others.

The deeper failure is that **governance is asserted rather than evidenced**. A spreadsheet says a
model was validated. A ticket says a finding was closed. Nothing connects the assertion to the
artefact, so an examiner is shown a claim and asked to believe it, and the organisation's own risk
committee is in the same position.

---

## The idea

**A model is a parametric kernel:**

```
f : P ⊗ X → D(Y)
```

Parameters, tensored with inputs, mapping to a *distribution* over outputs. That is the whole
definition, and everything else in the platform is derived from it.

Three consequences, and each one dissolves a problem rather than managing it.

**Trainability is derived, never declared.** Ask not *is it AI* but *how is `P` inhabited?* — from
theory (nothing to fit), from a solver against market quotes, from a statistical estimator, from a
training run, from a configuration, from a room full of people, or from inside a vendor's binary.
That question sorts the estate correctly, and the class **T0–T8** falls out of the answer. Nobody
self-reports it, so asking a closed-form pricer for its training set is a *type error* rather than an
empty field.

**Parameters are not versions.** A version is the kernel; a parameter set is a point of `P`.
Refitting produces a new point, not a new kernel — which is what lets a daily recalibration procedure
be approved once instead of pretending a committee meets every morning.

**A model's inputs are half of it.** `X` is a **featureset**: a schema of named slots, each version
of it binding every slot to an exact feature and an exact pinned view version. A model is defined
over the *slots*, so swapping what fills one does not change the model's input space — it changes
what the model was fitted on, which is a different event with a different control.

---

## What MAYA does differently

| | |
|---|---|
| **It does not run models.** | It issues a signed, expiring, entitlement-bound **warrant**, and an execution engine acts on it. Governance is therefore never in the serving path, and a governed version move requires no consumer to redeploy. |
| **Evidence, not assertion.** | Every governance claim is bound to the artefact it rests on, in an append-only hash-chained record. There is no separate audit log: two records of who did what are two records that can disagree, and segregation of duties is decided by reading the chain. |
| **Refusals are the product.** | Every refusal names what was violated and what to do about it. The interesting behaviour of this platform is what it *will not* do. |
| **Laws, not conventions.** | Twenty-one foundational laws are stated; **sixteen run in the test suite** and a failing one fails the build. The five that do not run are named, with the reason. |
| **Derived, not entered.** | The tier, the worklist, the estate summary, the documentation, the board pack: computed from the register. Nothing that can be derived is stored, because a stored derivation is one that can go stale. |

---

## The five pillars

| | Pillar | What it means |
|---|---|---|
| **1** | **Inventory** | Every model, with an owner, a purpose, a tier and a lifecycle state — and a dependency graph in which `input_to` is a **typed composition** rather than a drawing |
| **2** | **Data** | Features and featuresets as governed objects on **two clocks**, with a point-in-time read whose reproducibility is a law rather than a convention |
| **3** | **Execution** | Warrants: a four-axis grammar with fourteen admissibility laws, checked before the signature |
| **4** | **Assurance** | Validation, findings, monitoring with delayed labels, overlays, and supervisory regimes encoded as institutions |
| **5** | **Documentation** | Compiled from the register, filed against what it is *about*, and walkable as a **graph** rather than a list |

---

## Some models are never trained — and that is a design decision, not a footnote

Most of what a bank runs is not learned from data. A discount factor, a swaption price, a bond's
accrued interest: these come from theory. There is nothing to fit, no training set, no drift in the
usual sense — and a platform that assumes otherwise makes its users write "N/A" in fields until they
stop reading the fields at all.

MAYA treats that case as first-class. `parameter_kind: none` means `P` is the terminal object; the
class is **T0**; and a fit warrant is **refused**, naming the fact about the kernel that made the
request incoherent:

```json
{"error": "nothing_to_fit",
 "detail": "markets.pricing.vanilla 1.0.0 is T0: its parameter object is the terminal
            object, so there is no point of P to move to",
 "remediation": "if this model does have parameters, the kernel declares the wrong
                 parameter_kind; fix the version rather than the warrant"}
```

What is governed instead moves to where the risk actually is: the conventions, the curve, the
valuation date, the library version, and the **domain of applicability** the model was benchmarked
in. The fibre table in [02 §4](docs/02-model-taxonomy.md) gives the same treatment to every
class: what inhabits `P`, what fits it, what runs it, and what evidence it owes.

---

## And some models are just rules somebody wrote

The class a bank has most of by count is **T8** — a rule set: eligibility criteria, exclusion lists,
limit checks, the band assignment on the end of a scorecard. In practice it is a spreadsheet, a
stored procedure, or a paragraph of policy transcribed into code once, and no tool says anything
about it.

MAYA always held these as `P` — versioned, digested, approved by a second person — and held them as
an opaque JSON blob, which meant it could tell you a rule set had changed and nothing about what it
said. A rule set now has a **structure**: ordered rules, first match wins, a required `otherwise`, a
required `because` per rule, and conditions that are trees of `field op value` with no arithmetic.
The restriction is the point. Four questions become decidable that are undecidable over a free
expression:

| | |
|---|---|
| **Totality** | `otherwise` is required, so no input falls through — by construction, not by analysis |
| **Reachability** | a rule an earlier rule already covers can never fire, and nothing about reading the document tells you so. A rule that never fires also never produces a wrong answer, so it survives every review while somebody believes it is in force |
| **Contradiction** | the same condition reaching two different outcomes |
| **Conformance** | every field a rule reads is declared on the version, no ordered comparison is asked of a field that has no order, and no field is compared against a value of the wrong kind |

The reachability analysis is **sound and incomplete**, and the honest statement of it is the
promise: *no rule is shadowed by any single earlier rule.* Two earlier rules that between them cover
a third are **not** detected — that is satisfiability over the whole set, which is a solver, and a
solver here is a dependency whose failure modes nobody in the bank can debug.

This is also the one place MAYA edits a model, and the boundary is intact rather than bent. **MAYA
does not become the authoring tool; it becomes an editor for a parameter set it already held.**
Publishing is the ordinary parameter-set record — the set lands `proposed`, and self-approval is
still refused. There is deliberately no ONNX or PMML editor: those serialize a *fitted* map, and
hand-authoring one would mint an artifact indistinguishable in the register from a trained one. A
rule set has no training run to be indistinguishable from — authorship *is* its provenance.

And the `rules` runtime, named by the grammar since the first milestone and implemented by nothing
until now, means a rule set is finally run by the platform that governs it rather than by a stored
procedure nobody compared it against. Every decision names the rule that made it, because a bank
that cannot attribute a refusal cannot explain it — and under most consumer-credit regimes the
explanation is the obligation, not the decision.

---

## Built on stated mathematics

| Question | Structure | What it buys |
|---|---|---|
| What *is* a model? | `Para(Stoch)` — parametric maps into distributions | One definition covering every family; trainability derived rather than declared |
| When may one replace another? | **Contract refinement** and **schema variance** | An alias move is a proof obligation, not a deployment |
| Does this fit where that fitted? | A **lattice** on schemas (`L-20`) | One order answering four questions that previously had four implementations |
| How do models compose? | Typed composition (`L-21`); symmetric monoidal structure | A `input_to` edge that does not type-check is refused; a composite has a *derived* schema |
| What supports a claim? | **Provenance semirings**, including the universal `ℕ[X]` | Six questions from one traversal — sufficiency, minimal support, corroboration, trust, cost, currency — and the law that makes that a theorem (`L-9`) |
| Was a training set honest? | **Bitemporal** algebra with a named `AsOf` operator | Reproducibility as a *saturation law*: every read at or after the label gives the same answer |
| How do regulators differ? | **Institutions** and comorphisms | A regime is a signature, some sentences and a translation; adding one needs no core change |
| Is an obligation set coherent? | Deontic consistency (`L-16`) | A regime that obliges and forbids the same term cannot be activated |
| Can aggregate risk be one number? | **Lax** monoidality | No — and the board pack says so rather than producing one |

Full treatment: [00 — Mathematical Foundations](docs/00-mathematical-foundations.md). The law table
in §12 states each law, whether it runs, and where.

---

## Regulatory grounding

Encoded as **institutions** — a signature, obligations in that vocabulary, and a translation into the
core — so that a regime's determinations are made in *its* terms and can be defended in them.

| Regime | Encoded |
|---|---|
| **SR 26-2** (Federal Reserve / OCC) | Model definition, effective challenge, tiering, use-test |
| **PRA SS1/23** (Bank of England) | Principles 1–5, model families, senior-manager accountability |
| **EU AI Act** | High-risk classification, Annex IV technical documentation, human oversight |
| **SOX / SS3/18 / TRIM** | Documented as design targets rather than encoded |

The **satisfaction condition** — truth invariant under change of notation — is *checked* against probe
states before a regime can be activated, and a regime whose encoding fails it cannot be turned on.
Regimes that disagree are reported as disagreeing rather than merged.

---

## Warrants — running a model on demand

A consumer holds a **URN**, never a version:

```
maya://model/credit.pd.smallbiz#champion
```

Everything else resolves at the moment of use, against the policy in force at that moment. Promoting
a version requires no consumer to redeploy; revocation takes effect in under sixty seconds; an open
blocking finding stops resolution, so a validation finding actually stops the model rather than
generating an email.

A warrant is the product of **four independent vocabularies** — how `P` is inhabited × how the kernel
is realised (**nineteen runtimes**) × what is asked of it (**ten verbs**) × where its data comes from
(**twelve bindings**). `descriptor_only` is one of the nineteen and matters most in a bank: much of
the estate already runs inside engines nobody is going to replace.

**Warrants differ by kind of model as refusals over one document, never as different documents.**
Fourteen admissibility laws are checked before the signature. The last three quantify over facts the
platform *derives* rather than a category anybody attached: a calibration must state its `as_of`
(**L-W11**) or staleness is silent; parameters living inside an artifact need that artifact digested
(**L-W12**); a generative runtime must pin the build rather than the model family (**L-W13**).

What *is* templated is the **request**. A warrant profile fills holes in it, selected by the same
derived facts, folded by the `L-19` monoid, and refused at creation if it reaches for authority.

```bash
# Pin exactly, to reproduce a decision made months ago
maya://model/credit.pd.smallbiz@3.2.1
```

Full protocol: [06 — Warrants & Execution](docs/06-warrants-and-execution.md).

---

## Documentation

Documentation arrives at **five moments about five objects**, and it is filed against what it is
*about*: a methodology paper about the **model**, a specification about the **version**, a training
record about one **parameter set**, a data dictionary about one **featureset version**, an
independent recode about a **validation**.

A subject is always **pinned** — `featureset_version`, never `featureset` — because a document filed
against the set would describe something that has since moved.

Four kinds are **compiled** from the register and the evidence graph by fifteen lenses, so they cannot
drift from what they describe. A fifth, the **training record**, is compiled per parameter set: a
model recalibrated every morning produces two hundred and fifty governed acts a year, and until now
none of them had a record anybody could read.

The **dossier** walks the whole graph from a model — versions, their parameter sets, the featureset
versions those were fitted from, and the features in them — and every node with nothing filed is a
**named gap** rather than a blank, because a page that silently omits what it could not find reads as
complete.

An **export pack** carries the same graph, digested member by member, to somebody who will never be
given a login.

---

## What is built

**Specification complete and adversarially reviewed. Every planned component is built.**

The register, the feature platform, warrants and their grammar, validation and findings, the record
lifecycle with quorum attestation, authorisation with segregation of duties read from the evidence
chain, monitoring with delayed labels, compiled documentation and the documentation graph, the
overlay register, supervisory regimes as institutions, machine assistance, baseline import with
compliance debt, the content-addressed artifact store, export packs, risk appetite with the board
pack, rule sets for the T8 estate with the runtime that executes them, and a dependency-free Python
SDK.

Build status, what is genuinely working, and the honest gaps are recorded in one place and kept
current there:

### → [12 — Implementation Plan §0, Build status](docs/12-implementation-plan.md#0-build-status)

| | |
|---|---|
| Tests | **over 2,300 passing**, plus a scale suite excluded by default |
| Foundational laws executable | **16 of 21** — the five that are not are named with the reason |
| Warrant admissibility laws | **14 of 14**, checked before every signature |
| Database | SQLite by default, PostgreSQL by URL alone. One typed schema, **51 tables**, DDL generated per dialect, no migrations |
| Dependencies | Everything vendored. No CDN, no external calls, deployable air-gapped |

---

## Try it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run_maya_web.py
```

Then <http://localhost:5006> — sign in as `admin` / `maya-admin-dev`, and change that before anybody else
can reach it.

**With something in it.** An empty register is a poor way to judge a register, so there is a script
that builds a demonstration estate — five models across five trainability classes, a typed
`input_to` edge, features in a materialised view of bitemporal rows, a published featureset,
warrants, documents, telemetry and an open finding. Everything goes through the HTTP API as a client
would; nothing is inserted, because an estate assembled by writing rows would show screens in states
the platform cannot actually reach.

```bash
.venv/bin/python tools/demo/seed_estate.py --data ./data/demo
.venv/bin/python run_maya_web.py --config ./data/demo/application.yaml
```

The server takes `--config`, then `MAYA_CONFIG`, then the file in the repository. A second instance
should never require editing a tracked file.

Or from Python, with no dependencies at all:

```python
from maya_sdk import Maya, Blocked

maya = Maya("http://localhost:5006", "d.raman", "…")
maya.models.register(urn="maya://model/credit.pd.smallbiz", name="SB PD",
                     model_class="credit.pd.scorecard", domain="credit",
                     owner="person/j.okafor", legal_entity="LE-US-01",
                     purpose="12-month PD at origination")

try:
    maya.versions.promote("maya://model/credit.pd.smallbiz", semver="3.3.0")
except Blocked as refusal:
    print(refusal.detail)        # an open blocking finding stands against it
    print(refusal.remediation)   # close it, or ask the validator to downgrade it
```

The **compliant path is the fast path**, deliberately: if registering a model properly took forty
lines of HTTP plumbing and getting it wrong took four, the register would fill with models nobody
registered properly.

---

## Documentation

### Learning it

| | |
|---|---|
| [**Help**](content/help/) | Seventeen topics in seven sections, rendered in the interface at `/help` |
| [**Tutorials**](content/tutorials/) | Six walkthroughs, rendered at `/tutorials`. One per subsystem — defining a model, features, featuresets, warrants and training, the model package — and one end to end. Each shows the **UI, the SDK and curl** for every step, and every command in them was executed against a running instance before it was written down |

### Specifying it

| # | Document | Covers |
|---|---|---|
| **00** | [Mathematical Foundations](docs/00-mathematical-foundations.md) ★ | The definitions, the theorems, and the law table with what runs |
| **01** | [Industry Research](docs/01-industry-research.md) | The estate as it is, and what the incumbent tools do |
| **02** | [Model Taxonomy](docs/02-model-taxonomy.md) | Families, fibres, and what each needs as evidence |
| **03** | [Requirements](docs/03-requirements.md) | ~200 numbered requirements with regulatory traceability |
| **04** | [Architecture](docs/04-architecture.md) | Containers, bounded contexts, extension points, failure modes |
| **05** | [Data Model](docs/05-data-model.md) | One typed schema rendered to both dialects, the evidence graph, the data-plane layout |
| **06** | [Warrants & Execution](docs/06-warrants-and-execution.md) | URNs, the grammar, resolution, revocation, composites |
| **07** | [Feature Platform](docs/07-feature-platform.md) | Two clocks, point-in-time assembly, contracts, transfer, Delta or Iceberg |
| **08** | [UI & UX](docs/08-ui-ux.md) | The interface, and the tense warning on what is designed versus built |
| **09** | [Security & Compliance](docs/09-security-compliance.md) | Threat model, sandbox, identity, ambient authority, audit |
| **10** | [What Is Left](docs/10-roadmap.md) | What remains, why each thing is not built, and the order it should be done in |
| **11** | [Adversarial Review](docs/11-adversarial-review.md) | 27 findings; 17 required redesign, and what each cost |
| **12** | [The Build](docs/12-implementation-plan.md) ★ | **The authoritative record of what exists** — and what the build taught: five ways a control can be green and inert |
| **13** | [AI in the Platform](docs/13-ai-in-the-platform.md) | Where machine assistance may act, and the oracle criterion |
| **14** | [Detailed Design](docs/14-detailed-design.md) ★ | Interfaces, algorithms, transaction boundaries, SLOs, capacity |
| **15** | [X and P](docs/15-featuresets-and-parameters.md) | The two letters that are not the kernel: featuresets, derived features on the provenance polynomial, and the parameter object |
| **16** | [Five Things a Feature Is Not](docs/16-features-composed-and-shaped.md) | Not a number, not defined in one place, not mutable, not permanent, not its author's — and what happens between the store and the model |
| **17** | [The Algebra](docs/17-feature-and-model-algebra.md) | One order for four questions; the `AsOf` operator and its saturation law; derived features on the provenance polynomial; typed composition; the documentation graph |
| — | [ADRs](docs/adr/INDEX.md) | Eleven architecture decision records |

---

## Research

| Artefact | Audience |
|---|---|
| [**Models as Parametric Kernels, Governance as Verified Automation**](docs/research/models-as-parametric-kernels.pdf) — 34-page paper, [LaTeX source](docs/research/models-as-parametric-kernels.tex) | Academic. Formal definitions; an impossibility theorem for aggregate risk; conservative-extension and satisfaction-condition results; and an **oracle criterion for where AI may do governance work** |
| [**The same argument in prose**](docs/research/models-as-parametric-kernels-article.md) | General technical readers. The definition and what it dissolves, why aggregate risk cannot compose, the two clocks and what a leak looks like, featuresets and the fold that composes them, artefacts that remember, and the oracle criterion |
| [**Models as Parametric Kernels**](docs/Models-as-Parametric-Kernels.pptx) — 27 slides | A conversation-starter deck mirroring the paper |

The paper, the article and the research deck are deliberately **product-neutral** — no MAYA name, no
branding — so the ideas can be judged on their own.

| Engineering artefact | Audience |
|---|---|
| [**MAYA — Model and Feature Management: Concepts and System Design**](docs/MAYA-Model-and-Feature-Management.pptx) — 114 slides | Five parts. **I Philosophy** — what a model is, why "is it AI?" separates nothing, the five positions this platform takes, and what the decision costs against each alternative by name. **II Foundations** — the definition, the algebra, two clocks, evidence and its semirings, and the laws with which of them run. **III Concepts** — feature, featureset, warrant, parameters, composition, documentation, and what MAYA refuses. **IV System design** — components, algorithms, transaction boundaries, operations. **V Worked examples** — eight kinds of model one at a time, then a worked example computed from two real FRED series **whose data is embedded in the file** |

*Ashutosh Sinha, Independent Researcher.*

---

## Repository layout

```
maya/
├── README.md                        ← the only README; this file
├── core/                            the platform, split by responsibility
│   ├── domain/                      the algebra: kernels, schemas, contracts, the lattice
│   ├── registry/                    models, immutable versions, governed aliases, typed composition
│   ├── features/                    features, views, featuresets, shapes, composition,
│   │                                lifecycle, retrieval policy, alignment, bulk transfer
│   ├── parameters/                  inhabitants of P: fitted, calibrated, declared
│   ├── rules/                       the T8 parameter object with a shape: conditions, the
│   │                                reachability analysis, the editor that mints no authority
│   ├── execution/                   warrants, the grammar, profiles, the runtimes, the sandbox
│   ├── artifacts/                   the content-addressed store: a file's name is its own hash
│   ├── validation/  monitoring/     tests and findings; drift and delayed labels
│   ├── telemetry/                   two bitemporal streams, idempotent ingestion
│   ├── lifecycle/                   version approval by quorum, attestation, amendment
│   ├── authz/                       roles, scope, segregation of duties, OIDC, RS256, CSRF
│   ├── policy/                      versioned gates: a rule is a predicate, with its cases
│   ├── docs/                        documents compiled; subjects, training records, the dossier
│   ├── attachments/                 documents filed, content-addressed
│   ├── export/                      export packs: digested, self-contained, gaps named
│   ├── reporting/                   risk appetite as a computable limit; the board pack
│   ├── overlays/                    post-model adjustments, time-boxed
│   ├── regimes/                     supervisory regimes as institutions
│   ├── assist/  baseline/           machine assistance; cold-start import
│   ├── scheduler/  notify/          idempotent jobs; digests, not a message per item
│   ├── estate/                      the worklist and the summary, derived not assigned
│   └── evidence/  risk/  content/   the chain and its semirings; tiering; rendered help
├── db/                              the only package that knows about storage
│   └── schema/                      tables.py — 51 typed tables; the .sql files are generated from it
├── maya_deltalake/                  the Delta subset MAYA uses, in pure Python — used where
│                                    binary wheels are forbidden and `deltalake` cannot install
│                                    (Iceberg is the other table format, by configuration)
├── routes/  web/                    the HTTP surface and the vendored interface
├── sdk/                             clients, one folder per language
│   ├── python/                      maya_sdk — standard library only, no dependencies
│   └── java/                        not built; the contract it must honour, written down
├── content/                         help and tutorials, rendered at request time
├── examples/warrants/               thirteen worked warrants across the model estate
├── docs/                            18 specification documents + ADRs
├── tools/deck/                      the decks, generated from source rather than edited
└── tests/                           the law suite and the discipline walkers
```

### The discipline walkers

Several tests do not test a feature. They walk the source and hold a rule that would otherwise rot:

| | |
|---|---|
| `test_logging_discipline` | No exception is ignored. Every `except` logs; none is bare; none is only `pass` |
| `test_refusal_discipline` | Every coded refusal maps to a status that says who must act, and no code is mapped twice |
| `test_schema_discipline` | One typed declaration renders identically to both dialects; the checked-in `.sql` is not stale; a truth value is a `Boolean` and a count is not |
| `test_size_discipline` | No source file over 1,500 lines |
| `test_documentation_counts` | Every number claimed in prose is recounted from the code |
| `test_deck_geometry` | No slide has overlapping or escaping content |
| `test_ui_tables` | Every HTML table has a header, and pagination where it needs one |
| `test_laws` | The foundational laws, run as tests |

---

## Licence

**Proprietary and confidential.** Copyright © 2026 Ashutosh Sinha. All rights reserved.

No part of this repository may be copied, modified, distributed or used without prior written
permission. See [LICENCE](LICENSE) and [NOTICE](NOTICE).

The research paper, its article and the research deck are product-neutral and may be shared for
academic discussion, with attribution.

---

## Contributing

This is a single-author research and engineering project. Issues and discussion are welcome;
pull requests are not accepted at this time.

If you are reading this because you run a model estate and something here describes a problem you
have — that is the most useful feedback there is.
