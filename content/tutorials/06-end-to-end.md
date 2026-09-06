---
title: One model, end to end
slug: end-to-end
section: Start here
order: 60
icon: signpost-split
summary: One multiple linear regression taken the whole way — registered, defined over features, fitted under a warrant, approved by a second person, promoted, scored, refitted, versioned, documented and packed — as one script whose every response is a real one.
audience: Everyone
---

# One model, end to end

The other five tutorials each take one subsystem and explain it properly. This
one takes one model and never stops. A small-business card-spend regression:
two regressors, sixty borrowers, from an empty register to a number a service
can act on, and then to the pack you would hand a supervisor.

Nothing here is explained twice. Where a step deserves depth, there is a link.

**This one is written SDK-first**, which is the opposite of the others. An
end-to-end walkthrough is at its clearest as one script you can run top to
bottom, and reading it that way shows the *order* — which is most of what this
tutorial has to teach. Every section still says where the same thing lives in
the UI, and there is curl at the end for anyone integrating.

Everything below was run against a real instance. The responses are pasted
as they came back.

---

## The people

Four accounts, because no one person can walk this path. That is the point of
the path.

| | Does |
|---|---|
| `j.okafor` — model owner | registers the model, issues warrants |
| `d.raman` — model developer | defines features, creates versions, runs the fit |
| `a.mehta` — validator | signs the version approval |
| `s.iqbal` — model risk manager | signs the version approval, approves the numbers |

One client each:

```python
from maya_sdk import Maya, Refused

BASE = "https://maya.internal"
owner = Maya(BASE, "j.okafor", "…")
dev   = Maya(BASE, "d.raman",  "…")
val   = Maya(BASE, "a.mehta",  "…")
mrm   = Maya(BASE, "s.iqbal",  "…")

URN = "maya://model/credit.spend.smallbiz"
```

One client each and not one client with four passwords, because several steps
below are refused when the same principal performs both halves. The SDK holds
no opinion about any of that — it carries the request and raises the refusal.

*In the UI: sign in at `/login`; `/dashboard` is the estate.*

---

## 1. The model, and the version that runs

A **model** is a record with an owner and a purpose. A **version** is the
immutable kernel. They are registered separately because they change on
different clocks.

```python
owner.models.register(
    urn=URN, name="Small-business card spend",
    model_class="credit.spend.linear", domain="credit",
    owner="person/j.okafor", legal_entity="LE-UK-01",
    purpose="expected 12-month card spend at renewal")
```

```json
{ "urn": "maya://model/credit.spend.smallbiz", "status": "draft",
  "tier": null, "created_by": "j.okafor",
  "id": "01a0737d239f290afda3ad80dfbd" }
```

Now the kernel. `turnover` is trailing twelve-month turnover in thousands,
`tenure_years` is how long the business has banked with us, `annual_spend` is
what we are predicting. The `contract` is the operating boundary: what the
model assumes about its inputs, and what it promises when those hold.

```python
KERNEL = {
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "runtime": "estimator",
    "entry": {"family": "ols", "target": "annual_spend",
              "regressors": ["turnover", "tenure_years"]},
    "input_schema": [{"name": "turnover", "dtype": "numeric"},
                     {"name": "tenure_years", "dtype": "numeric"}],
    "output_schema": [{"name": "annual_spend", "dtype": "numeric"}],
}
CONTRACT = {
    "assumptions": [{"key": "turnover", "minimum": 50, "maximum": 2000},
                    {"key": "tenure_years", "minimum": 0, "maximum": 60}],
    "guarantees": [{"key": "annual_spend", "minimum": 0}],
    "on_boundary_violation": "reject",
}

dev.versions.create(URN, semver="1.0.0", kernel=KERNEL, contract=CONTRACT)
```

```json
{ "semver": "1.0.0",
  "manifest_digest": "sha256:35afb256c657befa8a1a3a0f492d7be3…",
  "trainability_class": "T2",
  "parameter_kind": "estimated_coefficients",
  "fit_procedure": "estimate",
  "deterministic": true,
  "status": "draft" }
```

**Nobody typed T2.** The trainability class is *derived* from how the parameter
object is inhabited — coefficients, obtained by estimation. It is not a label
you choose; it is a consequence of what you declared, and it decides for the
rest of this tutorial which questions the platform will ask you.

Then the tier, which is also derived — from exposure and purpose, not from an
opinion:

```python
owner.models.assess(URN, exposure=2.0e9, purpose_class="regulatory_capital")
```

```json
{ "tier": 2, "materiality": "material", "complexity": "simple",
  "required_controls": ["independent_validation", "biennial_review",
                        "quarterly_monitoring", "delegated_approval",
                        "full_documentation"],
  "rationale": "materiality=material (exposure 2,000,000,000 in band 'material',
    purpose 'regulatory_capital'); complexity=simple (class T2);
    tau(material,simple)=Tier 2 under ruleset 2026.09.1" }
```

