---
title: Quickstart
slug: quickstart
section: Getting started
order: 20
icon: rocket-takeoff
summary: Six calls from an empty register to a signed warrant, then a seventh that takes the model out of service — the whole governed path, including the refusals, against a running instance.
audience: Engineers
---

# Quickstart

Six calls take a model from nothing to a signed warrant an execution engine can
act on. A seventh takes it out of service. Everything below is a real API call
against a running instance; none of it is illustrative pseudocode.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python run_maya_web.py         # listens on 5006
```

## Before the first call: make the people

**Duties are separated, so the accounts have to be.** The developer who creates a
version cannot approve it, and a version on a tiered model needs signatures from
two different people. Run all seven steps as one account and you will be refused
somewhere around step four — correctly, and it is the single most useful thing
this page demonstrates.

A fresh instance has one principal: `admin` / `admin123`. Change it before
anybody else can reach the port. Then make the four the rest of this page uses:

```bash
for who in "j.okafor|Joy Okafor|model_owner|owner-pw" \
           "d.raman|Deepa Raman|model_developer|dev-pw" \
           "s.iqbal|Sara Iqbal|model_risk_manager|mrm-pw" \
           "a.mehta|Arun Mehta|validator|val-pw"; do
  IFS='|' read -r user name role pw <<< "$who"
  curl -su admin:admin123 -X POST localhost:5006/api/v1/principals \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$user\",\"display_name\":\"$name\",
         \"roles\":[\"$role\"],\"password\":\"$pw\"}"
done

curl -su admin:admin123 -X POST localhost:5006/api/v1/principals \
  -H 'Content-Type: application/json' \
  -d '{"username":"svc/origination","display_name":"Origination",
       "kind":"service","roles":["service"],"password":"svc-pw"}'
```

Ask at any point what an account may actually do:

```bash
curl -u a.mehta:val-pw localhost:5006/api/v1/me
```

**A note on authentication.** Services and scripts use HTTP Basic against the
same principal register the interface uses, so there is one identity store. The
browser uses a signed session cookie, and *only* the cookie surface carries a
CSRF token (`x-maya-csrf`) — a Basic caller already holds the credential, so
asking for a token as well would protect nothing and break every service client.
Every response carries an `x-request-id`; send your own and it is echoed back and
stamped on every log line the call produced.

## 1. Register the model

Registration is the cheapest governance act here, and the one most often skipped.
It asks only for what makes a model **findable** and **accountable**, and defers
everything consequential to the version.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' -d '{
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
[Warrants and execution](/help/warrants#the-urn-is-all-a-consumer-holds).

## 2. Create a version

A version carries the kernel: how `P` is inhabited, the input and output schemas,
and the operating contract.

```bash
curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/versions \
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

