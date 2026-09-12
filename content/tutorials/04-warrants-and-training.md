---
title: Warrants — training a model, and running one
slug: warrants-and-training
section: Start here
order: 40
icon: shield-check
summary: A warrant is the signed contract MAYA hands an execution engine — one to fit a model, one to run it. This walks the whole round trip on a real scorecard, from the standing grant that nothing works without, through the fit warrant an engine trains from and the parameters coming back under it, to the scoring warrant that names the numbers a run is at.
audience: Model developers, Model owners, Engineers running models
---

# Warrants — training a model, and running one

MAYA does not run your model. It hands out a **signed, expiring contract** that
says who may do what to which version, with which data, until when — and your
execution engine acts on it.

There are two you will meet on Monday:

| | what it says | where it comes from |
|---|---|---|
| **fit warrant** | train *this* version from *that* featureset version, over this window, as of this moment | `POST /api/v1/fit-warrants` |
| **scoring warrant** | run *this* version at *these* approved parameters, inside this operating boundary | `POST /api/v1/resolve` |

**The three variables every curl block here uses**, stated rather than assumed —
the page used them from the first block and named them nowhere, so a reader
copying one ran `curl -u ":"` against an empty host:

```bash
MAYA=http://localhost:5006
USER=j.okafor
PASS=owner-pw
```

Every screen below is on one page: **`/warrants`**, with the model chosen at the
top. Every screen posts to the endpoint shown beside its button — the same
endpoint your engine calls.

---

## 1 · An approved model is not an entitled one

This is the refusal that surprises everybody, so it comes first. Take a model
that is registered, versioned, approved by two people and pointed at by the
`champion` alias, and ask for a warrant:

```json
{
  "error": "no_entitlement",
  "detail": "svc/origination holds no warrant for maya://model/credit.pd.smallbiz in prod",
  "remediation": "request a warrant grant for this principal and approved use"
}
```

HTTP 403. `/api/v1/execute` gives the same refusal for the same reason. Nothing
is wrong with the model, and nothing is wrong with your login. It means nobody
has yet said that **this principal** may use **this model** in **this
environment** for **this purpose**.

That standing statement is a **grant**. It is a different object from the
warrant, and the difference is the whole design:

| | a grant | a descriptor |
|---|---|---|
| says | this principal *may ask* | one signed answer to one asking |
| lifetime | until revoked | seconds to an hour |
| stored by MAYA | **yes** — it has an id you can quote | **no** — minted per request |
| revoking it | stops the *next* descriptor | bumps the epoch, so the ones already out go stale |

### Issue the grant

**On the screen.** Open `/warrants`, choose the model, and use *1 — The standing
grant*. The table above the form lists every grant on the model with its TTL,
grace, epoch and — the column you will need in section 4 — its **grant id**.

**In the SDK.**

```python
grant = maya.warrants.grant(urn="maya://model/credit.pd.smallbiz#champion",
                            environment="prod",
                            principal="svc/origination",
                            declared_use="origination_decision")
print(grant["id"])          # 01a0737af0614a9778204e856443
```

**With curl.**

```bash
GRANT=$(curl -s -u "$USER:$PASS" -X POST "$MAYA/api/v1/warrants" \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz#champion","environment":"prod",
       "principal":"svc/origination","declared_use":"origination_decision"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "$GRANT"
```

**Keep that id.** Section 4 needs it, and there is no endpoint that lists
grants — the `/warrants` screen reads them from the register directly, so a
script has to hold on to what the creation returned. That asymmetry is worth
knowing before you find it.

```json
{"model_id": "01a0737aef0bb2354e5898b17e85", "environment": "prod",
 "binding_kind": "alias", "alias_name": "champion", "version_id": null,
 "flavour": "descriptor_only", "principal": "svc/origination",
 "declared_use": "origination_decision", "ttl_seconds": 300,
 "grace_seconds": 0, "revoked": false, "revoke_reason": null, "epoch": 0,
 "id": "01a0737af0614a9778204e856443"}
```

Three things to notice, because each one bites later:

- **`declared_use` is matched exactly.** Asking with `"pricing"` against a grant
  approved for `"origination_decision"` is refused `use_not_approved`, 403.
- **A bare urn binds the alias**, so the grant follows `champion` wherever it is
  pointed. `#champion` says so explicitly; `@1.0.0` pins one version instead.
