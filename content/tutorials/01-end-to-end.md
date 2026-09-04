---
title: A model, end to end
slug: end-to-end
section: Start here
order: 10
icon: signpost-split
summary: One model taken all the way — registered, versioned, tiered, submitted, approved, attested, given features, validated, warranted, monitored — with every call shown.
audience: Everyone
---

# A model, end to end

This is the whole platform in one worked example: a small-business PD scorecard,
from nothing to a signed warrant an execution engine can act on, with monitoring
watching it afterwards.

Every call is real. Run them against a local instance and you will get the
states described.

## Cast

Duties are separated, so this takes four people. That is not ceremony — the
system refuses several of these steps if one person tries to do them all.

| Who | Role | Does |
|---|---|---|
| `j.okafor` | `model_owner` | registers, tiers, submits, issues warrants |
| `d.raman` | `model_developer` | creates versions, defines and materialises features |
| `s.iqbal` | `model_risk_manager` | approves, moves aliases, defines monitors |
| `a.mehta` | `validator` | runs validation, closes findings |

```bash
curl -u admin:admin123 -X POST localhost:5006/api/v1/principals \
  -H 'Content-Type: application/json' -d '{
  "username": "j.okafor", "display_name": "Joy Okafor",
  "roles": ["model_owner"], "password": "pw"}'
# ...and the same for d.raman (model_developer), s.iqbal (model_risk_manager),
# a.mehta (validator)
```

## 1. Register — `j.okafor`

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

The record is now `draft`: open to change, not in force.

## 2. Create a version — `d.raman`

```bash
curl -u d.raman:pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/versions \
  -H 'Content-Type: application/json' -d '{
  "semver": "3.2.1",
  "kernel": {
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "runtime": "pmml",
    "entry": {"document": "sb_pd_3.2.1.pmml", "model_name": "SBPD", "pmml_version": "4.4"},
    "input_schema": [{"name": "dscr", "dtype": "float", "minimum": -5, "maximum": 20}],
    "output_schema": [{"name": "pd_12m", "dtype": "float"}]},
  "contract": {
    "assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
    "guarantees": [{"key": "gini", "minimum": 0.42}]},
  "artifact_digest": "sha256:9f2c1a"}'
```

Two things happened that you did not ask for. The **trainability class** was
derived — `estimated_coefficients` fitted by `estimate` is **T2** — and the
**manifest digest** was computed over the whole specification. Neither is
declarable, which is the point: see
[Trainability classes](/help/registering-a-model#trainability-classes-t0-to-t8).

Declaring `runtime` and `entry` is optional but worth doing. Without them the
warrant is issued **descriptor-only** — MAYA holds the governance, and the
engine has to know how to find the artifact itself.

## 3. Assess the risk — `j.okafor`

```bash
curl -u j.okafor:pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure": 2000000000, "purpose_class": "regulatory_capital"}'
```

The response carries the derivation, not just the number: which facts were used,
which lattice they landed in, which ruleset decided.

## 4. Features — `d.raman`

A model that reads features needs those features pinned. See
[the features tutorial](/tutorials/features-end-to-end) for the full story;
briefly:

```bash
# define, create a view, materialise it with BOTH clocks
curl -u d.raman:pw -X POST localhost:5006/api/v1/features -d '{...}'
curl -u d.raman:pw -X POST localhost:5006/api/v1/feature-views -d '{...}'
curl -u d.raman:pw -X POST \
  localhost:5006/api/v1/feature-views/sb_financials/materialise -d '{"rows": [...]}'

# pin this model version to that exact view version
curl -u d.raman:pw -X POST localhost:5006/api/v1/feature-contracts \
  -H 'Content-Type: application/json' \
  -d '{"model_version_id": "...", "items": [{"view": "sb_financials", "version": 1}]}'
```

## 5. Validate — `a.mehta`

```bash
VAL=$(curl -su a.mehta:pw -X POST localhost:5006/api/v1/validations \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz", "semver": "3.2.1",
  "validators": ["a.mehta"], "kind": "initial",
  "scope": ["discrimination", "calibration"]}' | jq -r .id)

curl -u a.mehta:pw -X POST localhost:5006/api/v1/validations/$VAL/results \
  -H 'Content-Type: application/json' -d '{
  "test_key": "discrimination.gini", "threshold": {"min": 0.42},
  "left": [0,0,1,1,...], "right": [0.02,0.05,0.61,0.94,...]}'

curl -u a.mehta:pw -X POST localhost:5006/api/v1/validations/$VAL/conclude \
  -H 'Content-Type: application/json' -d '{"outcome": "approved"}'
```

Try naming `d.raman` as validator and it is refused: they built this version.
Try concluding `approved` with a failed test and it is refused, and the refusal
offers the two legitimate routes.

## 6. Approve the version, point the alias — `s.iqbal`

```bash
curl -u s.iqbal:pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/versions/3.2.1/approve

curl -u s.iqbal:pw -X PUT \
  localhost:5006/api/v1/models/credit.pd.smallbiz/aliases \
  -H 'Content-Type: application/json' \
  -d '{"environment": "prod", "alias": "champion", "semver": "3.2.1"}'
```

`d.raman` cannot do either of these — not because of their role but because the
evidence chain records that they created this version. See
[segregation of duties](/help/approval-and-attestation#segregation-of-duties).

## 7. The record: submit, approve, attest

```bash
curl -u j.okafor:pw -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/submit \
  -H 'Content-Type: application/json' -d '{"note": "ready for second-line review"}'

curl -u s.iqbal:pw -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/approve \
  -H 'Content-Type: application/json' -d '{"note": "challenge complete"}'

# a quorum: BOTH required roles sign
curl -u j.okafor:pw -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/attest \
  -H 'Content-Type: application/json' -d '{
  "role": "model_owner",
  "statement": "Controls are operating and the model is used only for its approved purpose."}'

curl -u s.iqbal:pw -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/attest \
  -H 'Content-Type: application/json' -d '{"role": "model_risk_manager"}'
```

The record is now **attested**: in force, and immutable. Try adding a version and
you are told to open an amendment. See
[Approval and attestation](/help/approval-and-attestation).

## 8. A warrant — `j.okafor`

```bash
curl -u j.okafor:pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz#champion", "environment": "prod",
  "principal": "svc/origination", "declared_use": "origination_decision"}'

curl -u j.okafor:pw -X POST "localhost:5006/api/v1/resolve?verb=score" \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz#champion", "environment": "prod",
  "principal": "svc/origination", "declared_use": "origination_decision"}'
```

That second call returns the signed warrant — the whole contract an execution
engine acts on. See [warrants by model family](/tutorials/warrants-by-family).

## 9. Monitor — `s.iqbal`

```bash
curl -u s.iqbal:pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz",
  "name": "origination discrimination", "kind": "performance",
  "test_key": "discrimination.gini", "threshold": {"min": 0.40},
  "label_delay_days": 365, "cadence_days": 30,
  "breach_severity": "High", "owner": "person/j.okafor"}'
```

## 10. Watch it fail closed

```bash
curl -u a.mehta:pw -X POST localhost:5006/api/v1/findings \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz", "severity": "Critical",
  "title": "Label leakage in the training set", "owner": "person/j.okafor"}'
```

Resolve again: **423 Locked**, error `blocked`. The model is registered,
approved, attested, aliased — and unservable. That is the difference between a
register and a control.
