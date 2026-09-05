# 01 — The estate, the supervisors, and what the tools do

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

> **What this document is.** The evidence base the requirements rest on: what a large bank's model
> estate actually contains, what the supervisors now oblige, what the products on the market do and
> where each stops, and the one position MAYA can defend with a test rather than a claim.
>
> **Research date:** September 2026. Every external figure carries its source in §7. Where a number
> could not be sourced it has been removed rather than rounded.

---

## The argument

Nothing in this market is bad at what it was built for. GRC platforms run a governance process well.
MLOps platforms track artefacts well. Feature stores serve features well. Semantic layers compose
metrics better than any of them. Each was built for a buyer, and each serves that buyer.

A bank's model estate has **five properties that cut across all four categories**, and since April 2026
it has **two supervisors pulling in opposite directions**. The categories do not fail at their own
jobs; they fail at the intersection, and the intersection is where a model estate lives.

This document is organised around that. §1 is the estate. §2 is the divergence. §3 is what each
category does and where it stops, stated so that somebody who sells one of these products would
recognise the description. §4 is a live threat none of them addresses. §5 is the prior art MAYA stands
on and should cite rather than quietly reuse. §6 is the gap, what MAYA now has against it, and what it
still does not.

---

## 1. The estate as it is

### 1.1 Scale, with the ranges the surveys actually report

| Fact | Figure | Source |
|---|---|---|
| Mean inventory across surveyed banks | ≈ **175 models**, heavily right-skewed | Moody's 2026 MRM survey, 79 MRM leaders |
| Large-bank concentration | ~**20% of commercial banks** and **most investment banks** report 1,000+ | *ibid.* |
| Growth | **every** surveyed bank reported growth; >50% growth in two years reported by 9% (retail), 16% (commercial), 17% (investment) | *ibid.* |
| Highest concentration of high-risk models | **CECL/IFRS 9, ALM, BSA/AML** | *ibid.*; RMA survey |
| End-user computing | counted separately, and in the thousands to tens of thousands where anybody has counted | EUC scanning vendors; RiskSpan |

Two things follow, and they are engineering facts rather than observations.

**The inventory is an operational database, not a register somebody maintains.** At a thousand models
with named owners, dated obligations and per-model evidence, the working set is too large for a
spreadsheet and too interlinked for a ticketing system. It needs search, paging, bulk operations and an
API, or it silently becomes a subset of itself.

**Discovery matters more than attestation.** The pain point banks report is not that the register is
wrong about the models in it; it is the models that are not in it. Periodic owner attestation finds the
first class of error and cannot find the second.

### 1.2 Five properties, and what each breaks

Each of these is why one category of tool cannot hold the estate. They are stated as failures rather
than as principles because the failure is what a reader can check.

---

**1. Most of a bank's models were never trained.**

A discount factor, a swaption price, an SA-CCR exposure, an LCR calculator: these come from theory.
There is no training set, no drift in the usual sense, and no refit. A yield curve is re-solved every
morning against market quotes, which is a different act with different evidence. A country-risk
scorecard is set by a committee. A vendor score is somebody else's arithmetic under licence.

*What it breaks.* The question every product asks first — **is it AI?** — separates nothing useful. It
puts a Black–Scholes pricer and a linear regression in different buckets while putting a regression and
a large language model in the same one. Downstream, a validation template acquires fields that make no
sense for half the estate, and users write "N/A" until they stop reading the fields at all.

*The question that does sort it* is **how is the parameter object inhabited?** — from theory, from a
solver, from an estimator, from a training run, from a configuration, from a room full of people, or
from inside a vendor binary. That question is answerable for every model in the estate, its answer is a
property of the kernel rather than a self-report, and the classification T0–T8 falls out of it. The
classes are defined and worked in [02 — Model Taxonomy](02-model-taxonomy.md); the algebra they come
from is [00 §3](00-mathematical-foundations.md).

---

**2. The estate is a directed graph, and the most important nodes are the least inventoried.**

A single yield-curve model is a feeder to hundreds of valuation models, which feed VaR, XVA, FRTB, RWA
and capital planning. Market-data construction models are simultaneously the most systemically
important family and the family most often absent from an inventory, because nobody thinks of a curve
build as a model.

*What it breaks.* A change-impact assessment written by hand is a guess. SR 26-2's requirement to
assess risk "in aggregate — reliance on common assumptions, data, or methodologies" cannot be met by
reading a list. And a dependency edge that is *recorded* but never *checked* is worse than none: the
blast radius computed over it looks authoritative and is not.

---

**3. Reproducibility breaks in the data, not in the model.**

Training/serving skew and training sets that are not point-in-time correct are the dominant silent
failure mode, and they are silent by construction: a leaked column looks unremarkable afterwards. A
z-score fitted over a whole history encodes what the mean *turned out* to be. A restated figure that
reaches a row labelled before the restatement arrived produces a model that validates well and
performs badly.

*What it breaks.* Almost every feature store offers point-in-time joins. Very few **refuse** an
assembly that cannot be shown correct, and none of them refuses a *normalisation* fitted over the
future. The correct condition needs two clocks — when a thing happened, and when the platform came to
know it — and a read defined against both.