- **`ttl_seconds` and `grace_seconds` come from the tier**, not from you: 60s and
  no grace at Tier 1, 300s at Tier 2, an hour with 15 minutes of grace at Tiers 3
  and 4. Tier 1 is the most material, which is why its credential is the
  shortest-lived.

> **Keep the grant id.** `POST /api/v1/warrants` is the only place it is returned
> over the API — there is no `GET /api/v1/warrants`. After that it lives on the
> `/warrants` page and on the model page, and nowhere else.

---

## 2 · A fit warrant, and the document it produces

A fit warrant is what you hand an external training engine. It names the version
to fit, the featureset version to fit it from, the period, and the moment the
data is read as of.

**On the screen.** `/warrants` → *4 — Fit → parameters → score* → **step one**.
Pick the featureset and version from the dropdowns, give the window a from and a
to, give it an `as_of`, and press *Resolve the fit warrant*. The document comes
back on the page.

**In the SDK.**

```python
fit = maya.warrants.for_fitting(
    urn="maya://model/credit.pd.smallbiz",
    principal="svc/model-lab",
    featureset="sb_pd_2026", featureset_version=2,
    window={"from": 1546300800.0, "to": 1735603200.0},
    as_of=1736899200.0,
    environment="lab")
```

**With curl.**

The fit warrant below names **`credit.pd.sbset`**, the model
[featuresets §7](/tutorials/featuresets) registered over `sb_pd_2026`. The
scorecard from [defining a model](/tutorials/defining-a-model) reads `dscr`,
which this set does not carry, and `L-W10` refuses the pair —
`schema_not_satisfied: 'sb_pd_2026' does not provide dscr`. That is the law
working; naming the right model is the fix.

A fit warrant resolves through an **alias in its own environment**, so `lab`
needs one — `nothing bound for … in lab` is not a missing grant, it is a missing
binding, and the two refusals are worth telling apart:

```bash
curl -u s.iqbal:mrm-pw -X PUT "$MAYA/api/v1/models/credit.pd.sbset/aliases" \
  -H 'Content-Type: application/json' \
  -d '{"semver":"1.0.0","environment":"lab","alias":"champion",
       "justification":"the version the lab trains against"}'
```

A grant is per **principal, environment and use**, so the prod grant above does
not reach a lab fit — `no_entitlement: svc/model-lab holds no warrant for … in
lab` is the register declining to widen one on your behalf:

```bash
curl -u "$USER:$PASS" -X POST "$MAYA/api/v1/warrants" \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.sbset","environment":"lab",
       "principal":"svc/model-lab","declared_use":"model_development"}'
```

```bash
curl -u "$USER:$PASS" -X POST "$MAYA/api/v1/fit-warrants" \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.sbset",
       "environment":"lab",
       "principal":"svc/model-lab",
       "declared_use":"model_development",
       "featureset":"sb_pd_2026",
       "featureset_version":2,
       "window":{"from":1546300800,"to":1735603200},
       "as_of":1736899200}'
```

Issuing needs `warrant:issue`, which the **model owner** holds and the model
developer does not. A developer asking gets `403 forbidden` naming the
permission.

### What comes back

Ten sections, each answering exactly one question. This is the real document,
abridged only where a block repeats what you already sent:

