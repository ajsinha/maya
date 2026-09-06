---
title: Defining a model in MAYA
slug: defining-a-model
section: Start here
order: 10
icon: box-seam
summary: Register a model and its first version — on screen, from the SDK and with curl — with a worked kernel for each of the nine trainability classes, the documents you can file against it, what a second version may and may not change, and how one model is composed with or derived from another.
audience: Model developers, Model owners, Model risk managers
---

# Defining a model in MAYA

Everything else in this platform hangs off two records, so it is worth thirty
seconds on the difference before you create either.

| | |
|---|---|
| A **model** | the record: a URN, an owner, a purpose, a tier. Created once. |
| A **version** | the kernel that actually runs: schemas, contract, artifact digest. **Immutable** from the moment it exists. |
| A **parameter set** | one point of `P` — this morning's calibration, this quarter's fit. A refit is a *new parameter set*, never a new version. |

That last line saves the most time. Re-running the fit does not produce a new
version, because the kernel did not change. See
[warrants and training](/tutorials/warrants-and-training) for where fitted
parameters go.

Everything below is shown three ways: on screen first, then the SDK, then curl.
They are the same endpoints — the screens decide nothing.

---

## 1 · Register the model

**On screen.** Go to **`/models/new`**. The left-hand card, *Register the model*,
takes seven fields: the URN, a name, a model class, a domain, a legal entity, the
owner and what it is for. Press **Register**.

**SDK.**

```python
from maya_sdk import Maya

owner = Maya("http://localhost:5006", "j.okafor", "owner-pw")

owner.models.register(
    urn="maya://model/credit.pd.smallbiz",
    name="Small business PD",
    model_class="credit.pd.scorecard",
    domain="credit",
    owner="person/j.okafor",
    legal_entity="LE-US-01",
    purpose="12-month PD at origination",
    description="Logistic scorecard over five financial ratios.")
```

**curl.**

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn": "maya://model/credit.pd.smallbiz",
       "name": "Small business PD",
       "model_class": "credit.pd.scorecard",
       "domain": "credit",
       "owner": "person/j.okafor",
       "legal_entity": "LE-US-01",
       "purpose": "12-month PD at origination",
       "description": "Logistic scorecard over five financial ratios."}'
```

```json
{"urn": "maya://model/credit.pd.smallbiz", "name": "Small business PD",
 "status": "draft", "tier": null, "origin": "internal",
 "created_by": "j.okafor", "id": "01a07374c13dd624cb4e921e74d2"}
```

Registering is the **owner's** act, not the developer's. A developer gets:

```json
{"error": "forbidden",
 "detail": "'model:register' is not granted by your roles (model_developer)",
 "remediation": "ask an administrator for a role that carries this permission"}
```

Assess the risk tier next — but do it *after* the first version, because the tier
reads the version's class. See [risk tiering](/help/risk-tiering).

---

## 2 · The first version, and the class you never type

A version declares the kernel: how `P` is inhabited, what goes in, what comes
out, and what the model promises. The **trainability class `T0`–`T8` is derived**
from `parameter_kind` and `fit_procedure`. There is no field to type it into.

**On screen.** **`/model-algebra/version/{name}`** — for this model,
`/model-algebra/version/credit.pd.smallbiz`. Choose `parameter_kind` and
`fit_procedure` and the *class, derived* panel fills in beside the form, showing
which branch fired and what evidence the class then requires. **Create version**
stays disabled until the register says the kernel would be accepted.

**SDK.**

```python
dev = Maya("http://localhost:5006", "d.raman", "dev-pw")

dev.versions.create(
    "maya://model/credit.pd.smallbiz",
    semver="1.0.0",
    artifact_digest="sha256:431e6dc969271581d46cbddfb2dc9b0cf9d72d6bacc4b1c72f4e07fe95575143",
    kernel={"parameter_kind": "estimated_coefficients",
            "fit_procedure": "estimate",
            "output_kind": "point_estimate",
            "input_schema": [{"name": "dscr", "dtype": "float", "minimum": -5, "maximum": 20},
                             {"name": "years_trading", "dtype": "float", "minimum": 0, "maximum": 100}],
            "output_schema": [{"name": "pd_12m", "dtype": "float", "minimum": 0, "maximum": 1}]},
    contract={"assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
              "guarantees": [{"key": "gini", "minimum": 0.42}],
              "on_boundary_violation": "reject"})