Tier 2 is why the version needs two signatures in §5. Assess before you approve,
or you are choosing your own control depth.

More on kernels, contracts and what a version may declare:
[Defining a model](/tutorials/defining-a-model).

*In the UI: `/models/new`, then the model page at
`/model/credit.spend.smallbiz`.*

---

## 2. The features it reads

A feature is an object with an owner, a definition and a lineage — not a column
in whatever table the data happened to land in.

```python
for name, desc in [
        ("turnover",     "Trailing twelve-month turnover, GBP thousands"),
        ("tenure_years", "Years the business has banked with us"),
        ("annual_spend", "Card spend over the following twelve months, GBP")]:
    dev.features.define(name=name, entity="borrower_id", dtype="numeric",
                        description=desc, owner="person/d.raman",
                        source_system="core_banking")
```

Values live in a **view**. One upload is one view version, and every later
reference is to the version rather than to the path.

```python
dev.features.create_view(
    name="sb_spend", entity="borrower_id", owner="person/d.raman",
    features=["turnover", "tenure_years", "annual_spend"],
    description="Small-business turnover, tenure and realised spend")

dev.features.load("sb_spend", "examples/data/sb_spend_2025h1.csv")
```

The file must carry both clocks. `event_ts` is when the fact was true;
`ingest_ts` is when we learned it. A file with one clock is refused here rather
than accepted and regretted later.

The file is in the repository — `examples/data/sb_spend_2025h1.csv` — so this
page is a script you can run rather than a shape to reproduce. Its first lines
and its last:

```
entity_id,event_ts,ingest_ts,turnover,tenure_years,annual_spend
B00,1751241600.0,1752537600.0,80.0,1.0,3750.0
B01,1751241600.0,1752537600.0,85.0,2.0,5590.0
B02,1751241600.0,1752537600.0,90.0,3.0,6195.0
…
B07,1751241600.0,1772323200.0,61.0,8.0,10455.0
```

That last line matters. It is the *same* period for borrower B07 — same
`event_ts` — restated on 1 March 2026 after an audit knocked its turnover down
from 115 to 61. Sixty-one rows for sixty borrowers.

```json
{ "version": 1, "delta_version": 0, "row_count": 61,
  "valid_time_column": "event_ts", "ingest_time_column": "ingest_ts",
  "quality_report": {"turnover": {"null_rate": 0.0, "distinct": 61}, …},
  "detail": "61 rows materialised as sb_spend v1" }
```

Definitions, derived features, lineage and sensitivity:
[Features](/tutorials/features).

*In the UI: `/features/new`, `/features/load`, and `/feature-views/sb_spend`.*

---

## 3. The featureset

A featureset is the *presentation of X* the model is defined over: named slots,
a label, and an outcome window. Declaring the schema and filling it are two
acts, because the schema is what a version is checked against and the fill is
what a fit reads.

```python
dev.featuresets.define(
    name="sb_spend_v1", entity="borrower_id",
    slots={"turnover": "numeric", "tenure_years": "numeric",
           "annual_spend": "numeric"},
    label_slot="annual_spend", outcome_window_days=365,
    grain="one row per borrower per half-year",
    description="What the spend model reads")

dev.featuresets.fill("sb_spend_v1", bindings={
    "turnover": "turnover", "tenure_years": "tenure_years",
    "annual_spend": "annual_spend"}, note="first pin")
```

Each binding comes back pinned to an exact namespace and Delta version, which
is what makes a filled version resolve to the same bytes forever:

```json
{ "version": 1,
  "bindings": {
    "turnover": {"feature": "turnover", "view": "sb_spend", "view_version": 1,
                 "namespace": "features/borrower_id/sb_spend/v1",
                 "delta_version": 0, "certification": "experimental"},
    "tenure_years": { … }, "annual_spend": { … } } }
```

The featureset says what **training** reads. What **serving** reads is a
separate declaration, and it is easy to skip:

```python
dev.call("POST", "/feature-contracts", json={
    "model_version_id": dev.versions.list(URN)[0]["id"],
    "items": [{"view": "sb_spend", "version": 1}]})
```

```json
{ "digest": "sha256:5b43c4a23d0c87dfd614d9d704cdd061…",
  "items": [{"view": "sb_spend", "version": 1,
             "namespace": "features/borrower_id/sb_spend/v1"}] }
```

Skip it and there is nothing to compare production reads against, and the
compiled documentation reports the gap. Do it, and §12's *Data and features*
section fills itself from this one call.

Composition, sealing, and the operations that build one set from others:
[Featuresets](/tutorials/featuresets).

*In the UI: `/featuresets/author`, then `/featureset/sb_spend_v1/bind`.*

---

## 4. The two clocks

Before assembling anything, ask the view what it would read. This is free, it
writes nothing, and it is the step people skip.