```json
{
  "maya_warrant": "1.0",
  "warrant_id": "01a0737af0b47ac84c23bf98e200",
  "issued_at": 1788643831.988,

  "subject": {"urn": "maya://model/credit.pd.smallbiz",
              "version": "1.0.0", "version_id": "01a0737aef4b5e1b83d0e791df6a",
              "manifest_digest": "sha256:fc8f8fee…",
              "binding_kind": "alias", "trainability_class": "T2"},

  "operation": {"verb": "fit", "determinism": "deterministic",
                "seed": null, "mode": "batch"},

  "parameters": {"kind": "estimated_coefficients",
                 "source": {"binding": "to_be_fitted"},
                 "digest": null, "mutable": false},

  "realisation": {"runtime": "estimator",
                  "entry": {"family": "ols", "target": "default_flag",
                            "regressors": ["dscr", "turnover"]},
                  "artifact": {"uri": null, "digest": null, "format": null,
                               "executes_on_load": false, "held_by_maya": false},
                  "environment": {}},

  "data": {"inputs": [{"name": "training_set", "binding": "featureset",
                       "featureset": "sb_pd_2026", "version": 2,
                       "digest": "sha256:f0d6d9d3…",
                       "as_of": 1736899200.0,
                       "window": {"from": 1546300800.0, "to": 1735603200.0},
                       "entity": "borrower_id",
                       "grain": "one row per borrower_id",
                       "slots": [
                         {"slot": "dscr", "feature": "dscr", "dtype": "numeric",
                          "view": "sb_credit", "view_version": 1,
                          "namespace": "features/borrower_id/sb_credit/v1",
                          "delta_version": 0, "certification": "experimental"}
                       ],
                       "namespaces": ["features/borrower_id/sb_credit/v1"],
                       "pit_rule": "event_ts <= label_ts AND ingest_ts <= min(label_ts, as_of)"}],
           "outputs": [{"sink": "parameter_object"}]},

  "io_contract": {"input_schema": [{"name": "dscr", "dtype": "numeric"}],
                  "output_schema": [{"name": "pd_12m", "dtype": "numeric"}]},

  "constraints": {"operating_boundary": {"assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
                                         "guarantees": [{"key": "gini", "minimum": 0.42}],
                                         "on_boundary_violation": "reject"},
                  "on_boundary_violation": "reject",
                  "resources": {"max_seconds": 30}},

  "authority": {"principal": "svc/model-lab", "declared_use": "model_development",
                "environment": "lab", "granted_at": 1788643831.988,
                "expires_at": 1788644131.988, "grace_seconds": 0,
                "revocation": {"epoch": 0, "check": "monotonic"}},

  "governance": {"tier": 2, "model_status": "draft", "version_status": "approved"},

  "signature": {"alg": "HMAC-SHA256", "key_id": "k-f0da581c64135cb6",
                "value": "…"}
}
```

| section | answers |
|---|---|
| `subject` | which model and version this is about |
| `operation` | what is being asked of it |
| `parameters` | where the parameter object comes from |
| `realisation` | how to obtain and invoke the artifact |
| `data` | where the inputs come from and where the outputs go |
| `io_contract` | the input and output schemas |
| `constraints` | the operating boundary and the resource limits |
| `authority` | who may do this, for what, until when |
| `governance` | the state of the record at the moment of issue |
| `signature` | integrity |

The part worth reading twice is `data.inputs[0]`. The **schema travels with the
warrant** — every slot, its type, which feature and which *view version* fills
it, the Delta version, the entity, the grain and the point-in-time rule. An
engine receiving this needs no second call to learn what columns it is training
on, and `digest` lets it check that what it assembled is what was authorised.

Two laws are checked before it is signed, and both refuse rather than warn:

- **L-W9** — a featureset read for fitting must be bounded in *both* clocks. Omit
  `as_of` or either end of `window` and the warrant is refused.
- **L-W10** — the featureset must provide what the kernel declares it reads.
  Bind a set that is missing a regressor and you get `schema_not_satisfied`,
  because adding a regressor is a model change, not a data change.

See [Featuresets](/tutorials/featuresets) for the set this warrant names, and
[Features](/tutorials/features) for the two clocks the `pit_rule` is written in.

---

## 3 · The same warrant, one model type at a time

The document above has exactly one shape. What differs by model is the
`parameters` block and whether `fit` is a question you may ask at all — because
the **trainability class is derived** from how the parameter object is inhabited,
never declared.

All six of these were resolved against the same featureset. The refusals are the
platform's own words:

| class | how `P` is inhabited | `POST /fit-warrants` |
|---|---|---|
| **T0** analytic | nothing to fit — a Black-Scholes closed form | **refused**, 422 `grammar_violation` — *"a T0 model cannot be fitted: its parameters come from theory, not from data — there is nothing to fit"* (**L-W1**) |
| **T1** calibrated | `calibration_set`, solved each morning against instruments | `201` — `"kind": "calibration_set"`, `"source": {"binding": "to_be_fitted"}` |
| **T2** estimated | `estimated_coefficients` from a regression | `201` — the document in section 2 |
| **T3** machine-learned | `learned_weights` inside an artifact | `201` — same, plus `parameters.digest` carrying the artifact's digest |
| **T5** configured | `llm_configuration` — a prompt bundle and its settings | `201` — `"determinism": "stochastic"`, because the version declared it so |
| **T6** vendor black box | `opaque`; the numbers exist and are not ours to see | **refused**, 422, **three problems at once**: descriptor-only cannot be fitted (**L-W6**), a T6 model cannot be fitted (**L-W1**), and a fit cannot run from `vendor_internal` (**L-W8**) |