```

**curl.** The same body, at
`POST /api/v1/models/credit.pd.smallbiz/versions`:

```bash
curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver": "1.0.0",
       "artifact_digest": "sha256:431e6dc969271581d46cbddfb2dc9b0cf9d72d6bacc4b1c72f4e07fe95575143",
       "kernel": {"parameter_kind": "estimated_coefficients",
                  "fit_procedure": "estimate",
                  "output_kind": "point_estimate",
                  "input_schema": [{"name": "dscr", "dtype": "float", "minimum": -5, "maximum": 20},
                                   {"name": "years_trading", "dtype": "float", "minimum": 0, "maximum": 100}],
                  "output_schema": [{"name": "pd_12m", "dtype": "float", "minimum": 0, "maximum": 1}]},
       "contract": {"assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
                    "guarantees": [{"key": "gini", "minimum": 0.42}],
                    "on_boundary_violation": "reject"}}'
```

```json
{"semver": "1.0.0", "trainability_class": "T2", "status": "draft",
 "parameter_kind": "estimated_coefficients", "fit_procedure": "estimate",
 "manifest_digest": "sha256:ce923dbf6c4b1ac06f1287a3977e4543f50475b45eec46998af5cd57fd59f204"}
```

`T2` was derived, not supplied. Now assess:

```bash
curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure": 40000000, "purpose_class": "risk_management"}'
```

```json
{"tier": 3, "materiality": "low", "complexity": "simple",
 "rationale": "materiality=low (exposure 40,000,000 in band 'low', purpose 'risk_management'); complexity=simple (class T2); tau(low,simple)=Tier 3 under ruleset 2026.09.1"}
```

Assess before there is a version and the rationale reads `class T0`, because
there is no class to read yet. And submit before assessing at all and you get:

```json
{"error": "not_tiered",
 "detail": "this model has no risk tier; approval depth depends on it",
 "remediation": "POST /api/v1/models/{name}/assess before submitting"}
```

### Try the kernel before you write it

`POST /api/v1/model-algebra/kernel` answers *what class would this be, and would
it be accepted* — it writes nothing and needs only `model:read`. It is what the
version screen calls as you type. The SDK has no wrapper for it, so use the
client's `call`:

```python
dev.call("POST", "/model-algebra/kernel",
         json={"parameter_kind": "learned_weights",
               "fit_procedure": "train", "adaptive": 1})
# {"ok": 1, "trainability_class": "T4", "requires_fitting_evidence": 1, ...}
```

---

## 3 · A kernel for every class

Nine classes, and the two fields that decide each one. Every row below was
created as a real version.

| Class | `parameter_kind` | `fit_procedure` | Worked example | `X → Y` |
|---|---|---|---|---|
| **T0** analytical | `none` | `none` | `pricing.equity.blackscholes` | `spot, strike, tau, vol, rate → price` |
| **T1** calibrated | `calibration_set` | `calibrate` | `rates.curve.usdois` | `tenor_years → discount_factor` |
| **T2** estimated | `estimated_coefficients` | `estimate` | `credit.pd.retail` | `bureau_score → pd_12m` |
| **T3** learned | `learned_weights` | `train` | `fraud.card.gbm` | `amount, mcc → p_fraud` |
| **T4** adaptive | `learned_weights` | `train` + `"adaptive": true` | `pricing.quote.bandit` | `client_tier, notional → spread_bps` |
| **T5** configured | `llm_configuration` | `configure` | `kyc.adverse.summariser` | `article_text → summary` |
| **T6** vendor | `opaque` | `none` | `credit.rating.vendor` | `issuer_id → rating` |
| **T7** elicited | `elicited_weights` | `elicit` | `risk.country.expert` | `country → country_risk_score` |
| **T8** authored | `rule_set` | `author` | `aml.screening.rules` | `amount, country → decision` |

Two of them are worth seeing in full, because they are the two people get wrong.

**T0 — nothing to fit.** `P` is the terminal object, so asking this model for a
training set is a category error rather than rigour, and MAYA does not:
`requires_fitting_evidence` comes back `0`. The same is true of T6.

```json
{"parameter_kind": "none", "fit_procedure": "none",
 "output_kind": "point_estimate",
 "input_schema": [{"name": "spot", "dtype": "float", "minimum": 0},
                  {"name": "strike", "dtype": "float", "minimum": 0},
                  {"name": "tau", "dtype": "float", "minimum": 0},
                  {"name": "vol", "dtype": "float", "minimum": 0},
                  {"name": "rate", "dtype": "float"}],
 "output_schema": [{"name": "price", "dtype": "float", "minimum": 0}]}