---

**4. Scope is plural, and since April 2026 it is contradictory.**

The same model is out of scope for the US guidance and in scope for the UK one. See §2.

*What it breaks.* Every product that treats regulatory scope as a schema — a column set, a form, a
report layout — needs a migration for the next regulator. A bank operating in five jurisdictions
cannot wait for a vendor roadmap for each.

---

**5. Documentation is the largest single cost, and it is stale on arrival.**

Hundreds of pages per model, produced by hand, describing a version that has since moved.

*What it breaks.* The model development document is the artefact a supervisor actually reads, and in
most banks it is the artefact that has drifted furthest from the model. Any process that produces it by
hand produces it stale; the only structural answer is to compile it from the register and compute its
staleness rather than remember it.

---

## 2. Two supervisors moving in opposite directions

### 2.1 United States — SR 26-2 / OCC 2026-13 / FDIC, 17 April 2026

The three agencies jointly issued *Revised Guidance on Model Risk Management*, superseding SR 11-7
(2011) and SR 21-8 (BSA/AML model risk, 2021). It is principles-based and materiality-driven, and it
**narrows** what counts as a model.

**Model definition (narrowed).**
> "the term 'model' refers to a complex quantitative method, system, or approach that applies
> statistical, economic, or financial theories to process input data into quantitative estimates.
> The term 'model' in this guidance **excludes simple arithmetic calculations, such as those found
> within spreadsheets, as well as deterministic rule-based processes and software** where there are
> no statistical, economic, or financial theories underpinning their design or use."

**Generative and agentic AI, carved out.**
> "Generative AI and agentic AI models are novel and rapidly evolving. As such, they are **not within
> the scope of this guidance**… However, the principles described in this guidance apply to traditional
> statistical and quantitative models and **non-generative, non-agentic AI models**."

Out of MRM scope is not out of risk-management scope, and the guidance says so. A bank still owes
controls; it simply cannot point at this document for them.

**Risk decomposed into four factors**, which MAYA stores separately rather than collapsing on input:

| Factor | Definition (SR 26-2) |
|---|---|
| **Inherent risk** | "the assumptions made in developing the model, the model's complexity, the quality of inputs for the model, and data constraints" |
| **Model exposure** | "the significance of the model output to a banking organization's business decisions… can be quantitatively measured (e.g., by portfolio size)" |
| **Model purpose** | "a qualitative consideration… models developed to help meet regulatory requirements or manage financial risk exposures are generally considered to be of greater risk" |
| **Model materiality** | "Model purpose, together with model exposure, determines model materiality." |

> "even a fundamentally sound model producing accurate outputs consistent with the model's design
> objective can exhibit high model risk **if it is misapplied or misused**."

That sentence is why risk attaches to a **use** and not only to an artefact, and why an inventory
that records one model per row loses the fact the sentence is about.

**Aggregate risk.**
> "Sound practice involves assessing model risk both individually and **in aggregate**. Aggregate risk
> reflects interactions and dependencies among models; reliance on common assumptions, data, or
> methodologies…"

**Effective challenge.**
> "the critical analysis conducted by objective experts who evaluate model risk and effect appropriate
> changes throughout the model lifecycle… performed by individuals with the appropriate expertise…
> sufficient independence to maintain objectivity, as well as the organizational standing and
> influence to effect any change."

**Validation cadence is no longer fixed.** SR 11-7's "at least annually" is gone:
> "The timing, nature, and frequency of validation activities vary based on model purpose, model
> methodology, frequency and scope of model changes, data limitations, and other practical constraints."

**Use before validation is permitted, with compensating controls.**
> "certain circumstances (e.g., an urgent business need) may necessitate using the model before
> validation is completed… determining appropriate controls (e.g., **placing limits on model use or
> more closely monitoring its performance**)."

A restricted approval is therefore a first-class state with machine-enforced limits, not a note in a
comment field.

**Vendor models.** "developing an understanding of the vendor model, including its conceptual
soundness, design, development data, and performance… conducting ongoing monitoring and outcome
analysis… Where vendor models are customized… appropriately documenting, justifying, and evaluating
adjustments."

**Enforceability.** The guidance "does not set forth enforceable standards or prescriptive
requirements; accordingly, non-compliance with this guidance will not result in supervisory criticism"
— *but* "supervisory action may result for any violations of law or unsafe or unsound practices
stemming from insufficient management of model risk." It records an applicability threshold of **$30bn
total assets**.

> **What the relaxation actually costs a firm.** Under a prescriptive regime, compliance is
> demonstrated by pointing at the rule you followed. Under a principles-based one, the burden moves to
> the firm to evidence that the controls it *chose* were proportionate and were *actually applied*.
> Fewer rules mean more evidence, not less. That is an evidence-graph problem, and it is the reason
> the April 2026 change increased rather than decreased the case for a system of record.

### 2.2 United Kingdom — PRA SS1/23, May 2023, amended 23 April 2026

Five principles, and a definition materially **broader** than SR 26-2's.