Fitting a T0 or a T6 is not a policy choice MAYA made. It is a **type error**:
one has no parameters to inhabit, the other has parameters nothing on this side
can reach. Both can still hold **declared** parameters — a closed form arrives
with its constants — which is a different route, taken in section 4.

One trap that catches T5 first: a version that declares `deterministic: true`
over a generative runtime is refused **L-W5**, *"MAYA cannot verify that the
'llm.prompt' runtime is deterministic, because it runs code MAYA does not read."*
Declare it stochastic, or pin a seed. And a generative warrant must pin the
provider's **build**, not just the model family, or **L-W13** refuses it:
*"'claude-sonnet' names a family of weights rather than a build."*

---

## 4 · The engine trains. The numbers come back.

Fitting does **not** create a new model version. `f : P × X → D(Y)` is unchanged;
a fit picks a point in `P`. So what comes back is a **parameter set**, recorded
against the version it belongs to.

> ### The one that costs an hour
>
> `warrant_id` on `POST /parameters` wants the **grant's** id — not the
> `warrant_id` field of the descriptor you just resolved. They are two different
> objects that happen to share a field name. The descriptor is minted per request
> and never stored, so MAYA cannot vouch for it later; the grant is what is
> persisted, so the grant is what is checked.
>
> Quoting the descriptor's id gives you:
>
> ```json
> {"error": "unknown_warrant",
>  "detail": "MAYA did not issue warrant 01a0737af0b47ac84c23bf98e200",
>  "remediation": "parameters are accepted only against a warrant from this register"}
> ```
>
> HTTP 404, and it is entirely correct — MAYA did not issue *that id*, it issued
> the grant behind it.

**On the screen.** `/warrants` → section 4 → **step two**. The `warrant_id` field
is labelled *"the GRANT id"*, and pressing **use** on any row of the grant table
in section 1 fills it in for you. That button exists precisely because of the
trap above.

**In the SDK.**

```python
recorded = maya.parameters.record(
    urn="maya://model/credit.pd.smallbiz", semver="1.1.0",
    name="sb-pd-2026q1", kind="estimated_coefficients",
    values={"intercept": -1.42, "dscr": 0.31, "turnover": -0.02},
    provenance="fitted",
    warrant_id=grant["id"],                    # the GRANT, not fit["warrant_id"]
    featureset="sb_pd_2026", featureset_version=2,
    window={"from": 1546300800.0, "to": 1735603200.0},
    as_of=1736899200.0,
    diagnostics={"r_squared": 0.41, "rows": 18400, "condition_number": 12.4})
```

**With curl.**

The `warrant_id` is **the grant that authorised the fit**, and it is the id from
your own run rather than the one printed above — parameters recorded against a
warrant this register did not issue are refused with `unknown_warrant`, which is
the whole point of the field:

```bash
curl -u "$USER:$PASS" -X POST "$MAYA/api/v1/parameters" \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","semver":"1.1.0",
       "name":"sb-pd-2026q1","kind":"estimated_coefficients","provenance":"fitted",
       "values":{"intercept":-1.42,"dscr":0.31,"turnover":-0.02},
       "diagnostics":{"r_squared":0.41,"rows":18400,"condition_number":12.4},
       "featureset":"sb_pd_2026","featureset_version":2,
       "window":{"from":1546300800,"to":1735603200},"as_of":1736899200,
       "warrant_id":"'"$GRANT"'"}'
```

```json
{"id": "01a0737af0e732dad5541b84792b", "name": "sb-pd-2026q1", "version": 2,
 "provenance": "fitted", "state": "proposed",
 "digest": "sha256:5a31438f7462264f14c2c6ce56a7137dcb40833662abac73c56e4d3d372f849b",
 "created_by": "d.raman",
 "featureset_version_id": "01a0737af04c12daf93d0afbcf8f",
 "warrant_id": "01a0737af083a9ff44ea7a5229ab"}
```

### Where they land, and what they are not yet

They land in the **parameter register**, against `model_version_id` — a row with
its own version number, an immutable digest over the values, the diagnostics, the
window, the `as_of`, and the *featureset version id* the fit read. Not a new model
version; the kernel did not change.

And `"state": "proposed"`. That is not a formality — **no warrant will name a
proposed set**, so the version still cannot run. Somebody who is not the author
has to accept it:

```bash
# the person who recorded them, trying to approve them
curl -u d.raman:… -X POST "$MAYA/api/v1/parameter-sets/$PS/review" \
  -H 'Content-Type: application/json' -d '{"accept":true,"note":"looks fine to me"}'
# 403 {"error":"forbidden","detail":"'parameter:approve' is not granted by your
#      roles (model_developer)", …}

# the validator
curl -u a.mehta:… -X POST "$MAYA/api/v1/parameter-sets/$PS/review" \
  -H 'Content-Type: application/json' \
  -d '{"accept":true,"note":"diagnostics reviewed; condition number acceptable"}'
# 200 {"state":"approved","approved_by":"a.mehta", …}
```

In the SDK that is `maya.parameters.review(ps_id, accept=True, note="…")`, and
on the screen it is *step three* of the same card, which lists every version with
what it may run on and what is waiting.

Ask what the version may run on at any time:

```bash
curl -u "$USER:$PASS" "$MAYA/api/v1/parameters?urn=maya://model/credit.pd.smallbiz&semver=1.1.0"
```

```json
{"model_version": "maya://model/credit.pd.smallbiz@1.0.0",
 "recorded": 1, "approved": 1, "awaiting_approval": 0, "ready": true,
 "detail": "running on 'sb-pd-2026q1' v1, fitted"}
```

**Three rules the register will not bend for a fitted set:** it must name a
warrant MAYA issued, it must name the featureset version that produced it
(`featureset_required` otherwise), and it must not name a snapshot that failed
point-in-time verification. Parameters recorded with `provenance: "declared"` —
a closed form's constants, an elicited weight — need neither a warrant nor a
featureset, because nobody fitted them; they are an assertion by a person and
are attested rather than fitted.

---

### The second person

A fitted set lands `proposed` and inhabits nothing until somebody **other than
its author** accepts it. Skip this and §5 answers `no_approved_parameters:
this version's parameter object is 'estimated_coefficients' and nothing
inhabits it` — which is the register declining to serve a model that has no
numbers rather than serving one with unreviewed numbers:

```bash
PSET=$(curl -s -u "$USER:$PASS" \
        "$MAYA/api/v1/parameters?urn=maya://model/credit.pd.smallbiz&semver=1.1.0" \
       | python3 -c 'import json,sys; print(json.load(sys.stdin)["parameter_sets"][0]["id"])')

curl -u s.iqbal:mrm-pw -X POST "$MAYA/api/v1/parameter-sets/$PSET/review" \
  -H 'Content-Type: application/json' \
  -d '{"accept": true, "note": "diagnostics and condition number reviewed"}'
```

---

## 5 · The scoring warrant an engine runs on

Now the same model resolves. `POST /api/v1/resolve` is the hot path — your engine
calls it, gets a signed descriptor or a refusal with a reason, and never caches
it, because a cached warrant is a revocable authorisation quietly made permanent.

**On the screen.** `/warrants` → *3 — Resolve a scoring warrant*. The verb
dropdown offers all ten verbs, including ones this class will refuse, so that you
meet the refusal rather than a greyed-out control.

**In the SDK.**

```python
d = maya.warrants.resolve(urn="maya://model/credit.pd.smallbiz#champion",
                          principal="svc/origination",
                          declared_use="origination_decision",
                          environment="prod")
```

**With curl.**

```bash
curl -u "$USER:$PASS" -X POST "$MAYA/api/v1/resolve" \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz#champion","environment":"prod",
       "principal":"svc/origination","declared_use":"origination_decision"}'
```

### The point of `P`

The section your engine reads first:

```json
"parameters": {
  "kind": "estimated_coefficients",
  "source": {
    "binding": "parameter_set",
    "parameter_set": "01a0737af0e732dad5541b84792b",
    "name": "sb-pd-2026q1",
    "version": 2,
    "digest": "sha256:5a31438f7462264f14c2c6ce56a7137dcb40833662abac73c56e4d3d372f849b",
    "as_of": 1736899200.0,
    "age_seconds": 51744632.2
  },
  "digest": null,
  "mutable": false
}
```

Every run has to say which point of `P` it is at — that is **L-W8** — and here it
does so by id *and* digest. An engine re-derives the digest from the values it
loaded rather than comparing MAYA's stored digest against the warrant's copy;
those are two copies of one claim and would agree happily over values somebody
had edited underneath them.