```

**T4 — a trained kernel that keeps learning.** One extra field separates it from
T3, and it is a governance fact, not a footnote: the artifact under the warrant
stops being the artifact that was validated.

```json
{"parameter_kind": "learned_weights", "fit_procedure": "train",
 "adaptive": true, "output_kind": "point_estimate",
 "input_schema": [{"name": "client_tier", "dtype": "string"},
                  {"name": "notional", "dtype": "float", "minimum": 0}],
 "output_schema": [{"name": "spread_bps", "dtype": "float", "minimum": 0}]}
```

**T6 is reached before the fit procedure is read.** `opaque` says `P` exists and
you cannot see it, so nothing after it is checked — which is why the vendor row
above carries `fit_procedure: none` without being refused.

Everywhere else, real parameters with no fit procedure *are* refused:

```json
{"error": "registry_refused",
 "detail": "this version declares parameters ('learned_weights') and no fit procedure, which says both that the model has parameters and that nothing produced them. Declare how P was inhabited — 'calibrate', 'estimate', 'train', 'configure', 'elicit' or 'author' — or declare parameter_kind 'none' if there really are none"}
```

What each class then owes — evidence, metrics, templates — is on
**`/model-algebra`**, or from `maya.fibres.of("T2")`.

---

## 4 · Attach the documents

Yes, now. A document is filed against **what it is about**, and the answer is
usually one version rather than the model.

There are nine kinds — from `model_development_document` and
`validation_report` through to `other` — and six subjects: `model`,
`model_version`, `parameter_set`, `featureset_version`, `feature`, `validation`.
Ask rather than remember: `GET /api/v1/attachment-kinds` and
`GET /api/v1/document-subjects`.

**On screen.** **`/model-algebra/documents/{name}`**. Choose the kind, give it a
title, choose the version it is about — or *the model itself — model level* —
and press **Attach**. What is on file is listed below with an
**Accept** and a **Reject** button on each.

**SDK.**

```python
doc = dev.attachments.attach(
    "maya://model/credit.pd.smallbiz",
    "sb-pd-mdd.md",
    kind="model_development_document",
    title="SB PD model development document",
    semver="1.0.0",
    note="Section 4 covers the sampling.")

# somebody else accepts it
val = Maya("http://localhost:5006", "a.mehta", "val-pw")
val.attachments.review(doc["id"], accept=True,
                       note="Reproduced the fit on the 2025 sample.")
```

**curl.** Multipart, and **declare the media type**: curl sends
`application/octet-stream` for a `.md` file otherwise, and the register then
honestly records the document as stored but not indexed.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/attachments \
  -F urn=maya://model/credit.pd.smallbiz \
  -F kind=model_development_document \
  -F "title=SB PD model development document" \
  -F semver=1.0.0 \
  -F "note=Section 4 covers the sampling." \
  -F "file=@sb-pd-mdd.md;type=text/markdown"
```

```json
{"id": "01a07374f914272c3465f053d92d", "kind": "model_development_document",
 "subject_type": "model_version", "state": "attached",
 "media_type": "text/markdown", "text_indexed": true,
 "digest": "sha256:10e06a0f13085817cab2255ba8845cffe0460bed124a2074d6e7d10e908bf052",
 "attached_by": "d.raman"}
```

It lands `attached`, not accepted. Somebody else moves it:

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/attachments/01a07374f914272c3465f053d92d/review \
  -H 'Content-Type: application/json' \
  -d '{"accept": true, "note": "Reproduced the fit on the 2025 sample."}'
