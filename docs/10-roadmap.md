# 10 — What is left, and the order it should be done in

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Annex to** [03 — Requirements](03-requirements.md) and [04 — Architecture](04-architecture.md).

---

## 1. What this document is

A roadmap written before the work reads, a year later, as a list of things
somebody was going to do. This one is written **from where the build actually
is**, so it says three things and nothing else:

1. **What remains** — named, with the reason each is not built.
2. **The order it should be done in**, and the argument for that order.
3. **The decisions already made** that constrain it — build versus buy, and what
   MAYA deliberately does not own.

The authoritative record of what *exists* is
[**12 §0, Build status**](12-implementation-plan.md#0-build-status). This
document does not duplicate it, because two records of what is built are two
records that can disagree — the same reason there is no separate audit log.

A schedule is deliberately absent. Dates in a document nobody re-dates are the
fastest thing here to go stale, and the ordering argument is the part that
survives.

---

## 2. What remains

Grouped by what stops each one, because that is what decides when it can be
done.

### 2.1 Structural — these change what MAYA can *claim*

| | Why it is not built | What it costs while absent |
|---|---|---|
| ~~**Asymmetric warrant signatures**~~ **Dropped as a requirement; the problem it named is solved** | The row led this table for two revisions on the argument that verifying a warrant requires holding a key that could **mint** one. That was true and the proposed fix was wrong for it. The defect has two halves that were being treated as one: *who can forge*, which is operational, and *who can prove authorship to a third party*, which needs public-key cryptography and which nobody had asked for | **Closed by derivation, not by asymmetry.** `core/execution/signing.py` derives each audience's key from the root and the audience's own principal — `HMAC(root, "maya/warrant/v<gen>/" ‖ audience)` — so a compromised engine forges warrants for **itself and nobody else**, and the derivation is one-way, so holding one key yields no other. The audience is read from the document being verified, so redirecting a warrant to another principal breaks its signature rather than needing a separate check somebody remembered. Rotation is a generation counter in the key id. `GET /warrant-signing` publishes what a signature proves and, in the same object, that it does **not** prove authorship to a third party: a verifier holds the key it verifies with, so a descriptor is evidence to the bank and not to anybody outside it. If a firm ever does need non-repudiation to an external party, that is a new requirement with its own argument, and it is not this one |
| ~~**A third-party time source for the anchors**~~ **Built** | `core/evidence/timestamps.py`. It takes an RFC 3161 token over an anchored head, and the design is in what it declines: MAYA is not the authority **and does not verify**, because checking a token means holding a certificate chain and choosing which roots to trust — a decision the firm's security function has already made. What remains is not code: an authority has to be *chosen and wired*, and the platform reports itself as **arguing from its own clock** until one is | Closed, with the bound stated in the interface rather than in a footnote. A token bounds a head **from above only** — it proves this hash existed no later than that time, which is what stops a chain being rewritten and dated before the fact. It says nothing about how early the head existed, nothing about deletion, and nothing at all about the period before the first token. `unverified` is a third state that never collapses into either neighbour. Finding **C-4**'s third disposition is now closed |
| **Three foundational laws** | `L-6`, `L-11`, `L-13` — each named in [00 §12](00-mathematical-foundations.md#12-the-laws-maya-enforces) with the reason. `L-14` and `L-17` were on this list and now run | The strongest claim the design makes is that the laws are the acceptance criteria. Eighteen of twenty-one run; a law stated and not executed prevented nothing |
| ~~**`entry_points` discovery for fibres**~~ **Built** | `core/plugins/discovery.py` reads `entry_points(group="maya.extensions")` across every open axis, fibres included | Closed, and the seam is the control rather than the convenience: discovery **imports nothing**, so a package is *seen* from its metadata and *enabled* only when configuration names it. A control that switched itself on when somebody bumped a dependency is a control nobody turned on. `not_installed` and `not_enabled` are separate refusals — the second is the safe state; the first means somebody believes a control is running. A third-party fibre may **add** obligations and never remove one, checked at load |

### 2.2 Reach — these change what MAYA can *cover*

| | Why it is not built | What it costs while absent |
|---|---|---|
| **An online feature store** | The Delta namespace is the serving contract; reading it at request latency is deliberately the engine's problem — and §7 says MAYA will not sit on the serving path, so building one here would contradict this document | Nothing, for `L-17`. That row said the law was inert without a store, and the law was blocked on the wrong thing: the engine knows which namespaces it read, so it **attests** and MAYA compares (`core/features/serving.py`). Training–serving skew is now detectable without the platform being on the request path. What a store would still buy is *observation* rather than attestation — MAYA seeing for itself rather than being told — and that is a different, smaller claim than the one this row used to make |
| ~~**Connectors** — MLflow, Unity Catalog, git, SageMaker, Vertex, SAS, the CMDB~~ **Built, in one direction** | `core/discovery/connectors.py` parses an **export document** each of those systems already produces. It deliberately does not call an API and holds no credential: a register with read access to every ML platform in the bank is the broadest standing access anybody holds, granted to the system whose whole argument is that it holds none | Mostly closed. What a connector produces is **candidates for triage, never registrations** — five governance facts are in no ML platform anywhere (ownership in the bank's sense, the decision it is used for, the legal entity, materiality, and whether the thing is a model at all), and a register that inferred them would have manufactured exactly what it exists to hold. All seven sources named in `INT-001`, `INT-002` and the discovery rows now have one — and **SAS and the CMDB are the two that matter most**, for opposite reasons: SAS reaches the oldest credit, capital and ALM models, which were never in an ML platform and are the first thing a supervisor asks about; the CMDB holds the *business service* a thing supports, which is the nearest any system in the bank comes to materiality. What is still missing is the **push governance status back** direction, and it needs care rather than effort — a register that writes "approved" into another system's UI has told somebody something the approval record does not say. Each connector also publishes `do_not_read_as`: fields that carry a governance-sounding name and mean something else. SageMaker's `Approved` means a pipeline step passed; MLflow's `Production` is a deployment stage; a Unity Catalog owner is a read grant. **An absent governance fact is the easy case** — somebody notices — and a present one with the right word on it is not |
| **An EUC scanner** — the sweeping half | MAYA does not crawl the bank's drives and should not: a discovery agent needs credentials to every repository, notebook server, shared drive and gateway in the institution. The **receiving** half is built (`core/discovery/`), and what a scanner has to send is now **published as a contract** — `core/discovery/contract.py` names the required fields with the reason for each, caps confidence strictly below certainty, and refuses a sweep that misses it *whole* rather than keeping the good rows, because a partial ingest grades something other than the scanner | The inventory is still what somebody registered plus what somebody else's scanner delivered. Precision is computed from the triage outcomes and **recall is stated as not computable** — nothing here knows what a scanner did not look at, which is why the contract asks the scanner to declare its scope |
| ~~**Composite warrants**~~ **Built**; the interaction premium is **refused** | Composite resolution ships — a chain of models resolves as one unit or is refused as one. The aggregate `ρ` is not built and is not going to be: `L-14` says the copy map is the obstruction, so a network that *copies* a dependency and one that *duplicates* it produce identical component ratings, and any single figure computed from those ratings is blind to precisely what it would exist to find | What composes is the **order** — the worst tier at stake — and not a magnitude. That is `L-14` arriving as an interface rather than as a caveat, and it is a better answer than a number a committee cannot decompose |
| **Spark-scale monitor evaluation** | Monitors evaluate in-process | Fine at hundreds of models; not at an estate-wide nightly sweep over billions of rows |
| **An examiner portal** — and it stays unbuilt on purpose | The **handing-over** half is built: `core/export/sharing.py` issues a time-boxed link to a **content digest**, never a path, revocable, optionally read-capped, recording **every read including the refused ones**. A portal is the other thing — it authenticates a third party *into* the register, and whatever that session can reach they can reach | Closed for the workflow that mattered; open, deliberately, for the one that did not. `is_a_portal` and `establishes_identity` are published as false rather than left ambiguous, because letting a time-boxed link be mistaken for scoped interactive access is the mistake that costs something here |
| **PDF and `.docx`** — refused by name, with the reason | `core/docs/rendering.py` emits **typesetting source** — LaTeX or markdown — with the citations intact, and refuses PDF, `.docx` and standalone HTML on `/api/v1/document-rendering/formats` with what each would cost. Rendering needs a TeX distribution or a browser engine, which is a large attack surface for a formatting need, and a house template, which is a firm's document standard and not a register's decision | A committee paper is still typeset elsewhere — but it leaves here as source that **names the evidence each section rested on**, and coverage gaps are written *into* the output under a heading of their own. A rendering that flattened the citations away would produce a document whose claims can no longer be traced, which is the state every hand-written model document is already in; one that dropped the gaps would produce something that *looks* complete |
| **A Java SDK** | The contract it must honour is written down in `sdk/java/README.md`; the implementation is not | A JVM shop writes its own client, and writes it against HTTP rather than against the contract |
| ~~**Rule-set import from what a bank already has**~~ **Built for two of three; the third is refused** | `core/rules/importing.py` reads a CSV decision table and a DMN 1.3 decision table. A **stored procedure** is not translated and will not be: SQL is a general language with control flow, mutation and side effects, so a translator would be a compiler, and a wrong compiler produces a rule set that loads, validates and decides differently from the procedure it claims to be | Mostly closed, and the parser's honesty is the design rather than its coverage. A misread threshold does not *fail* — it produces a rule set nobody can tell is wrong by looking at it. So a cell that is a human judgement is **reported rather than guessed**; a document with any untranslated row is refused **whole**, because the rows a parser finds hard are the judgement calls and those are what a rulebook exists for; a hit policy that cannot map is refused **by name** with what first-match would silently become; and the catch-all is **derived** from first-match semantics rather than inferred from the last row's position. Nothing is imported — a candidate goes through the same check, trial and publish path a hand-written rule set takes, second-person approval included |

### 2.3 Deployment — these are somebody's operational work, not code

Row-level security, IaC, multi-region topology, and the three spikes that were
never run (a point-in-time join at a billion rows; warrant resolution p99 under
load; sandbox escape testing). The first two are configuration MAYA exposes and
does not perform; the spikes are measurements, and their absence is why every
NFR figure in [03 §7](03-requirements.md) is a target rather than a result.

---

## 3. The order, and the argument for it

**This section has been rewritten twice, and the second rewrite is the more
useful part of it.** For two revisions the order began *asymmetric signatures
before anything else*, on the argument that everything downstream of the warrant
is weaker while verification requires the minting key. That ordering was
challenged on 2026-09-10 and did not survive, and then the requirement itself
did not survive either — because looking at it properly showed it was the wrong
fix for a real defect rather than the right fix for an imagined one.

The defect was real: one estate-wide HMAC secret means any engine that can
*verify* a warrant can *mint* one, for any model and any principal. But the fix
it demanded was containment, not asymmetry, and containment is a **key
derivation**: sign each audience's warrants with a key derived from the root and
that audience's own principal. A compromised engine then forges warrants for
itself and for nobody else, at none of the custody, rotation and revocation cost
a public-key hierarchy brings. That is built.

What asymmetry uniquely buys is *non-repudiation to a third party* — showing
somebody who is not the bank that only MAYA could have issued a descriptor — and
nobody had asked for it. The platform now says so in the interface rather than
carrying it as debt. A roadmap item can be wrong about its own size; this one
was also wrong about its own shape.

**Everything that was ahead of it is now built.** Chain timestamping,
`entry_points` discovery, the connectors, the share, the scanner contract and
the document rendering closed in one wave in September 2026; composite warrants
closed earlier and out of order. What follows is what is genuinely left.

**First, the law gap, because it is the platform's own standard.**

`L-14` was blocked on composite warrants and now runs. `L-17` was listed here
too, blocked on the online store, and that was a mistake worth recording: the
store is a component §7 says MAYA will not own, so the law had been made to
depend on something the architecture forbids. The engine attests instead.
`L-6`, `L-11` and `L-13` are honest refusals: building a document `put` to
satisfy the lens laws would be building the wrong thing, and the table says so
rather than leaving a gap that looks like neglect.

`L-15` was the third of those, and closing it is worth recording because the
blocker was not effort. It was **the base**: the law says the fibration is
indexed by the model class, and `model_class` is a free-text column, so totality
over it is either a closed vocabulary — which contradicts *"adding a class adds a
fibre, no migration"* — or a gate defeated by typing an unregistered word. The
base is the derived trainability class, and every fibre had already been written
out in `docs/02 §5`.

**Then reach, in the order a bank actually feels the absence.**

1. **An EUC scanner somebody actually runs**, against the published contract.
   The receiving half and the contract are built; what is missing is a sweep,
   and it is deliberately last in the *earn the inventory* order below — a sweep
   run against a register that is not yet good produces a queue nobody triages,
   which is how every discovery programme that fails fails.
2. **A Java SDK**, because a JVM shop currently writes its own client against
   HTTP rather than against the contract.
3. **Spark-scale monitor evaluation**, which is a scale problem and not a
   coverage one — it changes nothing about what MAYA can claim, only about how
   many models it can claim it for in a night.

**Deployment work runs alongside all of it** and is not sequenced here, because
it belongs to whoever operates the platform rather than to whoever builds it.

---

## 4. Three principles that shaped the order

These were written before the build and have held, which is the only reason they
are still here.

**Earn the inventory before automating it.** Nothing else works if the inventory
is incomplete, so the first job is *getting every model in* — including the
awkward ones: vendor, EUC, quant. The baseline importer exists for exactly this,
and it deliberately admits models as `baselined` rather than `draft`, because the
register must never imply that historical evidence was asserted when it was not.

**Ship the hard architecture first and the pretty features later.** The evidence
graph, the fibration and the warrant protocol are load-bearing; retrofitting
immutability or extensibility is not possible, and adding a dashboard is trivial.
This is why the board pack arrived after the register rather than before it, and
why it is *derived* rather than entered.

**Make the compliant path the fast path from day one.** If the SDK lands after
the interface, developers will have built workarounds first and the next two
years go on undoing them. The SDK exists, is dependency-free, and decides
nothing — which is the other half of the same principle: a client that made
governance decisions locally would be a second implementation able to disagree
with the first.

---

## 5. Risks that are still live

Dropped the ones that have been resolved or overtaken. What remains:

| Risk | Why it is still live | The mitigation that is actually in place |
|---|---|---|
| **Developers route around MAYA** | The permanent risk of any control plane | The SDK, and the refusals carrying remediation. Neither is sufficient; measuring it is not built |
| **The inventory never reaches completeness** | The register holds what people registered, plus what a connector or a scanner delivered — and nobody in this firm has yet run a sweep | Baseline import with **compliance debt kept apart from breach** — an imported model is visibly incomplete rather than quietly counted as governed. Connectors and the scanner contract now give the two other routes in, and both produce **candidates for triage rather than registrations**, so nothing arrives counted as governed that nobody looked at |
| **The warrant plane becomes a bank-wide SPOF** | It is on the authorisation path, by design | Governance is *not* on the serving path: if MAYA is down, authorised scoring continues and only new issuance stops. The grace window is the second half of that |
| **Machine assistance ships ahead of its oracle** | The pressure to ship an impressive ungated demo is constant | Structural, not procedural: Tier C is **unrepresentable** in the schema. A capability without an oracle or a grounding check cannot be registered |
| **Assistants drift toward deciding** | Policy erodes; this one has to be architectural | No AI principal holds a credential permitting a governance transition. **Held by construction and not by any check** — the test that would enforce it is named in [13](13-ai-in-the-platform.md) and not written |
| **Scope creep into enterprise GRC** | The boundary is easy to state and easy to erode | Explicit: MAYA owns model risk; issues sync to the GRC platform rather than living in two places |
| **Over-engineering the theory** | An ever-present temptation in a design like this one | Every abstraction ships with a law and a test or it is cut. Eighteen of twenty-one run, and the three that do not are named as refusals rather than as gaps |

---

## 6. Build or buy, revisited

The decision was made before the build. It is worth restating now that there is
something to compare against.

| Option | Assessment |
|---|---|
| **Buy a GRC/MRM platform** — OpenPages, SAS MRM, ValidMind, ModelOp | Workflow and documentation quickly. No artifact binding, no feature management, no warrants, and no coverage of the quant or EUC estate. Would need a second and third system alongside it |
| **Buy an MLOps platform** — Databricks, Domino, DataRobot | Artifacts, lineage and monitoring for the ML subset. No MRM domain objects, no multi-regime scoping, no overlays, no findings — and the ML subset is a minority of the estate |
| **Buy both and integrate** | The status quo at most large banks. Produces two inventories that disagree, and an integration layer nobody owns. The disagreement is itself an audit finding |
| **Build** | Higher initial cost. Delivers what [01 §6](01-industry-research.md) says the market does not, and the extension architecture means the bank is not exposed to a vendor's roadmap for the next regulator or the next model paradigm |

**Still build, and still integrate rather than replace.** MLflow and Unity
Catalog stay as a training substrate; the enterprise GRC platform stays as the
enterprise issue register; ML observability tools stay as optional metric
producers. MAYA is the system of record that binds them.

What has changed since the decision was made is that one of its premises can now
be checked rather than argued: **no feature store has an algebra, the semantic
layers have an algebra and no time, and MAYA has both** — the schema lattice, the
point-in-time saturation law and typed composition are each asserted by a test
rather than by this sentence.

---

## 7. What MAYA deliberately will not own

A roadmap that does not say where it stops will be asked to go there.

| | Why not |
|---|---|
| **Running models** | Governance on the serving path makes it the bank's single point of failure. MAYA authorises; an engine acts |
| **Training models** | The estimator fits `ols` and `garch11` so the register can demonstrate the whole path; anything else is delivered back under a warrant |
| **Authoring models** — with one stated exception | An authoring surface would let MAYA mint an artifact that has never been trained or validated and is **indistinguishable in the register** from one that was. That is the whole objection, and it decides where the exception lies. A **rule set** has no training run to be indistinguishable from: authorship *is* its provenance, which is what `declared` means. So `core/rules/` edits a parameter set MAYA already held — versioned, digested, second-person approved — and publishing is `parameters.record` with a validated document, no new authority, `self_approval` still refused. There is deliberately **no ONNX or PMML editor**, and there will not be one |
| **Enterprise issue management** | Findings that block a model live here; the enterprise register is where they are reported. Two homes for one issue is the failure this avoids |
| **Feature engineering** | The expression language is small on purpose. Anything richer is `external`, and says so |
| **Being a model store of last resort** | The artifact store has an 8 GiB ceiling. Somebody should have to think before putting a foundation-model checkpoint in a governance platform |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