```python
dev.call("POST", "/feature-views/sb_spend/versions/1/as-of",
         json={"label_ts": AS_OF, "as_of": AS_OF, "entity_id": "B07"})
```

with `AS_OF = 1767571200.0` — 5 January 2026, before the restatement landed:

```json
{ "entities": [{ "entity_id": "B07",
    "candidates": [
      {"event_ts": 1751241600.0, "ingest_ts": 1752537600.0, "admissible": 1,
       "detail": "true by the decision moment and known by it — the latest such
                  row is the one that is read"},
      {"event_ts": 1751241600.0, "ingest_ts": 1772323200.0, "admissible": 0,
       "refused_by_event_clock": 0, "refused_by_ingest_clock": 1,
       "detail": "refused: it was not yet known at min(label_ts, as_of) — the
                  platform learned it later than the decision"}],
    "read": {"turnover": 115.0, "tenure_years": 8.0, "annual_spend": 10455.0} }],
  "operator": "AsOf(R, l, a) = argmax over (event_ts, ingest_ts) of
               { r in R : r.event_ts <= l and r.ingest_ts <= min(l, a) }" }
```

Ask the same question with an `as_of` after 1 March and the second row becomes
admissible and `turnover` reads `61.0`. Same view, same version, two answers,
both correct — which is exactly why the training set names its `as_of` rather
than reading "now".

```python
snapshot = dev.featuresets.training_set(
    "sb_spend_v1", version=1,
    spine=[{"entity_id": f"B{i:02d}", "label_ts": AS_OF} for i in range(60)],
    as_of=AS_OF, snapshot_name="sb_spend_2026_01")
```

```json
{ "name": "sb_spend_2026_01", "row_count": 60, "as_of": 1767571200.0,
  "delta_table": "snapshots/sb_spend_2026_01", "delta_version": 0,
  "pit_verified": true,
  "pit_report": {"passed": true, "layer": "sampled", "checked": 60,
                 "violations": [], "leakage": [],
                 "detail": "60 of 60 rows independently recomputed"},
  "featureset": "sb_spend_v1", "featureset_version": 1,
  "digest": "sha256:0077639fd237c8043cd6ce32578558a3…",
  "id": "01a0737d2531521f8980a271f891" }
```

Sixty-one rows in, sixty out, every one independently recomputed. The snapshot
is pinned at a Delta version, so this fit is reproducible after the next
restatement and after the one after that.

---

## 5. Approving the kernel

Here is the part of the order that surprises people. **The version is approved
before it is fitted.** MAYA will not resolve a warrant against a draft:

```
restricted: version 1.0.0 is 'draft'
  → an approved version is required in this environment
```

Two refusals guard this, and at *this* point in the walkthrough you will meet
the first rather than the second, because the alias does not exist yet:

```
not_found: nothing bound for maya://model/credit.spend.smallbiz#champion in prod
  → point the alias at an approved version
```

They are ordered that way deliberately. *Nothing is bound* is a question about
the environment; *the version is a draft* is a question about the version, and
answering the second before the first would describe a version nobody had asked
to run.

That is not an accident of sequencing. Approving a version approves a *shape* —
these regressors, these types, this operating boundary — and a shape can be
reviewed before any numbers exist. The numbers get their own approval, from a
different person, in §8. Two approvals, because they are two different
questions.

Tier 2 means a quorum:

```python
mrm.call("GET", "/version-approvals", params={"urn": URN, "semver": "1.0.0"})
```

```json
{ "tier": 2, "quorum_required": true,
  "required_roles": ["model_risk_manager", "validator"],
  "status": "draft", "open_approval": null,
  "detail": "a tier 2 version needs 2 signatures: model_risk_manager, validator" }
```

```python
approval = mrm.versions.open_quorum(urn=URN, semver="1.0.0")
mrm.versions.sign_quorum(approval["id"], role="model_risk_manager",
                         note="tier 2, shape reviewed")
val.versions.sign_quorum(approval["id"], role="validator",
                         note="regressors and schema agree")
```

```json
{ "status": "approved", "tier": 2,
  "signatures": [
    {"role": "model_risk_manager", "principal": "s.iqbal", "decision": "approve"},
    {"role": "validator",          "principal": "a.mehta", "decision": "approve"}],
  "outstanding_roles": [],
  "detail": "approved by 2 signatures: model_risk_manager, validator" }
```

`d.raman` cannot sign — a model developer does not hold `version:sign` — and no
one person can sign twice under two hats. A quorum is a number of people.

*In the UI: `/model-algebra/quorum/credit.spend.smallbiz`.*

---

## 6. Moving the alias

Consumers hold `maya://model/credit.spend.smallbiz#champion`. The alias is what
decides which version that is, and moving it is the most dangerous operation on
this page — so it is a proof obligation rather than a write.

```python
mrm.versions.promote(URN, semver="1.0.0", environment="prod",
                     alias="champion",
                     justification="first version of the spend model")
```