**Model definition (broad).**
> "A model is a quantitative method, system, or approach that applies statistical, economic, financial,
> or mathematical theories, techniques, and assumptions to process input data into output. The
> definition of a model includes input data that are quantitative and/or qualitative in nature or
> **expert judgement-based**, and output that are quantitative **or qualitative**."

With an explicit extension to deterministic methods:
> "where material deterministic quantitative methods such as decision-based rules or algorithms that
> are not classified as a model have a material bearing on business decisions and are complex in
> nature, firms should consider whether to apply the relevant aspects of the MRM framework."

**Principle 1.2 — inventory scope** covers models "implemented for use, **under development** for
implementation, or **decommissioned**", with prescribed content:

| SS1/23 1.2(c) | Required |
|---|---|
| (i) | purpose and use — "the intended use of the model **with a comparison to its actual use**, and the model **operating boundaries** under which model performance is expected to be acceptable" |
| (ii) | assumptions and limitations — "risks not captured in model and limitations in the data used to calibrate the model" |
| (iii) | validation findings — "indicators of whether models are functioning properly, the dates when those indicators were last updated, any **outstanding remediation actions**" |
| (iv) | governance — "the names of individuals responsible for validation, the dates when validation was last performed, and the **frequency of future validation**" |

**"Intended use compared to actual use" is the requirement almost nothing on the market implements**,
because implementing it requires observing calls. It cannot be satisfied by a form.

**Principle 1.3 — tiering on two independent axes**, not one score. Materiality is quantitative size
plus qualitative purpose; complexity is "the nature and quality of the input data, the choice of
methodology (including assumptions), the requirements and integrity of implementation, and the
frequency and/or extensiveness of use", extended for advanced techniques to "the use of alternative and
unstructured data" and "measures of a model's **interpretability, explainability, transparency, and the
potential for designer or data bias**".

And:
> "The firm-wide model tiering approach should be **subject to periodic validation**… Individual model
> tier assignments… should be **independently reassessed as part of the model validation** process."

*The tiering model is itself a model.* A register that cannot hold its own tiering rule is a register
with a governance hole exactly where the control depth is decided.

**Principle 3.3 — development testing**, including for **dynamic models** — "models able to adapt,
recalibrate, or otherwise change autonomously in response to new inputs" — requiring **parallel
outcomes analysis** comparing pre-change and post-change output against actuals.

**Principle 3.4 and Principle 5 — model adjustments and post-model adjustments.** The capability most
absent from commercial tooling:
> "the adjustments should be adequately justified and clearly recorded in the model inventory… the
> decisions taken relating to the reasons for model adjustments, and **how the adjustments should be
> calculated over time**."
> "Where such adjustments are made either to a **feeder model** whose output is the input [to
> another]… the impact… on related models should also be assessed and the relevant model owners and
> users should be made aware."
> "Firms should have a process to consider whether the materiality of model adjustments or a **trend of
> use of recurring model adjustments for the same model limitations**" indicates a deeper problem.

**Principle 2.6 — vendor models.** Firms should "satisfy themselves that the vendor models have been
validated to the same standard", "verify the relevance of vendor supplied data and their assumptions",
and validate their own use "using their own outcomes".

### 2.3 EU AI Act

High-risk obligations (Articles 6–49) apply from **2 August 2026**. The classifications that reach a
bank:

- **Annex III(5)(b)** — AI used "to evaluate the creditworthiness of natural persons or to establish
  their credit score" → high-risk.
- **Annex III(5)(c)** — risk assessment and pricing for life and health insurance.
- **Annex III(4)** — employment: recruitment screening, promotion and termination decisions.
- Fraud detection for financial services carries a **derogation** — explicitly *not* high-risk under
  the creditworthiness heading. A scoping subtlety that has to be encoded rather than assumed, because
  the intuitive answer is wrong.

Obligations that become concrete platform features: risk management system (Art. 9), data governance
(Art. 10), **technical documentation to Annex IV** (Art. 11), **automatic event logging over the
system's lifetime** (Art. 12), transparency to deployers (Art. 13), human oversight (Art. 14),
accuracy/robustness/cybersecurity (Art. 15), quality management (Art. 17), **log retention** (Art. 19),
post-market monitoring (Art. 72), serious incident reporting (Art. 73). Penalties reach 3% of global
turnover for high-risk breaches. DORA overlaps on ICT third-party risk across the vendor-model estate.

### 2.4 The rest of the frame

| Framework | Why it reaches the model estate |
|---|---|
| **NIST AI RMF 1.0** (Govern/Map/Measure/Manage) + **Generative AI Profile (AI 600-1)** | Voluntary, and the de facto US control vocabulary for AI |
| **ISO/IEC 42001** (AIMS), **ISO/IEC 23894** | Certifiable management system, increasingly demanded by counterparties |
| **Basel** — IRB (CRR Art. 143–191), FRTB, SA-CCR, IRRBB | Internal model approval, PLA and backtesting, NMRF — approvals with scope, conditions and expiry |
| **IFRS 9 / ASC 326 (CECL)** | ECL staging, lifetime PD/LGD, macro overlays, PMA disclosure |
| **CCAR / DFAST / ICAAP / ILAAP** | A supervisory stress-test estate with its own submission lineage |
| **ECOA / Reg B, FCRA, UDAAP; CFPB on advanced credit models** | Adverse-action reason codes, disparate impact, **search for less discriminatory alternatives** |
| **SR 11-3 / OCC 2013-29 & 2020-10, PRA SS2/21** | Third-party and vendor model oversight |
| **BCBS 239** | Risk data aggregation: accuracy, completeness, timeliness, lineage |
| **SOX / ICFR** | Models feeding the financial statements are key controls |
| **GDPR Art. 22** | Automated decision-making and the right to an explanation |

