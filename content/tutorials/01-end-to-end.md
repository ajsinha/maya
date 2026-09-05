---
title: A model, end to end
slug: end-to-end
section: Start here
order: 10
icon: signpost-split
summary: One model taken all the way — registered, versioned, tiered, validated, approved by a quorum, promoted, attested, warranted and monitored. Organised by who signs what, because no single account can reach the end.
audience: Everyone
---

# A model, end to end

You cannot get a model into production here on your own. That is not a
configuration setting; it is what the platform is for, and it is the reason this
tutorial is organised by **who acts** rather than by what call comes next.

A small-business PD scorecard, from an empty register to a signed warrant an
execution engine can act on. Eleven acts, four people, and at every handover the
platform decides by reading the **evidence chain** — who actually did what —
rather than by reading a role badge.

| Act | Who | Refused if you do it as anybody else |
|---|---|---|
| register | `j.okafor` — model owner | no `model:register` |
| create the version | `d.raman` — model developer | — |
| assess the tier | `j.okafor` | no `risk:assess` |
| validate | `a.mehta` — validator | `d.raman` built it, so `d.raman` cannot validate it |
| approve the version | `s.iqbal` + `a.mehta` | one signature is `quorum_required` at Tier 1 and 2 |
| move the alias | `s.iqbal` — model risk manager | whoever created the version cannot promote it |
| attest the record | `j.okafor` + `s.iqbal` | a quorum, not a signature |
| warrant it | `j.okafor` | you may only resolve for yourself |

Every call below is real. Run them against a local instance and you will get the
states described — including the refusals, which are the parts worth running
twice.

---

## 0 · Four accounts

```bash
curl -u admin:admin123 -X POST localhost:5006/api/v1/principals \
  -H 'Content-Type: application/json' -d '{
  "username": "j.okafor", "display_name": "Joy Okafor",
  "roles": ["model_owner"], "password": "pw"}'
```

Repeat for `d.raman` (`model_developer`), `s.iqbal` (`model_risk_manager`) and
`a.mehta` (`validator`). Roles are unions of permissions and nothing else; the
interesting checks are the ones roles cannot express, and those read the chain.

```bash
curl -u d.raman:pw localhost:5006/api/v1/me
```

Ask the platform what you may do rather than reasoning about it. A second
implementation of a governance rule disagrees with the first eventually, and it
disagrees in the direction of permitting more.

---

## 1 · `j.okafor` registers the model

```bash
curl -u j.okafor:pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz",
  "name": "Small Business PD",
  "model_class": "credit.pd.scorecard",
  "domain": "credit",
  "owner": "person/j.okafor",
  "legal_entity": "LE-US-01",
  "purpose": "12-month PD at origination"}'
```

The record lands in `draft`: open to change, and not in force. Registration
proves nothing about the model. It creates the thing everything else will be
bound to.

---

## 2 · `d.raman` creates a version

A version is the **kernel** — `f : P ⊗ X → D(Y)` — and it is immutable from the
moment it exists.

```bash
curl -u d.raman:pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/versions \
  -H 'Content-Type: application/json' -d '{
  "semver": "3.2.1",
  "kernel": {
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "runtime": "pmml",
    "entry": {"document": "sb_pd_3.2.1.pmml", "model_name": "SBPD",
              "pmml_version": "4.4"},
    "input_schema": [{"name": "dscr", "dtype": "numeric",
                      "minimum": -5, "maximum": 20}],
    "output_schema": [{"name": "pd_12m", "dtype": "numeric"}]},
  "contract": {
    "assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
    "guarantees": [{"key": "gini", "minimum": 0.42}]},
  "artifact_digest": "sha256:9f2c1a7e…"}'
```