```json
{ "alias": "champion", "version": "1.0.0", "environment": "prod",
  "refinement": {"holds": true, "reason": "no incumbent"},
  "variance":   {"ok": true,    "reason": "no incumbent"} }
```

No incumbent, so nothing to refine. In §11 there is an incumbent and the answer
is different.

The champion now points at an approved kernel with no numbers in it. Nothing
can run yet, and you will see exactly how it refuses in §11.

*In the UI: `/model-algebra/version/credit.spend.smallbiz`.*

---

## 7. The fit warrant

A **grant** says this principal may ask. A **warrant** is one signed, expiring
answer to one asking. Both are needed, and the developer cannot mint their own —
issuing is the owner's act.

```python
owner.warrants.grant(urn=URN, principal="person/d.raman",
                     declared_use="model_development", environment="prod")

owner.warrants.for_fitting(
    urn=URN, principal="person/d.raman",
    featureset="sb_spend_v1", featureset_version=1,
    window={"from": 1704067200.0, "to": 1767139200.0},
    as_of=1767571200.0, environment="prod")
```

```json
{ "maya_warrant": "1.0",
  "warrant_id": "01a0737d25d593846929056ada9d",
  "subject": {"version": "1.0.0", "binding_kind": "alias",
              "trainability_class": "T2",
              "manifest_digest": "sha256:35afb256c657befa8a1a3a0f492d7be3…"},
  "operation": {"verb": "fit", "determinism": "deterministic", "mode": "batch"},
  "parameters": {"kind": "estimated_coefficients",
                 "source": {"binding": "to_be_fitted"}, "digest": null},
  "realisation": {"runtime": "estimator",
                  "entry": {"family": "ols", "target": "annual_spend",
                            "regressors": ["turnover", "tenure_years"]}},
  "data": {"inputs": [{"name": "training_set", "binding": "featureset",
                       "featureset": "sb_spend_v1", "version": 1,
                       "as_of": 1767571200.0,
                       "entity": "borrower_id",
                       "slots": [ … three, each with its view and Delta pin … ],
                       "namespaces": ["features/borrower_id/sb_spend/v1"],
                       "pit_rule": "… ingest_ts <= min(label_ts, as_of)"}]} }
```

The descriptor is self-describing: an engine receiving it knows which columns
it is training on, which view version fills each, and the point-in-time rule —
without a second call. Names and types, never values.

The check that earns this step its place: the featureset must provide what the
kernel declares it reads. Bind one that does not —

```python
owner.warrants.for_fitting(urn=URN, principal="person/d.raman",
                           featureset="sb_partial", featureset_version=1, …)
```

```json
{ "error": "schema_not_satisfied",
  "detail": "'sb_partial' does not provide tenure_years, which this version
             declares it reads",
  "remediation": "bind a featureset whose schema covers the kernel's inputs, or
    create a model version whose input schema matches this set — adding a
    regressor is a model change, not a data change" }
```

Warrant families, verbs and what each carries:
[Warrants and training](/tutorials/warrants-and-training).

*In the UI: `/warrants`.*

---

## 8. The fit, and the second person

MAYA is not a modelling library. It ships a captive estimator so that the
governed path can be walked against real arithmetic; the same path takes
delivery of a fit performed anywhere else.

```python
fitted = dev.parameters.fit(
    urn=URN, snapshot_id=snapshot["id"], principal="person/d.raman",
    window={"from": 1704067200.0, "to": 1767139200.0},
    name="ols_2026_01", environment="prod",
    note="first fit on the 2025 book")
```

The warrant is resolved first and the data read second — authority before data,
because a read performed under an authority that turns out not to exist has
already happened.

```json
{ "id": "01a0737d25f8f2068f109a62cb6d",
  "name": "ols_2026_01", "kind": "coefficients", "provenance": "fitted",
  "values_inline": {"intercept": 1203.1628787878885,
                    "turnover": 30.774999999999924,
                    "tenure_years": 648.8243006993016},
  "diagnostics": {
    "n": 60, "k": 3, "degrees_of_freedom": 57,
    "r_squared": 0.9984335855081763,
    "adjusted_r_squared": 0.9983786235961825,
    "residual_std_error": 154.73059116354145,
    "standard_errors": {"intercept": 62.61876657150656,
                        "turnover": 0.2354150975455509,
                        "tenure_years": 5.905099507110243},
    "t_statistics": {"intercept": 19.21409418714683,
                     "turnover": 130.72653504750355,
                     "tenure_years": 109.87525272318645},
    "condition_number": 764.002966344353,
    "family": "ols", "rows": 60, "snapshot": "sb_spend_2026_01",
    "delta_version": 0, "pit_verified": true},
  "snapshot_id": "01a0737d2531521f8980a271f891",
  "warrant_id": "01a0737d25cd2d3d794ee3329ed4",
  "descriptor_id": "01a0737d25ef1bf2faff8c91ff49",
  "digest": "sha256:d98dc729c72e7ce0…",
  "state": "proposed",
  "created_by": "d.raman" }
```

