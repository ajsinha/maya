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
| **Asymmetric warrant signatures** | HMAC-SHA256 ships; RS256 verification already exists in `core/authz/jws.py` for OIDC, so the primitive is here | Verifying a warrant requires holding the key that could **mint** one. That is the wrong shape for a contract handed to engines you do not control, and it is the single largest gap in the execution story |
| **A third-party time source for the anchors** | Anchoring is built: `WORMReader`/`WORMWriter` in `core/ports.py`, a filesystem implementation writing under `./data/worm`, and `verify_against_anchors` comparing the chain against heads held outside the database. What is not built is an RFC-3161 timestamping authority, which is a third party rather than code | The anchors say *this head existed before that one*; they do not say *at this time, attested by somebody who is not us*. A bank arguing with a supervisor about **when** wants the second. Finding **C-4**'s third disposition is now half-closed |
| **Three foundational laws** | `L-6`, `L-11`, `L-13` — each named in [00 §12](00-mathematical-foundations.md#12-the-laws-maya-enforces) with the reason. `L-14` and `L-17` were on this list and now run | The strongest claim the design makes is that the laws are the acceptance criteria. Eighteen of twenty-one run; a law stated and not executed prevented nothing |
| **`entry_points` discovery for fibres** | The fibration itself is built — `core/fibres/`, nine fibres over the derived trainability class, a totality gate at start-up (`L-15`) | A bank's own fibre ships inside this repository rather than as its own package. The structure and the gate exist; third-party packaging does not |

### 2.2 Reach — these change what MAYA can *cover*

| | Why it is not built | What it costs while absent |
|---|---|---|
| **An online feature store** | The Delta namespace is the serving contract; reading it at request latency is deliberately the engine's problem — and §7 says MAYA will not sit on the serving path, so building one here would contradict this document | Nothing, for `L-17`. That row said the law was inert without a store, and the law was blocked on the wrong thing: the engine knows which namespaces it read, so it **attests** and MAYA compares (`core/features/serving.py`). Training–serving skew is now detectable without the platform being on the request path. What a store would still buy is *observation* rather than attestation — MAYA seeing for itself rather than being told — and that is a different, smaller claim than the one this row used to make |
| **Connectors** — MLflow, Unity Catalog, git | Each is a real integration against an external API | Bulk import exists for a spreadsheet; the models already sitting in an ML platform have to be entered by hand |
| **Discovery and an EUC scanner** | Nothing sweeps for unregistered models | The inventory is what somebody registered. An inventory campaign finds what people declare; discovery finds what they did not |
| **Composite warrants and the interaction premium** | Typed composition (`L-21`) now gives `L-14` something to quantify over; the aggregate `ρ` is not built | The question supervisors actually ask — *how much riskier is the network than its parts* — has a definition and no computation |
| **Spark-scale monitor evaluation** | Monitors evaluate in-process | Fine at hundreds of models; not at an estate-wide nightly sweep over billions of rows |
| **An examiner portal** | The export pack *is* the artefact — self-contained, digested, gaps named. What is missing is a place to hand it to somebody | Packs are produced and then emailed, which is the workflow they were meant to replace |
| **PDF, and any rendering past markdown** | The compiler emits markdown, rendered through the same pipeline as the help system | A committee paper is copied into a word processor, at which point it stops being compiled and starts being edited |
| **A Java SDK** | The contract it must honour is written down in `sdk/java/README.md`; the implementation is not | A JVM shop writes its own client, and writes it against HTTP rather than against the contract |
| **Rule-set import from what a bank already has** | A decision table in a spreadsheet, a DMN file, a stored procedure — each is a parser, and each is a parser that can be subtly wrong | The rules are typed in, or posted as a document. Migrating an existing rulebook is manual work, and it is the work that decides whether T8 coverage is a demonstration or a programme |

### 2.3 Deployment — these are somebody's operational work, not code

Row-level security, IaC, multi-region topology, and the three spikes that were
never run (a point-in-time join at a billion rows; warrant resolution p99 under
load; sandbox escape testing). The first two are configuration MAYA exposes and
does not perform; the spikes are measurements, and their absence is why every
NFR figure in [03 §7](03-requirements.md) is a target rather than a result.

---

## 3. The order, and the argument for it

**First, the two that change what can be claimed.**

**Asymmetric signatures** before anything else. Everything downstream of the
warrant — every engine integration, every conversation with a team that runs
models MAYA does not — is weaker while verification requires the minting key.
The primitive already exists in the repository for OIDC; this is mostly a key
management decision, and it is the kind of decision that gets harder after the
first external engine is integrated rather than before.

**Chain anchoring** second, and it is second only because it depends on
infrastructure somebody has to provide. Tamper evidence resting on
self-consistency is the claim most likely to be challenged by an examiner who
understands what a hash chain does and does not prove.

**Then the law gap, because it is cheap and it is the platform's own standard.**
`L-14` needs composite warrants, so one of the four is blocked on an item below
rather than on effort. `L-17` was listed here too, blocked on the online store,
and that was a mistake worth recording: the store is a component §7 says MAYA
will not own, so the law had been made to depend on something the architecture
forbids. The engine attests instead. `L-6`, `L-11` and `L-13`
are honest refusals: building a document `put` to satisfy the lens laws would be
building the wrong thing, and the table says so rather than leaving a gap that
looks like neglect.

`L-15` was the third of those, and closing it is worth recording because the
blocker was not effort. It was **the base**: the law says the fibration is
indexed by the model class, and `model_class` is a free-text column, so totality
over it is either a closed vocabulary — which contradicts *"adding a class adds a
fibre, no migration"* — or a gate defeated by typing an unregistered word. The
base is the derived trainability class, and every fibre had already been written
out in `docs/02 §5`.

**Then reach, in the order a bank actually feels the absence.**

1. **Connectors**, because an inventory somebody has to type is an inventory
   that stays incomplete — and completeness is the precondition for everything
   else. This is the *earn the inventory* principle below, and it is the one
   most often skipped.
2. **The examiner portal and PDF**, together: they are the same user, and half
   the artefact already exists.
3. **Composite warrants and the interaction premium**, which turn a theorem into
   a number.
4. **Discovery**, last of the reach items and deliberately so — it should run
   against a register that is already good, or it produces a queue nobody
   triages.

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
| **The inventory never reaches completeness** | Discovery is not built, so the register holds what people registered | Baseline import with **compliance debt kept apart from breach** — an imported model is visibly incomplete rather than quietly counted as governed |
| **The warrant plane becomes a bank-wide SPOF** | It is on the authorisation path, by design | Governance is *not* on the serving path: if MAYA is down, authorised scoring continues and only new issuance stops. The grace window is the second half of that |
| **Machine assistance ships ahead of its oracle** | The pressure to ship an impressive ungated demo is constant | Structural, not procedural: Tier C is **unrepresentable** in the schema. A capability without an oracle or a grounding check cannot be registered |
| **Assistants drift toward deciding** | Policy erodes; this one has to be architectural | No AI principal holds a credential permitting a governance transition. **Held by construction and not by any check** — the test that would enforce it is named in [13](13-ai-in-the-platform.md) and not written |
| **Scope creep into enterprise GRC** | The boundary is easy to state and easy to erode | Explicit: MAYA owns model risk; issues sync to the GRC platform rather than living in two places |
| **Over-engineering the theory** | An ever-present temptation in a design like this one | Every abstraction ships with a law and a test or it is cut. Eighteen of twenty-one run, and the three that do not are named |

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