### 2.5 What the divergence costs

A global bank must satisfy a **narrow** US scope and a **broad** UK scope over **one** inventory, at
the same time, for the same models — and must be able to say, per model, which regime says what and
why.

Three consequences the rest of this specification is built on:

1. **Scope is a multi-valued attribute with a stored rationale**, never a schema. A model is
   `{SR-26-2: out, SS1/23: in, EU-AI-Act: high-risk, IRB: in, SOX: key-control}`, and each
   determination has to survive being asked about two years later.
2. **Disagreement is a fact, not an error.** In scope for one supervisor and out for another is the
   correct answer to a real question. Merging the regimes into one verdict destroys the answer.
3. **Adding a supervisor must not be a migration.** The next regulator is not going to wait.

MAYA encodes SR 26-2, SS1/23 and the EU AI Act as **institutions** — a signature, obligations in that
vocabulary, and a translation into the core — and checks the satisfaction condition (`L-8`) against
probe states before a regime can be activated. Determinations carry the terms they read. Regimes that
disagree are reported as disagreeing. See [00 §8](00-mathematical-foundations.md) and
[ADR-005](adr/ADR-005-institutions-for-regimes.md).

---

## 3. What the incumbents do, and where each stops

Four categories, each described as its own vendor would describe it, then the boundary. The boundary
is not a defect: it is where the product stopped because its buyer stopped.

### 3.1 Governance without the artefact — GRC and MRM platforms

| Product | Genuinely strong at | Stops at |
|---|---|---|
| **IBM OpenPages (Model Risk Governance)** | Enterprise GRC breadth — operational risk, policy, audit, controls — on one platform, at global-estate scale, with two decades of workflow | Metadata is hand-keyed; nothing binds the record to the artefact; no feature layer; no execution |
| **SAS Model Risk Management** | A deep MRM domain model and strong validation workflow and reporting; excellent in SAS-centric estates | SAS-ecosystem gravity; weak over Python and open-source estates; the artefact link is by reference |
| **MetricStream / LogicManager / Empowered** | GRC workflow, mid-market friendly, quick to stand up | A generic risk register with a "model" object type; no technical depth |
| **Moody's Model Lifecycle Management** | Credit-risk domain content, benchmarking data, a serious analytics heritage | Oriented to Moody's own model content; thin over trading and generative estates |
| **ValidMind** | Best-in-class **documentation automation** and validation templates for regulated financial services; a developer SDK that pushes test results into governance | Documentation and validation centred; not an execution or feature platform; no notion of a warrant |
| **Yields.io (Chiron)** | Automated validation and testing; quantitatively serious; challenger automation | A validation point solution rather than the system of record for a lifecycle |
| **ModelOp Center** | The strongest **inventory automation** and continuous discovery; use-case intake; model cards and audit reports; agentic AI governance | A governance overlay over other people's runtime; not a feature platform; limited native quant coverage |
| **Mitratech ClusterSeven / CIMCON / Apparity / Incisive** | **EUC and spreadsheet discovery** — scanning shared drives, complexity scoring, change detection | EUC only, deliberately |
| **FICO Decision Central** | Decision-centric governance tied to the FICO platform | Vendor-ecosystem gravity |

**Where the category stops.** Nothing in these products can independently verify that the model
described in the workflow is the model running in production, because nothing in them ever touched the
artefact. They hold **assertions about models**. That is not a failure of implementation quality; it is
the consequence of a data model in which the model is a row.

### 3.2 Artefacts without the governance — MLOps platforms

| Product | Genuinely strong at | Stops at |
|---|---|---|
| **MLflow + Unity Catalog** | Experiment tracking, a model registry, **aliases as mutable pointers**, real lineage from version → run → notebook → dataset, cross-workspace governance | No MRM workflow, no validation findings, no overlays, no tiering, no vendor/EUC/quant coverage, no regulatory documents |
| **Databricks (UC + MLflow + Lakehouse Monitoring)** | The strongest single **substrate**: Delta Lake, lineage, monitoring, serving; the vendor now markets SR 26-2 alignment directly | Platform gravity; no MRM domain objects; assumes everything is a trainable ML asset |
| **AWS SageMaker / GCP Vertex Model Registry** | Registry, approval status, model cards, endpoints, tight cloud integration | Cloud-scoped; thin governance; no bank-domain concepts |
| **Domino Data Lab (+ Domino Governance)** | Policy templates for the **EU AI Act and NIST AI RMF**, and governance embedded in the data scientist's IDE — which is the right *placement*, and the thing most competitors get wrong | Tied to Domino workspaces; not an estate-wide inventory across SAS, C++, vendor and spreadsheet models |
| **Dataiku / DataRobot / H2O** | Broad AutoML with governance modules attached | Governance covers their own platform's models |
| **KServe / BentoML / Seldon / MLServer** | Standardised serving, the **Open Inference Protocol (KServe V2)**, multi-framework runtimes | Serving only; no notion of "may this model be used for this purpose by this team" |
| **Arize / Fiddler / Arthur / Evidently / WhyLabs / NannyML** | Drift, performance, explainability, fairness, LLM observability — mature and genuinely good | Monitoring only, disconnected from approval state and validation findings |