Spend rises about £31 per £1,000 of turnover and about £638 per year of tenure.
Read the condition number before the R²: 810 says the two regressors are
correlated enough to be worth a sentence in the write-up, and both t-statistics
are large enough that neither coefficient is in doubt.

Note that `warrant_id` is not the fit warrant's id from §7. A resolved
descriptor is minted per request and never stored; the **grant** is what MAYA
persists and can therefore vouch for, so that is what a parameter set records.
The descriptor id is kept alongside it.

**State `proposed`.** It runs on nothing until somebody else says so — and the
person who fitted it is not that somebody:

```python
dev.parameters.review(fitted["id"], accept=True, note="fine")
```

```json
{ "error": "forbidden",
  "detail": "'parameter:approve' is not granted by your roles (model_developer)",
  "remediation": "ask an administrator for a role that carries this permission" }
```

```python
mrm.parameters.review(fitted["id"], accept=True,
                      note="condition number and standard errors reviewed")
```

```json
{ "state": "approved", "approved_by": "s.iqbal",
  "review_note": "condition number and standard errors reviewed",
  "created_by": "d.raman" }
```

A model developer holds `parameter:record` and not `parameter:approve`, so the
refusal here is at the role. Where a principal holds both, the register
refuses the author's own approval separately, as `self_approval`. Either way: a number one person can
both produce and bless is a preference, not an estimate.

**If your fit happens elsewhere**, the shape is the same and the numbers arrive
by delivery rather than by computation:

```python
grant = owner.warrants.grant(urn=URN, principal="person/d.raman",
                             declared_use="model_development",
                             environment="prod")

dev.parameters.record(
    urn=URN, semver="1.0.0", name="ols_statsmodels", kind="coefficients",
    values={"intercept": 1220.36, "turnover": 30.9557,
            "tenure_years": 637.8823},
    warrant_id=grant["id"],                     # ← the GRANT id, as above
    featureset="sb_spend_v1", featureset_version=1,
    window=WINDOW, as_of=AS_OF, snapshot_id=snapshot["id"],
    diagnostics={"r_squared": 0.98742, "condition_number": 810.68, "n": 60},
    note="fitted with statsmodels in the lab notebook")
```

It lands `proposed` and needs the same second person. Pass anything but a
grant MAYA issued and you get `unknown_warrant: MAYA did not issue warrant …`;
without one, *which data produced these numbers* has no answer. And send the
diagnostics: a set delivered without them asks somebody to approve a number on
trust.

*In the UI: `/parameters/1.0.0/credit.spend.smallbiz`.*

---

## 9. Scoring

A separate grant for the consumer, addressed by alias, with its own declared
use:

```python
owner.warrants.grant(urn=f"{URN}#champion", principal="svc/renewals",
                     declared_use="renewal_limit_decision", environment="prod")

warrant = owner.warrants.resolve(
    urn=f"{URN}#champion", principal="svc/renewals",
    declared_use="renewal_limit_decision", environment="prod")
```

```json
{ "subject": {"urn": "maya://model/credit.spend.smallbiz#champion",
              "version": "1.0.0", "binding_kind": "alias",
              "trainability_class": "T2"},
  "operation": {"verb": "score", "determinism": "deterministic"},
  "parameters": {"kind": "estimated_coefficients",
                 "source": {"binding": "parameter_set",
                            "parameter_set": "01a0737d25f8f2068f109a62cb6d",
                            "name": "ols_2026_01", "version": 1,
                            "digest": "sha256:d98dc729c72e7ce083943351493d59dd…",
                            "as_of": 1767571200.0}},
  "constraints": {"operating_boundary": {"assumptions": [
      {"key": "turnover", "minimum": 50, "maximum": 2000},
      {"key": "tenure_years", "minimum": 0, "maximum": 60}]},
    "on_boundary_violation": "reject", "resources": {"max_seconds": 30}},
  "signature": {"alg": "HMAC-SHA256", "key_id": "k-f0da581c64135cb6",
                "value": "500e4688c2bad4ec1a1b8647ff284034…"} }
```

The warrant names the exact point of `P` it is to run at, by id and by digest.
That is the whole difference between "the model" and "the model, running on
these numbers".

Address it by alias — `#champion` — or by `@1.0.0`, which pins one version and
resolves. Both work; they say different things. An alias is a promise that
whatever it points at has been through the register, and it moves when a
challenger wins; a version qualifier is a consumer refusing to be moved. Hold
the alias unless you have a reason to be pinned, because a pinned consumer is
one nobody can promote without finding them first.

```python
owner.warrants.execute(
    urn=f"{URN}#champion", principal="svc/renewals",
    declared_use="renewal_limit_decision", environment="prod",
    inputs={"features": {"turnover": 240.0, "tenure_years": 6.0}})
```

