# 10 — What is left, and the order it should be done in

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Annex to** [03 — Requirements](03-requirements.md) and [04 — Architecture](04-architecture.md).

---

## 1. What this document is

A roadmap written before the work reads, a year later, as a list of things
somebody was going to do. This one is written **from where the build actually
is**.

It has been rewritten three times, and the rewrites are the more useful record
than any of the versions. It began as a list of eleven things to build. It
became a list of things built and things left. It is now mostly a list of
**decisions** — because as the build finished, item after item turned out not to
be work outstanding but a position the platform had taken without writing it
down.

So this document now says four things:

1. **What is genuinely left**, which is short.
2. **What will not be built, and what closing it would cost** — the longer list,
   and the one a reader is most likely to misread.
3. **What the ordering taught**, including an item that was wrong about its own
   size and another wrong about its own shape.
4. **The decisions that constrain the rest** — build versus buy, and what MAYA
   deliberately does not own.

The authoritative record of what *exists* is
[**12 §0, Build status**](12-implementation-plan.md#0-build-status). This
document does not duplicate it: two records of what is built are two records that
can disagree, which is the same reason there is no separate audit log.

A schedule is deliberately absent. Dates in a document nobody re-dates are the
fastest thing here to go stale, and the ordering argument is the part that
survives.

---

## 2. What is genuinely left

Four things, and only one of them is code this repository would contain.

### 2.1 A sweep somebody actually runs

The receiving half is built and the contract a scanner must meet is published
(`core/discovery/contract.py`). A **reference scanner** ships in
`tools/scanner/` — it runs outside the platform, imports nothing from `core/`,
and needs nothing installed, so it can be dropped onto a file server inside a
bank's perimeter and run.

What is missing is somebody running it, against a real estate, with the
credentials that requires. That is deliberately last in the *earn the inventory*
order below: a sweep run against a register that is not yet good produces a queue
nobody triages, which is how every discovery programme that fails, fails.

### 2.2 Three foundational laws

`L-6`, `L-11`, `L-13`, each named in
[00 §12](00-mathematical-foundations.md#12-the-laws-maya-enforces) with its
reason. Eighteen of twenty-one run.

These are **honest refusals** rather than pending work. Building a document `put`
to satisfy the lens laws would be building the wrong thing — the compiler
regenerates whole documents rather than editing them, and a `put` would exist
only to make a law pass.

### 2.3 The operating

Multi-region topology, backup and restore, TLS termination, a secret manager, and
an annual penetration test. The **artefacts** are built ([19](19-deploying-maya.md));
these are the running of them, and they belong to whoever operates the platform.

### 2.4 The measurements nobody has taken

Three of the NFR table's targets are now results (`tools/spikes/`, and
[19 §8](19-deploying-maya.md)). The rest are still targets: throughput, the
50,000-model scale figures, restore time, and anything about a multi-node
deployment.

> A number this platform has never observed is a number it should not print as
> though it had.

---

## 3. What will not be built

This is the longer list, and the one most likely to be misread. Every row is a
decision, not a gap. **A gap closes with effort. A refusal closes only by making
something else untrue**, and the third column says which thing.

### 3.1 Because the theorem forbids it

| | Closing it would require |
|---|---|
| **The interaction premium** as a magnitude | contradicting `L-14`. A network that *copies* a dependency and one that *duplicates* it produce identical component ratings, so any single figure over those ratings is blind to precisely what it would exist to find. What composes is the **order** — the worst tier at stake — and that is what ships |

### 3.2 Because the architecture forbids it

| | Closing it would require |
|---|---|
| **An online feature store** | MAYA sitting on the serving path, which §8 forbids. `L-17` was thought to be blocked on this and was blocked on the wrong thing: the engine attests which namespaces it read and MAYA compares. A store would buy *observation* rather than attestation — a smaller claim than the row used to make |
| **Enforcing a cost budget** | the same. MAYA cannot decline a model's next invocation, so a budget claiming to enforce would claim a control it has no way to exercise. A breach raises a finding with an owner |
| **Spark inside MAYA** | the governance platform owning a cluster and sitting on the compute path for every model in the bank. Monitoring at estate scale moves the **scan** instead and keeps the arithmetic, which is why that result can be replayed |

### 3.3 Because it would weaken something

| | Closing it would require |
|---|---|
| **An examiner portal** | issuing a credential to somebody outside the firm and owning its lifecycle. Handing a pack over *is* built — a time-boxed link to a content digest, revocable, recording every read including the refused ones — and `is_a_portal: false` is published rather than left ambiguous |
| **PDF and `.docx` rendering** | flattening away the citations that make a compiled document traceable. What leaves is typesetting source with them intact, and coverage gaps written *into* the output rather than dropped |
| **Fetching a tiering fact** | MAYA holding read credentials to the general ledger. A fact is attested, with a reference somebody can check, and the share that rests on somebody's word is reported |
| **Translating a stored procedure** | writing a compiler. SQL has control flow, mutation and side effects, and a wrong compiler produces a rule set that loads, validates and decides differently from the procedure the bank has been running — undetectable by reading its output |
| **Crawling the bank's drives** | the broadest standing read access anybody holds, granted to the system whose whole argument is that it holds none |

### 3.4 Because the requirement was wrong

| | What happened |
|---|---|
| **Asymmetric warrant signatures** | Led this document for two revisions. The objection was about **blast radius**; asymmetry answers a different question — proving authorship to a party that is not MAYA — and nobody had asked it. Per-audience key derivation ([ADR-012](adr/ADR-012-per-audience-warrant-keys.md)) gives the containment at none of the key-management cost. **A roadmap item can be wrong about its own size, and this one was also wrong about its own shape** |

---

## 4. What the ordering taught

The ordering argument is the part of a roadmap that survives, and this one was
wrong twice in instructive ways.

**It led with the wrong item for two revisions.** *Asymmetric signatures before
anything else* was argued from a real defect and proposed a fix for a different
problem. What made it visible was somebody asking why it was first, not any
amount of re-reading.

**It made a law depend on something the architecture forbids.** `L-17` sat under
*blocked on the online feature store* while §8 said MAYA would never own one. The
law was not blocked; the dependency was invented.

**And `L-15`'s blocker was not effort — it was the base.** The law says the
fibration is indexed by the model class, and `model_class` is a free-text column,
so totality over it is either a closed vocabulary (contradicting *adding a class
adds a fibre, no migration*) or a gate defeated by a typo. The base is the
**derived trainability class**, and every fibre had already been written out in
`docs/02 §5`.

Three failures, one shape: **the item was not what it said it was.** That is what
a roadmap is worst at showing you, because a list of names reads as a list of
understood things.

---

## 5. Three principles that shaped the order

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

## 6. Risks that are still live

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
| **A refusal is read as a backlog item** | New, and it arrived with the build finishing. §3 is longer than §2, and a list of absences reads as work outstanding to almost everybody | The document is now organised by *why* rather than by *what*, and every refusal names what closing it would cost. Three of the four in §3.3 would make the platform worse |
| **The documents drift from the code** | Permanent, and the most-read documents drift furthest because nobody re-reads what they think they know | `tests/test_documentation_counts.py` recounts every claimed number from the code. It has caught something on nearly every milestone — including, recently, the README on three separate numbers, because a pattern narrow enough to avoid false alarms missed the sentence somebody actually wrote |

---

## 7. Build or buy, revisited

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

## 8. What MAYA deliberately will not own

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