`as_of` and `age_seconds` are carried so nobody has to subtract two epochs to
discover they are running last quarter's fit. For a **calibration** the stamp is
compulsory — **L-W11** refuses a `calibration_set` whose set has no `as_of`,
*"so nothing downstream can tell a current calibration from a stale one"* — and
the age is the number a policy gate reads. The binding differs by where the
numbers live:

| where `P` lives | `parameters.source.binding` |
|---|---|
| an approved set in MAYA's register | `parameter_set`, with id, digest and `as_of` |
| inside the artifact (a graph, a PMML document) | `artifact`, with the artifact's digest — and **L-W12** refuses it without one |
| carried in the warrant (a closed form's constants) | `declared` |
| a vendor black box | `vendor_internal` |

### The operating boundary

`constraints` carries the contract the version was approved under, and travels to
whatever runs the model:

```json
"constraints": {
  "operating_boundary": {"assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
                         "guarantees": [{"key": "gini", "minimum": 0.42}],
                         "on_boundary_violation": "reject"},
  "on_boundary_violation": "reject",
  "resources": {"max_seconds": 30}
}
```

MAYA never sees your inputs, so it cannot check them. A violation is reported by
whatever ran the model, against the boundary the warrant carried.

### Expiry, revocation, grace

```json
"authority": {"principal": "svc/origination", "declared_use": "origination_decision",
              "environment": "prod", "expires_at": 1788644132.2,
              "grace_seconds": 0, "revocation": {"epoch": 0, "check": "monotonic"}}
```

Withdraw everything with one call. It is the kill switch and it is the only
revocation the API offers — every grant on the model, in every environment, for
every principal. **Not by the owner**: `warrant:revoke` is a second-line
permission, and the owner of a model is not the person who takes it out of
service:

```bash
curl -u s.iqbal:mrm-pw -X POST "$MAYA/api/v1/warrants/revoke" \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","reason":"withdrawn pending investigation"}'
# 200 {"revoked":2,"urn":"maya://model/credit.pd.smallbiz",
#      "reason":"withdrawn pending investigation","epoch":2}
```

The next resolution is `410 revoked`, with your reason in it. Every descriptor
carries the epoch it was minted under, so an engine can tell a stale credential
from a current one. And **grace** extends how long a descriptor's authorisation
stays current *when MAYA is unreachable* — never how long a consumer may stay
ignorant of a withdrawal it has already been told about.

> ### The other one that costs an hour
>
> On a model whose parameters live in MAYA's register, resolve **by alias**, not
> by pinned version. `maya://model/credit.pd.smallbiz@1.0.0` is refused
> `409 registry_refused — "no model registered with urn
> maya://model/credit.pd.smallbiz@1.0.0"`, because the lookup for the approved
> parameter set strips a trailing `#alias` and does not strip `@semver`.
> Artifact-backed versions are unaffected, which is why this only shows up on
> models you fitted here. Use `#champion`, or the bare urn.

Two more refusals you will meet, both 403 and both correct: `use_not_approved`
when `declared_use` does not match the grant exactly, and `principal_not_self`
if you ask for a credential in somebody else's name without holding
`warrant:issue`.

---

## 6 · The fourteen admissibility laws

A warrant can be well-formed and still be nonsense. Fourteen laws — `L-W0`
through `L-W13` — decide admissibility, and nine of them have already refused
something above. You do not have to meet the rest one 422 at a time.

`POST /api/v1/grammar/validate` checks a document and reports **every** problem,
because fixing one to be told about the next is the worst possible interface for
a document with ten sections. Here is a hand-written fit warrant with four things
wrong with it:

```bash
cat > my-warrant.json <<'JSON'
{"verb": "fit", "environment": "prod"}
JSON

curl -u "$USER:$PASS" -X POST "$MAYA/api/v1/grammar/validate" \
  -H 'Content-Type: application/json' -d @my-warrant.json
```

```json
{"valid": false, "problem_count": 4, "problems": [
  {"law": "L-W4", "path": "data.outputs",
   "detail": "a 'fit' produces a new parameter object and must say where it goes",
   "remediation": "add an output with sink 'parameter_object'"},
  {"law": "L-W8", "path": "parameters.source",
   "detail": "a 'fit' produces the parameter object, so it cannot also run from 'parameter_set'",
   "remediation": "a fit warrant binds its parameters as 'to_be_fitted'"},
  {"law": "L-W9", "path": "data.inputs[0].as_of",
   "detail": "a featureset read for fitting must say as of when it is read; without it the assembly reads whatever has since arrived",
   "remediation": "pin as_of to the moment the training set is assembled at"},
  {"law": "L-W9", "path": "data.inputs[0].window",
   "detail": "a featureset read for fitting must bound the period it covers",
   "remediation": "give the window a from and a to; the featureset fixes the columns, the warrant fixes the period"}
]}
```

Apply all four remediations — `source` to `to_be_fitted`, an output with sink
`parameter_object`, an `as_of`, a `window` with both ends — and:

```json
{"valid": true, "problem_count": 0, "problems": [],
 "detail": "conforms to the MAYA warrant grammar v1.0"}
```

In the SDK: `maya.warrants.validate(document)`. On the screen: *7 — The fourteen
admissibility laws*, which lists all of them with what each says, where it is
enforced, and a box to paste a document into — plus a *Load the last warrant
resolved* button. The SDK deliberately does **not** validate locally; a second
copy of the vocabulary would disagree with the first eventually, and in the
direction of permitting more.

`GET /api/v1/grammar` publishes the vocabularies and `GET /api/v1/grammar/schema`
the JSON Schema, so an engine in any language can check a warrant before acting
on it.

---

## 7 · Can documents be attached?

Yes — to the **model**, to a **model version**, to a **parameter set**, to a
**featureset version**, to a **feature**, or to a **validation** episode. The
convergence study for one morning's calibration, or the note explaining the fit
that went wrong, belongs on the parameter set:

```bash
printf '# Fit note\n\nsb-pd-2026q1, fitted in the lab.\n' > fit-note.md

PSET=$(curl -s -u "$USER:$PASS" \
        "$MAYA/api/v1/parameters?urn=maya://model/credit.pd.smallbiz&semver=1.1.0" \
       | python3 -c 'import json,sys; print(json.load(sys.stdin)["parameter_sets"][0]["id"])')

curl -u "$USER:$PASS" -X POST "$MAYA/api/v1/attachments" \
  -F "urn=maya://model/credit.pd.smallbiz" \
  -F "kind=model_development_document" \
  -F "title=Fit note - sb-pd-2026q1" \
  -F "semver=1.1.0" \
  -F "subject_type=parameter_set" \
  -F "subject_id=$PSET" \
  -F "file=@fit-note.md;type=text/markdown"
```

```json
{"id": "01a0737af1bdfada507859ec0fd1", "subject_type": "parameter_set",
 "subject_id": "01a0737af0e732dad5541b84792b",
 "kind": "model_development_document", "state": "attached",
 "digest": "sha256:073d80f0ab285b968f9e67e061ce0f15424e91e92e20214afedf3d7b59f329d7",
 "text_indexed": true}
```

Multipart, because that is how a file arrives. It lands `attached` and is
accepted or rejected by somebody other than whoever filed it, through
`POST /api/v1/attachments/{id}/review`. In the SDK the same call is
`maya.attachments.attach(...)`.

**What you cannot attach a document to is a warrant.**

```json
{"error": "unknown_subject",
 "detail": "'warrant' is not something a document can be about",
 "remediation": "use one of model, model_version, parameter_set, featureset_version, feature, validation; …"}
```

That is deliberate rather than missing. A descriptor is not stored, so there
would be nothing for the document to hang from, and the grant behind it is an
entitlement rather than a thing anybody writes a report about. Everything you
would want to say about a fit belongs on the **parameter set the fit produced**,
which is stored, immutable, digested, and reachable from the warrant that made it.

---

## What to read next

| | |
|---|---|
| [Defining a model](/tutorials/defining-a-model) | the version and the kernel every warrant is about |
| [Features](/tutorials/features) | the two clocks the `pit_rule` in a fit warrant is written in |
| [Featuresets](/tutorials/featuresets) | the presentation of `X` a fit warrant names |
| [The model package](/tutorials/model-package) | what an examiner is handed, parameter sets and all |
| [Everything, end to end](/tutorials/end-to-end) | the whole path with this section in its place |
| [Warrants](/help/warrants) | the reference card — every field, every refusal |
| [Featuresets and parameters](/help/featuresets-and-parameters) | the register the numbers land in |
| [API reference](/help/api-reference) | every endpoint used above |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE.
*Not legal, regulatory or financial advice — see NOTICE §4.*