Note what you did **not** send: a trainability class. `estimated_coefficients`
fitted by `estimate` is **T2**, and MAYA derives that rather than accepting it,
because a class you can declare is a class somebody will declare conveniently.
There is no such request field anywhere in the API. See
[Registering a model](/help/registering-a-model#trainability-classes-t0-to-t8).

Versions are immutable. Creating `3.2.1` twice is refused:

```
version 3.2.1 already exists for maya://model/credit.pd.smallbiz;
versions are immutable
```

## 3. Assess the risk

```bash
curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure": 2000000000, "purpose_class": "regulatory_capital",
       "feature_count": 12, "uses_alternative_data": false, "interpretable": true}'
```

The response carries the **derivation**, not just the number: `tier`,
`materiality`, `complexity`, `required_controls`, the `rationale` naming which
facts were used, and the `ruleset_version` that decided. See
[Risk tiering](/help/risk-tiering).

Do this **before** approving anything. The tier decides how many signatures a
version's approval needs, so a version on an untiered model cannot be approved at
all — approving first would be a way of choosing your own control depth.

## 4. Approve the version

Ask what this version's approval actually requires rather than guessing:

```bash
curl -u s.iqbal:mrm-pw \
  'localhost:5006/api/v1/version-approvals?urn=maya://model/credit.pd.smallbiz&semver=3.2.1'
```

Tiers 1 and 2 need a **quorum** — a model risk manager *and* a validator, who
must be two different people. Tiers 3 and 4 keep a single signature, and the
register says plainly that they do: pretending a scheduling heuristic deserves
the same ceremony as a capital model is how a control becomes something people
route around.

```bash
APPROVAL=$(curl -su s.iqbal:mrm-pw -X POST localhost:5006/api/v1/version-approvals \
  -H 'Content-Type: application/json' \
  -d '{"urn": "maya://model/credit.pd.smallbiz", "semver": "3.2.1"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -u s.iqbal:mrm-pw -X POST \
  localhost:5006/api/v1/version-approvals/$APPROVAL/sign \
  -H 'Content-Type: application/json' -d '{"role": "model_risk_manager"}'

curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/version-approvals/$APPROVAL/sign \
  -H 'Content-Type: application/json' -d '{"role": "validator"}'
```

Where a tier needs no quorum, one call does it instead:

```bash
POST /api/v1/models/credit.pd.smallbiz/versions/3.2.1/approve
```

On the single-signature path, whoever created the version may not approve it —
and that is not a role rule. It is read back from the evidence chain, which
recorded `version_created` against this exact version and knows who did it. On
the quorum path, independence comes from the quorum itself: two different people,
in two different second-line roles, and the same person may not sign twice under
two hats.

## 5. Point an alias

```bash
curl -u s.iqbal:mrm-pw -X PUT \
  localhost:5006/api/v1/models/credit.pd.smallbiz/aliases \
  -H 'Content-Type: application/json' \
  -d '{"environment": "prod", "alias": "champion", "semver": "3.2.1"}'
```

The alias move is the most dangerous operation in the platform, so it is a
**proof obligation** rather than a judgement call. Three things are checked, in
this order: the target version is approved; no blocking finding stands against
the model; and, against the incumbent if there is one, the replacement's contract
**refines** it (**L-7**) and its schemas satisfy variance (**L-12**). The
response carries both proofs and their reasons; a failure names the clause.

## 6. Issue and resolve a warrant

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz#champion",
  "environment": "prod",
  "principal": "svc/origination",
  "declared_use": "origination_decision"
}'

curl -u svc/origination:svc-pw -X POST localhost:5006/api/v1/resolve \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz#champion",
  "environment": "prod",
  "principal": "svc/origination",
  "declared_use": "origination_decision"
}'
```

The first call issues a standing **grant** — this principal, in this environment,
for this declared use. The second mints a **signed, expiring warrant** against
it. Your execution engine acts on the warrant; MAYA never touches the model.

Separating the two is what makes revocation mean something: withdrawing the grant
stops future warrants, and bumping the revocation epoch invalidates the ones
already in flight.

## 7. Watch it fail closed

This is the step worth doing, because it is what separates a register from a
control.

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/findings \
  -H 'Content-Type: application/json' -d '{
  "urn": "maya://model/credit.pd.smallbiz",
  "severity": "Critical",
  "title": "Label leakage in the training set",
  "owner": "person/j.okafor"
}'
```

Resolve again. You get **423**, an error code of `blocked`, and a remediation.
The model is still registered, still approved, still aliased — and unservable,
because a Critical finding blocks by default. Nothing had to be redeployed and
nobody had to be emailed.

Close the finding with an independent verifier and evidence, and service resumes
on the next call. The person who raised a finding may not close it, and its owner
may not verify their own closure: two different questions, and a person can fail
either.

## Where to go next

- [Features and the two clocks](/help/features-and-two-clocks) — read this
  before you train anything, not after.
- [Registering a model](/help/registering-a-model) — what the kernel fields mean
  and what the class changes.
- [Validation and findings](/help/validation) — how challenge is recorded and
  how it stops a model.
- [A model, end to end](/tutorials/end-to-end) — this path as a worked tutorial,
  carried on through attestation.
- [The whole path, step by step](/tutorials/end-to-end) — the same journey
  from an empty register, including every refusal on the way.

Or from Python, with no dependencies at all — `sdk/python` ships a standard
library only client, and a refusal is raised rather than returned:

```python
from maya_sdk import Maya, Blocked

maya = Maya("http://localhost:5006", "s.iqbal", "mrm-pw")
try:
    maya.versions.promote("maya://model/credit.pd.smallbiz", semver="3.2.1")
except Blocked as refusal:
    print(refusal.code, refusal.detail)
    print(refusal.remediation)
    print(refusal.request_id)      # the id the server logged this call under
```