```json
{ "descriptor_id": "01a0737d261ea6da143959bba1a6",
  "model_urn": "maya://model/credit.spend.smallbiz",
  "version": "1.0.0",
  "prediction": {"family": "ols", "prediction": 12477.010258682109,
                 "target": "annual_spend"},
  "boundary_ok": true, "boundary_violations": [], "latency_ms": 1.901 }
```

£12,477 for a business turning over £240k with six years of tenure. Check it
against the coefficients above if you like; it is the arithmetic and nothing
else.

Try it outside the boundary. A `turnover` of 9000, against a declared maximum
of 2000, is refused whether you nest it under `features` or put it at the top
level:

```
boundary_violation: inputs outside the operating boundary: turnover
```

That used to be true of the top-level form only. The estimator reads its record
from `inputs["features"]`, and the check looked at the top level alone — so a
signed operating boundary was unenforced for every runtime that nests its
inputs, silently, with `"boundary_ok": true` on the response. It reads one level
down as well now.

> If you run models in your own engine, read the boundary out of
> `constraints.operating_boundary` and apply it yourself. The warrant contract
> expects that of you regardless of what the captive engine does, and a boundary
> enforced only by the engine MAYA happens to ship is not a boundary.

*In the UI: `/warrants` shows the grants; `/telemetry/1.0.0/credit.spend.smallbiz`
shows what actually ran.*

---

## 10. Refitting is not a new version

Next quarter, on data that now includes B07's restatement:

```python
refit_snapshot = dev.featuresets.training_set(
    "sb_spend_v1", version=1,
    spine=[{"entity_id": f"B{i:02d}", "label_ts": LATER} for i in range(60)],
    as_of=LATER, snapshot_name="sb_spend_2026_04")     # LATER = 31 Mar 2026

dev.parameters.fit(urn=URN, snapshot_id=refit_snapshot["id"],
                   principal="person/d.raman", window=WINDOW,
                   name="ols_2026_04", environment="prod",
                   note="quarterly refit; B07's turnover was restated in March")
```

```json
{ "name": "ols_2026_04", "state": "proposed",
  "model_version_id": "01a0737d23d51759066ba6a5c503",
  "values_inline": {"intercept": 1331.9415164193629,
                    "turnover": 30.27825565718268,
                    "tenure_years": 652.2692271470183},
  "diagnostics": {"r_squared": 0.9804121386731571, "n": 60,
                  "condition_number": 804.3493821808597,
                  "snapshot": "sb_spend_2026_04", "pit_verified": true} }
```

Same `model_version_id`. The kernel did not change, so no new version — the
refit is a new point of `P` and nothing more. That is what lets a recalibration
be approved as a procedure instead of pretending a committee meets every
quarter.

And the champion does not move until somebody approves the new numbers:

```python
dev.call("GET", "/parameters", params={"urn": URN, "semver": "1.0.0"})
```

```json
{ "model_version": "maya://model/credit.spend.smallbiz@1.0.0",
  "recorded": 2, "approved": 1, "awaiting_approval": 1, "ready": true,
  "detail": "running on 'ols_2026_01' v1, fitted" }
```

---

## 11. A second version

Adding a regressor *is* a model change. The refusal in §7 said so; here is the
other half of it.

```python
KERNEL_2 = {**KERNEL,
            "entry": {"family": "ols", "target": "annual_spend",
                      "regressors": ["turnover", "tenure_years",
                                     "sector_index"]},
            "input_schema": KERNEL["input_schema"]
                            + [{"name": "sector_index", "dtype": "numeric"}]}

dev.versions.create(URN, semver="1.1.0", kernel=KERNEL_2)
```

```json
{ "semver": "1.1.0", "trainability_class": "T2", "status": "draft",
  "manifest_digest": "sha256:faba4fe2dc488aa9b8e08bfefe658737…" }
```

Through the same quorum as §5, then put in beside the champion rather than
over it:

```python
a2 = mrm.versions.open_quorum(urn=URN, semver="1.1.0")
mrm.versions.sign_quorum(a2["id"], role="model_risk_manager")
val.versions.sign_quorum(a2["id"], role="validator")

mrm.versions.promote(URN, semver="1.1.0", environment="prod",
                     alias="challenger",
                     justification="adds a sector index; runs beside the champion")
```

Two things now happen that are worth more than the rest of this section.

**An approved version is not a runnable model.**

```python
owner.warrants.grant(urn=f"{URN}#challenger", principal="svc/renewals",
                     declared_use="renewal_limit_decision", environment="prod")
owner.warrants.execute(urn=f"{URN}#challenger", principal="svc/renewals",
                       declared_use="renewal_limit_decision",
                       environment="prod",
                       inputs={"features": {"turnover": 240.0,
                                            "tenure_years": 6.0,
                                            "sector_index": 1.1}})
```