```

```json
{"state": "accepted", "reviewed_by": "a.mehta",
 "review_note": "Reproduced the fit on the 2025 sample."}
```

Three refusals you will meet:

```json
{"error": "self_review",
 "detail": "admin attached this document and cannot also accept it",
 "remediation": "review must be by somebody other than whoever filed it; a genuine document filed and approved by one person is still not a control"}
```

```json
{"error": "already_attached",
 "detail": "this exact document is already attached as 'Draft'",
 "remediation": "supersede that attachment if this is a replacement, or attach the revised document, which will have a different digest"}
```

```json
{"error": "no_version_to_attach_to",
 "detail": "maya://model/credit.pd.smallbiz has no versions, and a document filed at model level has to say so",
 "remediation": "create a version first, or pass model_level to file this against the model itself"}
```

That last one answers the obvious question: **you can file a document before the
first version exists**, but you have to say `model_level=true`, because the
default is the latest version and there isn't one. Documents are content
addressed, so an edited document is a different document — replacing one is a
`supersedes`, never an edit.

`GET /api/v1/attachments?urn=…` gives the state of the file:

```json
{"attached": 2, "accepted": 1, "awaiting_review": 1, "rejected": 0,
 "kinds_present": ["model_development_document"], "unindexed": 1,
 "detail": "1 accepted, 1 awaiting review"}
```

More in [documentation](/help/documentation); the whole lot, zipped for somebody
without a login, is [the model package](/tutorials/model-package).

---

## 5 · A second version

Creating one is the same act as §2 with a new semver — **Create version** on
`/model-algebra/version/{name}`, `maya.versions.create(urn, semver="1.1.0", …)`,
or `POST /api/v1/models/{name}/versions`. What is different is what you are
allowed to change: nothing in an existing version, ever. The kernel, both
schemas, the contract and the artifact digest are fixed at creation, which is
what makes `manifest_digest` worth computing and lets a warrant name a version
and still mean it in a year.

Two rules, and both refuse rather than overwrite.

**A semver is used once.**

```json
{"error": "registry_refused",
 "detail": "version 1.0.0 already exists for maya://model/credit.pd.smallbiz; versions are immutable"}
```

**The record has to be open.** A new version *is* a change to the model, so it is
only accepted while the record is `draft`, `baselined` or `amending`. Submitting
for approval already closes it:

```json
{"error": "registry_refused",
 "detail": "cannot add a version to maya://model/credit.pd.smallbiz: this model is 'submitted' (submitted for approval; frozen while it is being considered) and is frozen"}
```

And once attested:

```json
{"error": "registry_refused",
 "detail": "cannot add a version to maya://model/credit.pd.smallbiz: this model is attested and therefore immutable; open an amendment to change it"}
```

The same refusal covers editing the record's fields. The way out is an amendment,
which is the only one, and it leaves a reason behind:

```python
owner.lifecycle.amend("maya://model/credit.pd.smallbiz",
                      reason="recalibrated on the 2026 sample",
                      scope=["versions"])
# state -> "amending", and versions are accepted again
```

```bash
curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/amend \
  -H 'Content-Type: application/json' \
  -d '{"reason": "recalibrated on the 2026 sample", "scope": ["versions"]}'
```

**On screen** this is **`/model-algebra/lifecycle/{name}`**: the state you are
in, the legal moves out of it, and which of them your roles carry. Approval and
attestation are covered in
[approval and attestation](/help/approval-and-attestation).

---

## 6 · When one version may replace another

Consumers bind to an **alias** — `prod/champion` — never to a semver. Moving one
is not a judgement call: two obligations discharge first, or the move is refused
naming the clause.

* **L-7, refinement.** The replacement's contract assumes no more and guarantees
  no less.
* **L-12, variance.** Inputs are contravariant, outputs covariant, so code
  written against the old version still type-checks against the new one.

**On screen.** **`/model-algebra/refinement/{name}`** puts both halves on one
page: *Ask the question* on the left, *Move an alias* on the right, and the two
contracts side by side underneath.

Ask first — it writes nothing:

```bash
curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/model-algebra/substitution \
  -H 'Content-Type: application/json' \
  -d '{"urn": "maya://model/credit.pd.smallbiz",
       "incumbent": "1.0.0", "replacement": "1.1.0"}'