**Where the category stops.** Their object model has no materiality, no approved use, no effective
challenge, no overlay, no finding and no regulatory approval — and a large share of a bank's estate
never passes through them at all, because a QuantLib pricing library, a SAS scorecard, a Murex
valuation and four thousand spreadsheets do not arrive as registered ML artefacts.

### 3.3 Features without an algebra — feature stores

This is the category the current design competes with most directly, and the honest reading is more
generous than the usual one.

| Product | Genuinely strong at | Stops at |
|---|---|---|
| **Feast** | The reference open-source implementation; deliberately un-opinionated, easy to adopt | Un-opinionated is the point and the limit: there is no algebra over feature definitions, so no question about two featuresets can be answered structurally |
| **Tecton** | A mature managed offering; real point-in-time correctness; strong operational tooling | Composition is Python function composition, and therefore untyped and un-analysable — you can run it, not reason about it |
| **Hopsworks** | **Genuine prior art.** Versioned feature groups and versioned *feature views*, with training-dataset provenance — the closest thing on the market to a featureset as a governed object, and it predates this design | No governance beyond the data layer: no approvals, no findings, no model documentation, no supervisory scope |
| **Databricks Feature Store** | Delta time travel underneath, so reproducibility rests on a mature substrate | Time travel is at *table* granularity; a featureset with a name, a schema and a version is not an object in it |

**Where the category stops.** Point-in-time joins are offered; refusal is not. A read with no stated
`as_of` is served rather than declined; a normalisation fitted over the whole column is nobody's
concern; and no store treats "can this featureset stand in for that one" as a question with a defined
answer. **No feature store has an algebra.**

### 3.4 An algebra without time — semantic layers

**dbt MetricFlow, Cube, Malloy, LookML.** These have real composition semantics and are ahead of every
feature store on it. MetricFlow's measure / dimension / entity split is the right decomposition, and
its metric graph is analysable in ways a feature store's Python is not.

**Where the category stops.** **None of them is bitemporal.** They can answer *what is the number*;
they cannot answer *what was the number as we knew it on the day the decision was made*, which is the
only form of the question a validator or an examiner asks. A metric layer that recomputes history
silently is the exact failure the two clocks exist to prevent.

### 3.5 Standards and building blocks

Adopted, adopted in part, or noted and not adopted — stated as three categories rather than one list,
because a list of "standards we align with" is a list nobody can check.

| Standard | Status in MAYA |
|---|---|
| **Open Inference Protocol / KServe V2** | **Design target, not implemented.** `rest` is one of the eighteen runtimes in the warrant grammar; MAYA does not host an OIP endpoint |
| **ONNX / PMML / safetensors** | **Adopted.** Among the eight artifact formats the store accepts. There is no `pickle`, at all, by construction |
| **`torchscript` / `tar`** | **Accepted and labelled.** Both execute code on load; the warrant says so, so an engine is not inferring it from a file extension |
| **SPDX 3.0 AI & Dataset profiles / CycloneDX ML-BOM / OWASP AIBOM** | **Not built.** Worth adopting as an export format — research indicates current AIBOM schemas already satisfy 13 of 14 EU AI Act information obligations — and the export pack is the natural place for it |
| **in-toto / Sigstore / SLSA** | **Not built.** MAYA content-addresses and verifies digests; it does not sign artifacts or carry build provenance |
| **OpenLineage** | **Not built.** The evidence graph would ingest it; nothing does |
| **Model Cards** | **Adopted.** One of four compiled document kinds, alongside the model development document, the validation report and Annex IV |
| **Open Policy Agent / Rego** | **Deliberately not adopted.** The policy register uses a closed predicate language of its own — comparison, membership, boolean connectives, two quantifiers, no loops and no function definitions — because a rule a reviewer has to *run* to understand is not a reviewable control |

---

## 4. The model supply chain is a live threat, and nothing above addresses it

Research reports that **44.9% of popular Hugging Face models still ship as pickle**; that pickle
deserialises to arbitrary code execution; that malicious `.pth` files carrying remote-access tools have
been published to trusted hubs; and that scanners produce both false positives and false negatives. For
a bank ingesting third-party and open-source models this is an unmanaged supply-chain vector sitting
underneath every other control.