```json
{ "error": "no_approved_parameters",
  "detail": "this version's parameter object is 'estimated_coefficients' and
             nothing inhabits it: no approved parameter set, and no artifact to
             carry one",
  "remediation": "record a parameter set and have somebody other than its author
    approve it, or register the version against an artifact" }
```

1.1.0 needs its own featureset, its own fit warrant, its own fit and its own
second person — §3 through §8 again. Fail-closed, with a name.

**And the move does not come back.**

```python
mrm.versions.promote(URN, semver="1.0.0", environment="prod",
                     alias="challenger", justification="second thoughts")
```

```json
{ "error": "registry_refused",
  "detail": "alias move refused: refines / inputs no longer accepted: sector_index" }
```

Callers that started sending `sector_index` would break. Input schemas are
contravariant; a replacement must accept everything the incumbent accepted. So
**fit and approve before you promote**, because promotion is a door that only
opens one way.

The champion, meanwhile, is untouched and still returns 12477.010258682109.

### What an attested record refuses

Attestation is the record's own approval — the statement that this is what the
model *is*. Once given, the record is immutable.

```python
owner.lifecycle.submit(URN, note="1.0.0 in production, 1.1.0 in challenge")
mrm.lifecycle.approve(URN, note="tier 2 controls in place")
owner.lifecycle.attest(URN, role="model_owner")
mrm.lifecycle.attest(URN, role="model_risk_manager")
```

```json
{ "state": "attested",
  "meaning": "in force and immutable; open an amendment to change it",
  "mutable": false,
  "available_transitions": [
    {"name": "amend", "to": "amending", "permission": "model:amend"},
    {"name": "retire", "to": "retired", "permission": "model:retire"}],
  "attested_at": 1788643977.2,
  "attestation_expires_at": 1820179977.2 }
```

```python
dev.versions.create(URN, semver="1.2.0", kernel=KERNEL)
```

```json
{ "error": "registry_refused",
  "detail": "cannot add a version to maya://model/credit.spend.smallbiz: this
             model is attested and therefore immutable; open an amendment to
             change it" }
```

Not obstruction — it is what makes the attestation worth anything. The way
through is to say so out loud:

```python
owner.lifecycle.amend(URN, reason="add a sector index to the champion")
```

```json
{ "status": "amending", "tier": 2, "created_by": "j.okafor",
  "id": "01a0737d239f290afda3ad80dfbd" }
```

The record is changeable again, the amendment is on the file, and the version
you create next has a reason attached to it. Note also that everything you
compile from here on says `Record state: **amending**` — which is true, and
which a reader should see.

*In the UI: `/model-algebra/lifecycle/credit.spend.smallbiz`.*

---

## 12. Documentation

Documents are *compiled* from the register and the evidence graph. Nobody
writes them, and a section the evidence cannot support comes back as a named
gap rather than an empty heading.

```python
owner.documents.kinds()
```

```json
{ "kinds": [
  {"kind": "model_development_document", "title": "Model Development Document"},
  {"kind": "validation_report",          "title": "Validation Report"},
  {"kind": "model_card",                 "title": "Model Card"},
  {"kind": "annex_iv", "title": "EU AI Act — Annex IV Technical Documentation"}] }
```

```python
doc = owner.documents.compile(URN, kind="model_development_document")
print(owner.documents.markdown(doc["id"]))
```

The section that exists because of the feature contract in §3 —

```markdown
## Data and features

The version is pinned to exact feature view versions. Serving reads these
namespaces and no others; publishing a later view version does not move what
this model is served.

| Feature view | Pinned version | Serving namespace |
|---|---|---|
| `sb_spend` | v1 | `features/borrower_id/sb_spend/v1` |

Contract digest: `sha256:5b43c4a23d0c87dfd614d9d70…`
```

— the classification and tier sections carrying their own derivations —

```markdown
| Trainability class | **T2** |
| Parameter kind | `estimated_coefficients` |

The class is **derived** from how the parameter object is inhabited
(`estimated_coefficients` obtained by `estimate`), not declared.

**Derivation.** materiality=material (exposure 2,000,000,000 in band
'material', purpose 'regulatory_capital'); complexity=simple (class T2);
tau(material,simple)=Tier 2 under ruleset 2026.09.1
```

— and the sections nothing supports say so plainly:

```markdown
## Validation

**This section is required and could not be filled.**

Nothing in the register supports a `validation` section for this model yet.
That is a statement about the model's evidence, not about this document.
```

Which is correct: we never opened a validation episode. Independent challenge is
a separate act by a separate person and this tutorial did not perform one.

### The training record

Every other document is about a model or a version. This one is about a single
fit — the moment that used to have no document at all.

```python
record = owner.documents.training_record(fitted["id"])
print(owner.documents.markdown(record["id"]))
```