Two things came back that you did not send. The **trainability class** was
derived — `estimated_coefficients` inhabited by `estimate` is **T2** — and a
**manifest digest** was computed over the whole specification. Neither is
declarable. See
[trainability classes](/help/registering-a-model#trainability-classes-t0-to-t8).

`runtime` and `entry` are optional. Leave them out and every warrant for this
model is issued **descriptor-only**: MAYA carries the governance and the engine
has to find the artifact itself. That is the honest state for a vendor black
box, and it is recorded rather than guessed — see
[storing model artifacts](/tutorials/storing-artifacts).

---

## 3 · `j.okafor` assesses the tier — *after* the version, not before

```bash
curl -u j.okafor:pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure": 2000000000, "purpose_class": "regulatory_capital",
       "feature_count": 3, "interpretable": true}'
```

```json
{"tier": 2, "materiality": "material", "complexity": "simple",
 "required_controls": ["independent_validation", "biennial_review",
                       "quarterly_monitoring", "delegated_approval",
                       "full_documentation"],
 "rationale": "materiality=material (exposure 2,000,000,000 in band 'material',
   purpose 'regulatory_capital'); complexity=simple (class T2);
   tau(material,simple)=Tier 2 under ruleset 2026.09.1"}
```

**Order matters here, and it is easy to get wrong.** Complexity is read off the
*latest version's* derived class. Assess a model with no version yet and the
assessment is made as though it were T0. For this scorecard that happens to
land on the same tier; for a neural network on the same book it is the
difference between Tier 2 and Tier 1 — and Tier 1 is the one that needs a
committee.

You get the **derivation**, not a number: the facts used, the bands they fell
in, the required control set and the ruleset version that decided. A tier
without its derivation is a number somebody has to defend from memory.

---

## 4 · `d.raman` pins the data

A model that reads features needs those features pinned to exact versions.
[Features, end to end](/tutorials/features-end-to-end) is the full story;
briefly:

```bash
curl -u d.raman:pw -X POST localhost:5006/api/v1/features -d '{…}'
curl -u d.raman:pw -X POST localhost:5006/api/v1/feature-views -d '{…}'

# values, with BOTH clocks on every row
curl -u d.raman:pw -X POST \
  localhost:5006/api/v1/feature-views/sb_financials/data \
  -H 'Content-Type: text/csv' --data-binary @financials.csv

# bind this model version to that exact view version
curl -u d.raman:pw -X POST localhost:5006/api/v1/feature-contracts \
  -H 'Content-Type: application/json' \
  -d '{"model_version_id": "01a06a0a079c…",
       "items": [{"view": "sb_financials", "version": 1}]}'
```

Then ask what serving *must* read:

```bash
curl -u a.mehta:pw \
  localhost:5006/api/v1/feature-contracts/01a06a0a079c…/namespaces
```

```json
{"namespaces": {"sb_financials": "features/customer/sb_financials/v1"}}
```

Without that pin, *the model used the right features* is an assumption. With
it, it is a comparison.

---

## 5 · `a.mehta` validates, and cannot be `d.raman`

```bash
VAL=$(curl -su a.mehta:pw -X POST localhost:5006/api/v1/validations \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz", "semver": "3.2.1",
  "validators": ["a.mehta"], "kind": "initial",
  "scope": ["discrimination", "calibration"]}' | jq -r .id)

curl -u a.mehta:pw -X POST localhost:5006/api/v1/validations/$VAL/results \
  -H 'Content-Type: application/json' -d '{
  "test_key": "discrimination.gini", "threshold": {"min": 0.42},
  "left": [0, 0, 1, 1], "right": [0.02, 0.05, 0.61, 0.94]}'

curl -u a.mehta:pw -X POST localhost:5006/api/v1/validations/$VAL/conclude \
  -H 'Content-Type: application/json' -d '{"outcome": "approved"}'
```

`left` is the outcomes, `right` is the scores, and the threshold is judged in
one place — the test catalogue — rather than by whoever wrote the results down.
`GET /api/v1/tests` lists the eight tests a validation may run; a test that is
not in the catalogue has no agreed definition, and a validation report full of
bespoke statistics is a report nobody can compare against the next one.

Name `d.raman` as a validator and it is refused: they created this version.
Conclude `approved` over a failed test and it is refused too, and the refusal
names the two legitimate routes — `approved_with_conditions` with the conditions
written down, or `rejected`.

---

## 6 · A Tier 2 version needs two signatures

```bash
curl -u s.iqbal:pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/versions/3.2.1/approve
```

```json
{"error": "quorum_required",
 "detail": "a tier 2 version is approved by a quorum of model_risk_manager,
            validator, not by one signature",
 "remediation": "open an approval at POST /api/v1/version-approvals with
   {\"urn\": \"maya://model/credit.pd.smallbiz\", \"semver\": \"3.2.1\"},
   then have each required role POST to /version-approvals/<id>/sign"}
```

The refusal names the endpoint, because a refusal that tells you what you may
not do and not what you may is half a refusal.

```bash
APPROVAL=$(curl -su s.iqbal:pw -X POST localhost:5006/api/v1/version-approvals \
  -H 'Content-Type: application/json' \
  -d '{"urn": "maya://model/credit.pd.smallbiz", "semver": "3.2.1"}' | jq -r .id)

curl -u s.iqbal:pw -X POST localhost:5006/api/v1/version-approvals/$APPROVAL/sign \
  -H 'Content-Type: application/json' -d '{"role": "model_risk_manager"}'
curl -u a.mehta:pw  -X POST localhost:5006/api/v1/version-approvals/$APPROVAL/sign \
  -H 'Content-Type: application/json' -d '{"role": "validator"}'
```

Tiers 3 and 4 are approved by one authorised person. The table is published at
`GET /api/v1/version-approval-quorum` rather than living in a policy document
somebody has to be told about.

---

## 7 · `s.iqbal` moves the alias

```bash
curl -u s.iqbal:pw -X PUT \
  localhost:5006/api/v1/models/credit.pd.smallbiz/aliases \
  -H 'Content-Type: application/json' \
  -d '{"environment": "prod", "alias": "champion", "semver": "3.2.1"}'
```

This is the only operation in the platform that **replaces** something rather
than adding to it, and it is therefore a proof obligation rather than a write:
the replacement's contract must refine the incumbent's (L-7) and its schemas
must satisfy variance (L-12). [Running several versions at
once](/tutorials/managing-versions) is that argument in full.

`d.raman` cannot do this, and not because of their role. The evidence chain
records that they created 3.2.1. See [segregation of
duties](/help/approval-and-attestation#segregation-of-duties).

---

## 8 · The record goes into force

```bash
curl -u j.okafor:pw -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/submit \
  -H 'Content-Type: application/json' -d '{"note": "ready for second-line review"}'

curl -u s.iqbal:pw -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/approve \
  -H 'Content-Type: application/json' -d '{"note": "challenge complete"}'

curl -u j.okafor:pw -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/attest \
  -H 'Content-Type: application/json' -d '{
  "role": "model_owner",
  "statement": "Controls are operating and the model is used only for its approved purpose."}'

curl -u s.iqbal:pw -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/attest \
  -H 'Content-Type: application/json' -d '{"role": "model_risk_manager"}'
```

Attestation is a **quorum**: both required roles sign, and one decline ends it.

The record is now `attested`, which means immutable — including for new
versions, because a new version *is* a change to the model. Try adding 3.3.0 and
you are told to open an amendment. Immutability is a state rather than a flag
because the question a supervisor asks is not *is this locked* but *what is in
force, who said so, and when*.

---

## 9 · `j.okafor` issues the entitlement; the consumer mints the warrant

A **grant** says this principal may ask. A **warrant** is one signed, expiring
answer to one asking. They are different objects, and revoking the first stops
the next warrant rather than reaching into the last one.

```bash
curl -u j.okafor:pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz#champion", "environment": "prod",
  "principal": "svc/origination", "declared_use": "origination_decision"}'
```

Now the consumer resolves for itself:

```bash
curl -u svc/origination:pw -X POST "localhost:5006/api/v1/resolve?verb=score" \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz#champion", "environment": "prod",
  "principal": "svc/origination", "declared_use": "origination_decision"}'
```

Ask for a warrant naming somebody else and you get `principal_not_self`, unless
you hold `warrant:issue`. A credential that does not name who is acting is not a
credential.

What comes back is the whole ten-section execution contract — subject,
operation, parameters, realisation, data, io_contract, constraints, authority,
governance, signature. See [warrants by model
family](/tutorials/warrants-by-family) for what changes across the estate, which
is less than you would expect.

---

## 10 · `s.iqbal` defines a monitor

```bash
curl -u s.iqbal:pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz",
  "name": "origination discrimination", "kind": "performance",
  "test_key": "discrimination.gini", "threshold": {"min": 0.40},
  "label_delay_days": 365, "cadence_days": 30,
  "breach_severity": "High", "owner": "person/j.okafor"}'
```

`label_delay_days` is the field that makes this monitoring rather than a
dashboard. A twelve-month PD's discrimination is not knowable sooner, and the
monitor **will not evaluate** a cohort until it is mature. A performance number
computed on a three-month-old cohort is a number about the fast defaulters only,
and it looks like reassurance.

---

## 11 · Watch it fail closed

Everything above is done. Registered, versioned, tiered, validated, approved by
two people, promoted, attested, warranted, monitored. Now:

```bash
curl -u a.mehta:pw -X POST localhost:5006/api/v1/findings \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz", "severity": "Critical",
  "title": "Label leakage in the training set", "owner": "person/j.okafor"}'
```

Resolve again:

```
423 Locked — {"error": "blocked", …}
```

The model is complete in every register sense and **unservable**. Nothing was
redeployed, nobody was emailed, and no consumer changed a line: the alias still
resolves, and resolution refuses. That is the difference between a register and
a control, and it is the single thing worth taking from this page.

---

## The same path, in Python

The compliant path is deliberately the fast path. If registering a model
properly took forty lines of HTTP plumbing and getting it wrong took four, the
register would fill with models nobody registered properly.

```python
from maya_sdk import Maya, Blocked

maya = Maya("http://localhost:5006", "s.iqbal", "pw")

try:
    maya.versions.promote("maya://model/credit.pd.smallbiz", semver="3.2.1")
except Blocked as refusal:
    print(refusal.code)          # blocked
    print(refusal.detail)        # an open blocking finding stands against it
    print(refusal.remediation)   # close it, or ask the validator to downgrade it
    print(refusal.request_id)    # quote this in the ticket
```

A refusal is raised, never returned: a caller who forgets to check a result
object has continued past a governance decision while their code reads as though
it succeeded. `sdk/python` is dependency-free and holds no opinions — ask
`maya.whoami()` rather than reasoning about permissions.

---

## Where to go next

| | |
|---|---|
| [The whole path](/tutorials/the-whole-path) | the same journey with the featuresets, the composition graph and the documentation that comes out of the far end |
| [Features, end to end](/tutorials/features-end-to-end) | the two clocks, and the operator that makes a training set reproducible |
| [Every kind of model, worked](/tutorials/every-kind-of-model) | the seven families, one tutorial each, and why the class is derived |
| [Warrants by model family](/tutorials/warrants-by-family) | one document, fourteen laws, no special cases |