**What MAYA does.** The artifact store is content-addressed — a file's name is its own SHA-256 — so an
artifact cannot be edited in place, a declared digest is checked at upload rather than trusted, and
"these are the bytes the warrant names" is true by construction rather than by procedure. The format
vocabulary is **closed and contains no `pickle`**. Formats that execute code on load are accepted and
**named as such on the warrant**. Artifact-backed runtimes load in a child process with CPU and
address-space limits read from the warrant.

**What MAYA does not do, stated plainly.** There is no malware scan, no pickle opcode analysis, no
dependency vulnerability scan and no secret detection at upload; and the sandbox's own `describe()`
says what it protects against — a runaway loop, an allocation storm, a hard crash — and what it does
not, which is a hostile artifact. That needs a container or a VM.

---

## 5. Prior art this design stands on

Cited rather than quietly reused, because a design document that presents borrowed structure as
invention is one nobody in the field will trust on anything else.

| Idea | Source | Where it is used |
|---|---|---|
| **Provenance semirings**, and the universal `ℕ[X]` | Green, Karvounarakis & Tannen, PODS 2007 | The evidence graph, and derived-feature lineage. `ℕ[X]` is implemented and its universal property is `L-9`, checked over 200 random derivation DAGs |
| **Bitemporality** — valid time and transaction time | Snodgrass; SQL:2011 system-versioned and application-time tables | The two clocks. SQL:2011's `AS OF` is the standard the `AsOf` operator names |
| **Versioned featuresets** | **Hopsworks** feature groups and feature views | Genuine prior art for the idea that a *selection of features* is a versioned object with training-set provenance. MAYA's featureset differs in being a **schema of slots** filled per version, which is what makes two versions with different constituents the same input space — but the ancestry is Hopsworks' and should be said |
| **Refinement types** | Rondon et al., *Liquid Types* | The lattice's `Field` carries the same bounds the operating contract carries as assumptions, so the two are one idea rather than two |
| **Aliases as mutable pointers** | MLflow / Unity Catalog | `#champion` resolution. MAYA adds that the move is a proof obligation |
| **Measure / dimension / entity** | dbt MetricFlow | The right decomposition, and the reason §3.4 is generous to the semantic layers |
| **Functorial data migration** (`Δ ⊣ Σ`, `Δ ⊢ Π`) | Spivak; Wisnesky's CQL | **Vocabulary borrowed, machinery not built.** Named here so it is not later presented as shipped |

---

## 6. The gap — why we build

### 6.1 What is absent from every product surveyed

Not "we do it better" — absent, as an object in the data model.

1. **One register that genuinely spans all nine trainability classes.** A Monte Carlo XVA engine, a
   vendor black box, a gradient-boosted fraud model, a SAR-drafting LLM and a pricing spreadsheet, each
   with class-appropriate evidence, and a fit request refused for the ones where fitting is a type
   error rather than an omission.
2. **A governance record bound to the artefact.** Everywhere else, "validated" is a field somebody set.
   Here it is a node in an append-only hash chain whose verification **re-derives** each node's content
   hash from its own fields — because re-linking proves the links are intact and says nothing about
   whether the thing linked is still what was recorded.
3. **Governed execution as a contract rather than a monopoly.** A signed, expiring, entitlement-bound
   warrant that an execution engine acts on, so governance is never in the serving path and a governed
   version move requires no consumer to redeploy — and revocation still takes effect in under a minute.
4. **Approved use against actual use.** SS1/23 1.2(c)(i) as a computation over resolution telemetry
   rather than a field somebody fills in.
5. **A post-model-adjustment register with teeth.** Time-boxed, measured, renewed only against a
   measurement, and raising a finding when it outlives its limit — because at that point it is an
   unversioned model change.
6. **Documentation compiled from the register**, filed against what it is *about* — a training record
   per parameter set, a data dictionary per featureset version — with staleness computed from the chain
   rather than remembered, and every gap named rather than left blank.

### 6.2 The one claim that is defensible with a test

Everything in §6.1 is a product argument. This one is a technical position, and it is checkable:

> **No feature store has an algebra. The semantic layers have an algebra and no time. MAYA has both.**

| | Checked by |
|---|---|
| Schemas form a **lattice**, and every substitutability question in the platform — schema variance, warrant admissibility, contract refinement, parent refinement — is the same comparison in it | `L-20`, `core/domain/lattice.py`, `tests/test_laws.py::TestL20SchemasFormALattice` |
| The point-in-time read is an **operator** with four properties, the fourth of which — **saturation at the label** — is the reproducibility guarantee: every read at or after the label gives the same answer, however many restatements arrived in between | `L-10`, `tests/test_laws.py::TestL10TheAsOfOperator` |
| **Composition type-checks.** An `input_to` edge holds only if what the source produces can stand in for what the target reads; a composite's schema is *derived* rather than declared | `L-21`, `core/registry/composition.py`, `tests/test_laws.py::TestL21FeedsIsCompositionRatherThanADrawing` |
| Composition of definitions is a **monoid**, and independent edits **commute**, so the order two people happened to edit a shared featureset in carries no meaning | `L-19`, `L-20`, `tests/test_composition.py` |