```

```json
{"incumbent": "maya://model/credit.pd.smallbiz@1.0.0",
 "replacement": "maya://model/credit.pd.smallbiz@1.1.0",
 "refinement": {"holds": true, "reason": "refines"},
 "variance": {"ok": true, "reason": "compatible"},
 "ok": 1,
 "detail": "the replacement may stand in for the incumbent. This is the proof an alias move discharges, so a move to this version would be judged on exactly this"}
```

Then move it. The version must be approved first — an alias never points at a
draft.

```python
mrm = Maya("http://localhost:5006", "s.iqbal", "mrm-pw")
mrm.versions.promote("maya://model/credit.pd.smallbiz", semver="1.1.0",
                     environment="prod", alias="champion",
                     justification="gini 0.42 -> 0.46 on the 2025 sample")
```

```bash
curl -u s.iqbal:mrm-pw -X PUT \
  localhost:5006/api/v1/models/credit.pd.smallbiz/aliases \
  -H 'Content-Type: application/json' \
  -d '{"semver": "1.1.0", "environment": "prod", "alias": "champion",
       "justification": "gini 0.42 -> 0.46 on the 2025 sample"}'
```

```json
{"model": "maya://model/credit.pd.smallbiz", "environment": "prod",
 "alias": "champion", "version": "1.1.0",
 "refinement": {"holds": true, "reason": "refines"},
 "variance": {"ok": true, "reason": "compatible"}}
```

A version that scores better but tightened its assumptions and dropped an input
is refused, and the refusal names both failures:

```json
{"error": "registry_refused",
 "detail": "alias move refused: assumptions not weakened: dscr / inputs no longer accepted: years_trading"}
```

That is not a bug in the new model. It is a statement that it is a different
model from the consumer's point of view — register it as one, and record where it
came from with the edge below.

---

## 7 · Composition and inheritance

Five relations, and MAYA moves no data across any of them — an edge is a
statement about two entries in the register, over a wire somebody else's engine
carries. Two of them do the work everybody means.

| Relation | Means | Propagates? |
|---|---|---|
| `derives_from` | built **from** it: a variant, a recalibration for another book, a copy that grew up | no |
| `input_to` | its **output is read as an input** by that model | **yes**, and it is type-checked |
| `challenger_of` | built to argue with it — deliberately *not* a dependency | no |
| `benchmark_for` | a reference point to judge it against | no |
| `calibrated_by` | its parameters are solved by that model | yes, but does not compose |

`GET /api/v1/model-relations` publishes this list with its meanings; `feeds` is
still accepted on the way in and stored as `input_to`.

**Inheritance is `derives_from`.** It records lineage and nothing propagates
along it. The derived model is its own model with its own versions and its own
approvals — MAYA has no notion of one model inheriting another's approvals, and
does not pretend to.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/model-relations \
  -H 'Content-Type: application/json' \
  -d '{"from_urn": "maya://model/credit.pd.smallbiz.challenger",
       "to_urn": "maya://model/credit.pd.smallbiz",
       "kind": "derives_from",
       "note": "started as a copy of the scorecard specification"}'
```

**Composition is `input_to`**, and it is checked. Two things are required, and
only two: the source supplies **at least one** field the target reads, and every
field they **share** type-checks. What the target reads from elsewhere is
somebody else's edge, or the caller's to supply.

**On screen.** **`/model-algebra/composition`** — *Propose an edge*, then
*The composite, computed* and *Blast radius* underneath.

```python
owner.models.relate(from_urn="maya://model/credit.pd.smallbiz",
                    to_urn="maya://model/credit.ecl.smallbiz",
                    kind="input_to",
                    note="the 12-month PD term in the stage-1 provision")
```

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/model-relations \
  -H 'Content-Type: application/json' \
  -d '{"from_urn": "maya://model/credit.pd.smallbiz",
       "to_urn": "maya://model/credit.ecl.smallbiz",
       "kind": "input_to",
       "note": "the 12-month PD term in the stage-1 provision"}'
