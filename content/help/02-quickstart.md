---
title: Quickstart
slug: quickstart
section: Getting started
order: 20
icon: rocket-takeoff
summary: Register a model, version it, assess its risk, approve it, point an alias, and resolve a signed warrant — the whole governed path, end to end.
audience: Engineers
---

# Quickstart

This walks the complete governed path. Every step is a real API call against a
running instance; nothing here is illustrative pseudocode.

Sign in at `/login` with the development credentials (`admin` / `admin123`), or
call the API directly as shown.

## 1. Register the model

Registration is the cheapest governance act in the platform and the one most
often skipped. It asks for the minimum that makes a model **findable** and
**accountable**, and defers everything else to the version that follows.

```bash
curl -X POST localhost:5006/api/v1/models -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz",
  "name": "Small Business PD",
  "model_class": "credit.pd.scorecard",
  "domain": "credit",
  "owner": "person/j.okafor",
  "legal_entity": "LE-US-01",
  "purpose": "12-month PD at origination"
}'
```

The **URN** is the permanent handle. Consumers hold it and nothing else — see
[Warrants](/help/warrants) for why that matters.

## 2. Create a version

A version carries the *kernel specification*: how the parameter object is
inhabited, the input and output schemas, and the operating contract.

```bash
curl -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/versions \
  -H 'Content-Type: application/json' -d '{
  "semver": "3.2.1",
  "kernel": {
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "input_schema": [{"name": "dscr", "dtype": "float", "minimum": -5, "maximum": 20}],
    "output_schema": [{"name": "pd_12m", "dtype": "float"}]
  },
  "contract": {
    "assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
    "guarantees": [{"key": "gini", "minimum": 0.42}]
  },
  "artifact_digest": "sha256:9f2c1a"
}'
```

Note what you did **not** send: a trainability class. It is derived from
`parameter_kind` and `fit_procedure`, because a class you can declare is a class
someone will declare conveniently.

Versions are immutable. Creating `3.2.1` twice is refused.

## 3. Assess the risk

```bash
curl -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure": 2000000000, "purpose_class": "regulatory_capital"}'
```

The response carries the **derivation**, not just the tier — which facts were
used, which lattice they landed in, and which ruleset version decided. See
[Risk tiering](/help/risk-tiering).

## 4. Approve, then point an alias

```bash
curl -X POST localhost:5006/api/v1/models/credit.pd.smallbiz/versions/3.2.1/approve

curl -X PUT localhost:5006/api/v1/models/credit.pd.smallbiz/aliases \
  -H 'Content-Type: application/json' \
  -d '{"environment": "prod", "alias": "champion", "semver": "3.2.1"}'
```

The alias move is the most dangerous operation in the platform, so it is a
**proof obligation** rather than a judgement call. If there were an incumbent, the
replacement's contract would have to refine it and its schemas would have to
satisfy variance, or the move is refused naming the clause that failed.

## 5. Issue and resolve a warrant

```bash
curl -X POST localhost:5006/api/v1/warrants -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz#champion",
  "environment": "prod",
  "principal": "svc/origination",
  "declared_use": "origination_decision"
}'

curl -X POST localhost:5006/api/v1/resolve -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz#champion",
  "environment": "prod",
  "principal": "svc/origination",
  "declared_use": "origination_decision"
}'
```

The second call returns a **signed, expiring warrant**. Your execution engine acts
on it. MAYA never touches the model.

## 6. Watch it fail closed

This is the part worth doing, because it is what distinguishes a register from a
control.

```bash
curl -X POST localhost:5006/api/v1/findings -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz",
  "severity": "Critical",
  "title": "Label leakage in the training set",
  "owner": "person/j.okafor"
}'
```

Now resolve again. You get **423 Locked**, an error code of `blocked`, and a
remediation hint. The model is still registered, still approved, still aliased —
and unservable, because a Critical finding blocks by default.

Close the finding with an independent verifier and evidence, and service resumes
on the next call.

## Next

- [Features and the two clocks](/help/features-and-two-clocks) — before you train anything.
- [Validation](/help/validation) — how challenge is recorded and enforced.