```markdown
# Training Record — ols_2026_01

## Under what authority
Fitted under warrant `01a0737d25cd2d3d794ee3329ed4`.

## What it read
Featureset **sb_spend_v1 @ v1** — the *version*, pinned.
Window `1704067200.0` → `1767139200.0`, as of `1767571200.0`.
Assembled from snapshot `01a0737d2531521f8980a271f891`, read at its pinned
Delta version rather than at the head.

## What it produced
| `intercept` | 1220.3600769425334 |
| `turnover` | 30.955652521929828 |
| `tenure_years` | 637.8822627460695 |

## Who accepted it
Accepted by **s.iqbal** — condition number and standard errors reviewed
Not by whoever recorded it (`d.raman`).
```

Every other document here is about something that changes rarely. This one is
about the act that happens every quarter, or every day — the one that used to
leave no readable trace at all.

*In the UI: `/model-algebra/documents/credit.spend.smallbiz`, and
`/dossier/credit.spend.smallbiz` for the graph.*

---

## 13. The pack

For somebody who will not be given a login: a supervisor, an internal auditor,
an acquirer's diligence team. Self-contained, every member digested, cut against
a named evidence chain head.

```python
owner.packages.manifest(URN)                              # without the bytes
owner.packages.cut(URN, "credit.spend.smallbiz.zip")      # with them
```

```json
{ "pack_version": "1.0", "urn": "maya://model/credit.spend.smallbiz",
  "model": {"name": "Small-business card spend", "tier": 2,
            "status": "amending", "legal_entity": "LE-UK-01"},
  "built_by": "j.okafor",
  "chain": {"head_seq": 54,
            "head_hash": "sha256:8211aa714d4bb7219f6af1864756fcb3…",
            "verified": true},
  "content_digest": "sha256:11c38962a6a86d99082fd1e615bdb402…",
  "files": [ … each with its own digest … ] }
```

```
README.md              documents/annex_iv.{json,md}
manifest.json          documents/model_card.{json,md}
model.json             documents/model_development_document.{json,md}
versions.json          documents/validation_report.{json,md}
warrants.json          documentation/dossier.json
findings.json          evidence/chain.json
validations.json       attachments/index.json
monitoring.json        gaps.md
overlays.json
```

Compare `content_digest` against the last pack to answer *has anything changed*
without moving the bytes to find out that nothing has.

**Read `gaps.md` first.**

```markdown
| What | Why |
|---|---|
| `documentation/model Small-business card spend` | nothing is filed here;
  expected the methodology, and the literature the approach comes from |
| `documentation/featureset_version sb_spend_v1 @ v1` | nothing is filed here;
  expected the data dictionary, and the source-system agreement |
| `documentation/parameter_set parameters ols_2026_04` | nothing is filed here;
  expected the training record, and any note explaining this fit |
```

Three honest absences from a model built in one sitting: no methodology note,
no data dictionary, and no training record for the *refit* — which is right,
because we never approved it. A pack that quietly left these out would look
complete, and looking complete is the failure this file exists to prevent.

What a pack holds and how to verify one:
[The model package](/tutorials/model-package).

*In the UI: `/packages/credit.spend.smallbiz`, with a preview before you cut.*

---

## For anyone integrating

Every SDK method above is one HTTP call under `/api/v1`, Basic-authenticated,
JSON in and JSON out. The two shapes:

```bash
curl -u j.okafor:… -X POST https://maya.internal/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.spend.smallbiz",
       "name":"Small-business card spend",
       "model_class":"credit.spend.linear","domain":"credit",
       "owner":"person/j.okafor","legal_entity":"LE-UK-01",
       "purpose":"expected 12-month card spend at renewal"}'

curl -u j.okafor:… -X POST https://maya.internal/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.spend.smallbiz#champion",
       "principal":"svc/renewals","declared_use":"renewal_limit_decision",
       "environment":"prod",
       "inputs":{"features":{"turnover":240.0,"tenure_years":6.0}}}'
```

Refusals share one shape — `error`, `detail`, `remediation`. Every response
carries an `X-Request-Id` header, and that is the id the server wrote in its
log for the same call, which is what makes a support conversation short. The
full endpoint list is in the [API reference](/help/api-reference).

---

## What this model still needs

The path is complete; the model is not. In rough order of what a reviewer will
ask for first:

- **Independent validation.** Nobody has challenged it. That is the gap the
  compiled document names, and it is a different person's job.
- **Monitoring.** No monitor watches the spend estimate drift, and a model
  nobody watches is a model nobody will notice going wrong.
- **A methodology note and a data dictionary**, filed as attachments — the two
  gaps the pack listed.
- **1.1.0**, which has a kernel and nothing else.

Where to go next: [Warrants and training](/tutorials/warrants-and-training)
for the warrant families beyond the two used here, and
[Validation and findings](/help/validation) for the challenge that comes next.

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE.
*Not legal, regulatory or financial advice — see NOTICE §4.*