```

The ECL stack also reads LGD, EAD and a discount factor. That is fine, and the
composite says exactly what is still missing:

```bash
curl -u d.raman:dev-pw -G localhost:5006/api/v1/model-algebra/composite \
  --data-urlencode "from_urn=maya://model/credit.pd.smallbiz" \
  --data-urlencode "to_urn=maya://model/credit.ecl.smallbiz"
```

```json
{"composite": "maya://model/credit.ecl.smallbiz ∘ maya://model/credit.pd.smallbiz",
 "input_schema": [{"name": "dscr", ...}, {"name": "years_trading", ...},
                  {"name": "lgd", ...}, {"name": "ead", ...},
                  {"name": "discount_factor", ...}],
 "output_schema": [{"name": "ecl_lifetime", "dtype": "float", "minimum": 0}],
 "supplied_by_the_edge": ["pd_12m"],
 "still_supplied_by_the_caller": ["lgd", "ead", "discount_factor"],
 "detail": "the source's inputs, plus everything the target reads that this edge does not carry — those are what somebody must still provide for the pair to run"}
```

The composite's type is **derived**, never declared, which is the whole point of
typing the edge.

Two refusals, each of them somebody believing a wire exists that does not. A
source that supplies nothing the target reads:

```json
{"detail": "maya://model/credit.pd.smallbiz does not compose with maya://model/credit.lgd.smallbiz: it produces pd_12m and maya://model/credit.lgd.smallbiz reads collateral_value, so this edge carries nothing. An `input_to` edge asserts that an output arrives where an input is read; one that supplies no field the target reads is a wire to nowhere, and the blast radius would follow it"}
```

And a shared field whose types do not line up:

```json
{"detail": "maya://model/credit.pd.smallbiz does not compose with maya://model/credit.report.pdgrade: on the 1 field(s) they share, what it produces accepts less than before at pd_12m. A wire that arrives carrying the wrong type is worse than no wire, because everything downstream believes it"}
```

An edge to itself, and an edge that closes a cycle, are refused the same way —
`a model whose output is its own input has no defined value, and a blast radius
over it does not terminate`.

> **Draw the edge after the versions exist.** The check runs against the latest
> version at each end, and where either end has none it is **skipped silently** —
> the edge is recorded on trust. `GET /model-algebra/composite` will then tell
> you `a composite has no schema until both ends have a version`, which is the
> only sign you get.

What a change reaches is then computed rather than remembered, and only
propagating edges are followed — so a challenger never inflates the answer:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/blast-radius \
  -H 'Content-Type: application/json' \
  -d '{"urn": "maya://model/credit.pd.smallbiz"}'
```

```json
{"count": 1,
 "reaches": [{"urn": "maya://model/credit.ecl.smallbiz", "distance": 1}],
 "detail": "a change here reaches 1 model(s). that is what the change process has to cover, and it is computed from the graph rather than remembered"}
```

Removing an edge needs a reason — `POST /api/v1/model-relations/remove` — and
without one:

```json
{"detail": "removing a relation needs a reason: an edge that disappears without one is a dependency somebody stopped believing in and nobody can ask about"}
```

---

## What you have, and what is next

A registered model, a tiered record, an immutable first version whose class was
derived, documents filed and accepted by somebody else, a second version behind
an alias that had to prove itself, and the edges that say what this model rests
on and what rests on it.

- [Features](/tutorials/features) — the governed signals a model reads
- [Featuresets](/tutorials/featuresets) — binding those signals to a model's `X`
- [Warrants and training](/tutorials/warrants-and-training) — fitting `P`, and
  where a parameter set goes
- [The model package](/tutorials/model-package) — all of it, zipped, for a reader
  without a login
- [End to end](/tutorials/end-to-end) — the whole path in one pass

Reference: [registering a model](/help/registering-a-model),
[risk tiering](/help/risk-tiering),
[approval and attestation](/help/approval-and-attestation),
[documentation](/help/documentation),
[the API reference](/help/api-reference) and the
[glossary](/help/glossary).

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE.
*Not legal, regulatory or financial advice — see NOTICE §4.*