Full treatment in [17 — The Algebra](17-feature-and-model-algebra.md). Sixteen of the twenty-one
foundational laws are executable and a failing one fails the build; the five that are not are named with
the reason in [00 §12](00-mathematical-foundations.md#12-the-laws-maya-enforces).

### 6.3 What MAYA has since built, against this survey

Stated because a competitive section written before the code is a competitive section that has stopped
being true.

| Capability | State |
|---|---|
| **Content-addressed artifact store** | Built. Eight formats, no `pickle`, digest checked at upload, two-level fan-out, 8 GiB ceiling |
| **Export packs** | Built. Self-contained, digested member by member, carrying where the evidence chain stood, with `gaps.md` naming what could not be gathered |
| **Risk appetite as a computable limit** | Built. Twelve derived metrics; a limit over a metric the platform cannot compute is refused *when the limit is written*; an unmeasured indicator is reported as unmeasured and never as clean; and there is **no composite score**, because aggregation requires the parts to compose |
| **The documentation graph** | Built. Six document subjects across five moments, every subject pinned; a dossier walked from a model with every empty node named as a gap |
| **Python SDK** | Built, standard library only, and it decides nothing — a source walker in the suite refuses a trainability class appearing in client code |
| **The algebra** | Built and tested — §6.2 |

### 6.4 What MAYA does not have

The same survey applied to MAYA. Anything here that a reader discovers rather than reads is a reader
lost.

- **No connectors and no discovery.** No MLflow, Unity Catalog, SageMaker, git, SAS-metadata or CMDB
  import; no scheduled sweep for unregistered models; no EUC scanner ingestion. ModelOp and the EUC
  vendors do this properly today and MAYA does not do it at all.
- **No online feature store**, so `L-17` — the contract–serving agreement — is stated and cannot run.
  Half of it exists: `serving_namespaces` computes what serving must read.
- **No document rendering beyond markdown.** No PDF, no house template, no signature page.
- **Attached documents are stored, not read.** Markdown and text are indexed; a PDF is served
  faithfully and reported as *not machine-readable*, because it is.
- **No SAML, no SCIM, no MFA enforcement.** OIDC only, and a leaver is suspended by hand.
- **Parameters are computed for two families and recorded for the rest.** `ols` and `garch11` in the
  captive engine; everything else is fitted wherever you run models and refused unless a warrant MAYA
  issued authorised the run.
- **Five runtimes of the eighteen** are implemented in the captive engine. Each of the rest is refused
  by name.
- **No artifact signing, no build provenance, no upload scanning** — §4.
- **Scale is designed for and not demonstrated.** The scale suite asserts complexity rather than
  wall-clock, deliberately; it has not been run against a real estate.
- **No ecosystem.** Databricks and Domino arrive with connectors, an installed base and a support
  organisation.

The bet is that the items above are **work**, and that §6.1 and §6.2 are **architecture** — that a
platform built on evidence and refusal can add connectors, rendering and scale, but a platform built on
workflow cannot retrofit evidence into a record that was never bound to the artefact.

---

## 7. Sources

**Regulation and supervisory guidance**
- [SR 26-2 — Revised Guidance on Model Risk Management (Federal Reserve, 17 Apr 2026)](https://www.federalreserve.gov/supervisionreg/srletters/SR2602.pdf)
- [OCC Bulletin 2026-13 — Model Risk Management: Revised Guidance](https://www.occ.gov/news-issuances/bulletins/2026/bulletin-2026-13.html)
- [OCC News Release 2026-29](https://www.occ.gov/news-issuances/news-releases/2026/nr-occ-2026-29.html)
- [Davis Polk — Visual memo: key changes under the revised MRM guidance](https://www.davispolk.com/insights/client-update/visual-memo-key-changes-under-federal-banking-agencies-revised-model-risk)
- [Sullivan & Cromwell — Federal Banking Agencies Issue Revised Guidance on Model Risk Management](https://www.sullcrom.com/insights/memo/2026/April/OCC-Fed-FDIC-Issue-Revised-Guidance-Model-Risk-Management)
- [Orrick — Agencies Overhaul Model Risk Management Guidance](https://www.orrick.com/en/Insights/2026/04/Agencies-Overhaul-Model-Risk-Management-Guidance-for-Banks-Heres-What-Changed)
- [PRA SS1/23 — Model risk management principles for banks (as amended April 2026)](https://www.bankofengland.co.uk/-/media/boe/files/prudential-regulation/supervisory-statement/2026/liaf0126app5.pdf)
- [PRA SS1/23 publication page](https://www.bankofengland.co.uk/prudential-regulation/publication/2023/may/model-risk-management-principles-for-banks-ss)
- [FDIC — Model Risk Management examination manual section](https://www.fdic.gov/risk-management-manual-examination-policies/model-risk-management)
- [EU AI Act Article 6 — high-risk classification](https://www.fluxforce.ai/regulations/eu-ai-act-article-6-high-risk)
- [EU AI Act timeline for financial services](https://www.horizon-scanner.com/landing/en/blog/eu-ai-act-timeline-financial-services)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [CFPB — Adverse action notices when using AI/ML models](https://www.consumerfinance.gov/about-us/blog/innovation-spotlight-providing-adverse-action-notices-when-using-ai-ml-models/)
- [CFPB fair lending risks in advanced credit scoring models](https://www.consumerfinancialserviceslawmonitor.com/2025/01/cfpb-highlights-fair-lending-risks-in-advanced-credit-scoring-models/)

**Industry data and practice**
- [Moody's — The evolving model risk management landscape in banking (2026 survey, 79 MRM leaders)](https://www.moodys.com/web/en/us/insights/banking/the-evolving-model-risk-management-landscape-in-banking.html)
- [RMA Model Risk Management Survey](https://www.rmahq.org/journal-articles/2024/october-november-2024/in-rma-s-model-risk-management-survey-a-picture-of-banks-diligence-and-frustrations/)
- [Databricks — Model risk management in 2026: a banker's guide to the revised interagency guidance](https://www.databricks.com/blog/model-risk-management-2026-bankers-guide-revised-interagency-guidance)
- [Building a defensible banking model & AI inventory (2026)](https://pitechsol.com/blog/banking-model-ai-inventory/)
- [ACAMS — Effective AML model risk management: six critical components](https://www.acams.org/en/opinion/effective-aml-model-risk-management-for-financial-institutions)
- [Stout — Best practices for bank model risk management](https://www.stout.com/en/insights/article/best-practices-bank-model-risk-management)
- [RiskSpan — End-user computing controls: building an EUC inventory](https://riskspan.com/end-user-computing-controls-euc-inventory/)
- [Model Validation Practice in Banking: A Structured Approach (arXiv)](https://arxiv.org/html/2410.13877v1)

**Products**
- [ModelOp — Evergreen AI Model Inventory](https://www.modelop.com/ai-governance-software/inventory)
- [ValidMind — Model & AI governance platform](https://validmind.com/platform/governance/)
- [Domino Governance](https://docs.dominodatalab.com/en/latest/user_guide/7f8a63/domino-governance/)
- [Yields.io — SS1/23 model risk management principles](https://www.yields.io/insights/ss1-23-model-risk-management-principles-for-uk-banks)
- [Mitratech — Top MRM software solutions 2026](https://mitratech.com/resource-hub/blog/top-8-model-risk-management-mrm-software-solutions-for-2026/)
- [Model Risk Directory — buyer comparison](https://modelriskdirectory.com/guides/best-model-risk-management-software)

**Feature stores, semantic layers and technical standards**
- [MLflow Model Registry](https://mlflow.org/docs/latest/ml/model-registry/)
- [Databricks — Manage model lifecycle in Unity Catalog (aliases, lineage)](https://docs.databricks.com/aws/en/machine-learning/manage-model-lifecycle/)
- [Feature store comparison 2026: Feast, Tecton, Hopsworks](https://mlopsplatforms.com/posts/feature-store-comparison-2026/)
- [Databricks — What is a feature store?](https://www.databricks.com/blog/what-is-a-feature-store)
- [KServe — Open Inference Protocol V2](https://kserve.github.io/website/docs/concepts/architecture/data-plane/v2-protocol)
- [KServe — model serving frameworks overview](https://kserve.github.io/website/docs/model-serving/predictive-inference/frameworks/overview)
- [IBM Research — Toward a transparent supply chain for AI (AI-BOM)](https://research.ibm.com/blog/ai-bill-of-materials)
- [Operationalising AI Bills of Materials for verifiable provenance (arXiv)](https://arxiv.org/pdf/2605.19755)
- [Delta Lake time travel for financial services (JETA)](https://www.espjeta.org/Volume2-Issue1/JETA-V2I1P109.pdf)

**Model supply-chain security**
- [Trail of Bits — Exploiting ML models with pickle file attacks](https://blog.trailofbits.com/2024/06/11/exploiting-ml-models-with-pickle-file-attacks-part-1/)
- [PickleBall: secure deserialization of pickle-based ML models (ACM CCS 2025)](https://dl.acm.org/doi/10.1145/3719027.3765037)
- [A large-scale exploit instrumentation study of AI/ML supply chain attacks in Hugging Face models (arXiv)](https://arxiv.org/pdf/2410.04490)

**Generative AI governance**
- [Governing Generative AI Across Financial Institutions: An SR 26-2-Compatible Framework (arXiv 2607.04103)](https://arxiv.org/html/2607.04103v2)
- [Model Risk Management for Generative AI in Financial Institutions (arXiv 2503.15668)](https://arxiv.org/pdf/2503.15668)
- [GAF-Guard: an agentic framework for risk management and governance in LLMs (arXiv)](https://arxiv.org/pdf/2507.02986)
- [Evaluation and benchmarking suite for financial LLMs and agents (arXiv)](https://arxiv.org/pdf/2602.19073)

**Academic prior art**
- Green, Karvounarakis & Tannen, *Provenance semirings*, PODS 2007
- Snodgrass, *Developing Time-Oriented Database Applications in SQL*; ISO/IEC 9075:2011 §4.16
- Rondon, Kawaguchi & Jhala, *Liquid Types*, PLDI 2008
- Spivak, *Functorial data migration*; Wisnesky et al., CQL

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
