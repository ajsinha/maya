---
title: A linear regression, end to end
slug: linear-regression-end-to-end
section: Worked models
order: 48
icon: graph-up
summary: A small-business PD scorecard from an empty register to a champion serving in production — features on two clocks, a featureset that pins its bytes, a fit warrant, MAYA's own least-squares estimator, four eyes on the coefficients, and a monitor that will not report a number until the cohort has matured. The ordinary case, done completely, with the condition number read properly.
audience: Data scientists, Model developers, Validators
---

# A linear regression, end to end

This is the plainest model in the book and the one worth doing first, because
every later tutorial is this one with a different way of filling `P`.

**What you are building.** A 12-month probability-of-default scorecard for a
small-business credit book. Two regressors, one label, three coefficients — and
every control the platform has, applied to them.

| | |
|---|---|
| `P` is | an intercept and two slopes |
| Filled by | ordinary least squares, in MAYA's own estimator |
| `parameter_kind` | `estimated_coefficients` |
| `fit_procedure` | `estimate` |
| Derived class | **T2** — statistically estimated |
| Runtime | `estimator`, family `ols` |
| Where `P` lives | in the register, as a record |

The last row is what separates this tutorial from
[the neural network](/tutorials/neural-network-end-to-end): three numbers are a
*record*, twenty million are a *file*, and `MAX_INLINE_VALUES = 4096` in
`core/parameters/common.py` is the exact line where one becomes the other.

---

## 0 · The four people

Duties are separated. Doing this as one account gets you refused, which is the
platform working rather than failing.

```bash
curl -u admin:admin123 -X POST localhost:5006/api/v1/principals \
  -H 'Content-Type: application/json' \
  -d '{"username":"d.raman","display_name":"D Raman",
       "roles":["model_developer"],"password":"dev-pw"}'
```

Repeat for `j.okafor` (`model_owner`), `a.mehta` (`validator`), `s.iqbal`
(`model_risk_manager`) and two service accounts, `svc/model-lab` and
`svc/origination` (`service`).

**Who may do what is not decoration here, and the surprises are worth knowing
before you hit them.** A `model_developer` may create versions and record
parameters but holds no `warrant:issue`. A `validator` may approve parameters
and seal a featureset but holds `document:review` and **not** `document:attach`
— the first line files, the second line accepts. And `monitor:define` sits with
the owner and the model risk manager, not with the validator. `GET /api/v1/me`
answers all of this for whoever is asking.

---

## 1 · The features

A feature is a governed object with an owner, a type and a lineage — not a
column somebody added to a table.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' \
  -d '{"name":"dscr","entity":"borrower_id","dtype":"numeric",
       "description":"Debt service coverage ratio, trailing 12m",
       "owner":"person/j.okafor"}'
```

Do the same for `turnover` (numeric) and `defaulted` (integer — the label). The
response carries `possible_duplicates` beside the feature: near-matches on name
and description, offered rather than enforced, because the twelfth definition of
*turnover* is how a feature store becomes a spreadsheet with an API.

> **Why the label is a feature too.** It has an owner, a definition and an
> ingest clock like anything else, and pretending otherwise is how a label gets
> restated without anybody noticing that a training set moved.

---

## 2 · The values, with both clocks

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/feature-views \
  -H 'Content-Type: application/json' \
  -d '{"name":"sb_financials","entity":"borrower_id","owner":"person/j.okafor",
       "features":["dscr","turnover","defaulted"]}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/feature-views/sb_financials/data \
  -H 'Content-Type: text/csv' --data-binary @financials.csv
```

```csv
entity_id,event_ts,ingest_ts,dscr,turnover,defaulted
B0001,1711843200,1716163200,1.42,2500000,0
B0002,1711843200,1716163200,0.88,410000,1
```

`event_ts` is when the fact was **true** (31 March, the quarter it describes).
`ingest_ts` is when it became **known** (20 May, when they filed).

CSV is accepted on the way *in* and never written on the way out, and the
asymmetry is deliberate: a CSV is what a person has, so refusing one means
somebody converts by hand and the conversion is where the mistakes live — but a
CSV cannot carry a type, so a feature exported as one comes back as text and the
two clocks come back as strings. Arrow, Parquet and NDJSON are accepted too.

A file missing either clock is refused before a row is stored:

```json
{"error": "assembly_rejected",
 "detail": "the upload is missing ingest_ts. feature rows carry two clocks —
            event_ts (when the fact was true) and ingest_ts (when the platform
            learned it) — and an entity key; without them the rows cannot be
            assembled point-in-time, and a set built from them could not be
            shown free of leakage"}
```

The whole upload becomes **one view version**, because a version is what a
featureset pins and half a version is not something anybody can pin.

---

## 3 · The featureset

A featureset declares a **schema**; a version **fills** it.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' \
  -d '{"name":"sb_core","entity":"borrower_id",
       "slots":{"dscr":"numeric","turnover":"numeric","defaulted":"integer"},
       "label_slot":"defaulted","outcome_window_days":365}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/sb_core/versions \
  -H 'Content-Type: application/json' \
  -d '{"bindings":{"dscr":"dscr","turnover":"turnover",
                   "defaulted":"defaulted"}}'
```

`sb_core@v1` now always resolves to the same bytes, because every binding names
a Delta version rather than a path. `GET /api/v1/featuresets/sb_core/versions/1`
returns the whole assembly plan — slots, namespaces, pins, the label binding,
the point-in-time rule — and
`GET …/versions/1/restatements` answers the neighbouring question a reviewer
actually asks before comparing two runs: *has anything underneath this version
been written to since?* The version still reads the bytes it pinned. That is
what the pin is for; this is how you find out the ground moved.

---

## 4 · The version, then the tier

Create the version first. The tier assessment reads the **latest version's
derived class** as one of its complexity facts, so assessing an empty model
computes complexity against `T0` and quietly under-tiers everything.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","name":"SB PD",
       "model_class":"credit.pd.scorecard","domain":"credit",
       "owner":"person/j.okafor","legal_entity":"LE-US-01",
       "purpose":"12-month PD at origination"}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver":"1.0.0",
       "kernel":{"parameter_kind":"estimated_coefficients",
                 "fit_procedure":"estimate",
                 "runtime":"estimator",
                 "entry":{"family":"ols","target":"defaulted",
                          "regressors":["dscr","turnover"]},
                 "input_schema":[{"name":"dscr","dtype":"numeric"},
                                 {"name":"turnover","dtype":"numeric"}],
                 "output_schema":[{"name":"pd_12m","dtype":"numeric"}]},
       "contract":{"assumptions":[{"key":"dscr","minimum":-5,"maximum":20},
                                  {"key":"turnover","minimum":0}],
                   "guarantees":[{"key":"auc","minimum":0.62}]}}'

curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure":2000000000,"purpose_class":"regulatory_capital",
       "feature_count":2,"interpretable":true}'
```

```json
{"tier": 2, "materiality": "material", "complexity": "simple",
 "required_controls": ["independent_validation","biennial_review",
                       "quarterly_monitoring","delegated_approval",
                       "full_documentation"],
 "rationale": "materiality=material (exposure 2,000,000,000 in band material,
               purpose regulatory_capital); complexity=simple (class T2);
               tau(material,simple)=Tier 2 under ruleset 2026.09.1",
 "ruleset_version": "2026.09.1"}
```

Read what that says. Materiality is a **join** — the more severe of the exposure
band and the purpose class — so a £2bn regulatory-capital model is *material*
either way. Complexity is a **meet** over declared components, and a two-feature
interpretable T2 scores zero on every one of them, so it is *simple*. Tier 2 is
what those two together map to, and the map is monotone: nothing you can say
about this model makes it a lower tier without changing one of the facts.

Tier 2 is why §8 needs two signatures, and it is why a resolved warrant for this
model lives 300 seconds with no grace. The
[neural network](/tutorials/neural-network-end-to-end) reaches Tier 1 on
complexity alone at a fifth of the exposure, which is the whole argument for
keeping the two orders apart.

**You never declare the trainability class.** It is derived from
`parameter_kind` and `fit_procedure` in
`core/domain/algebra.py::trainability_class`, which is why asking this model for
its training set is a sensible question and asking
[a closed-form pricer](/tutorials/derivative-pricing-end-to-end) the same thing
is a type error.

---

## 5 · The fit warrant

Nothing reads training data without one.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","environment":"prod",
       "principal":"svc/model-lab","declared_use":"model_development",
       "featureset":"sb_core","featureset_version":1,
       "window":{"from":1546300800,"to":1735603200},"as_of":1736899200}'
```

There is no `verb` field, and its absence is the design. A fit warrant's verb is
always `fit`; whether that *means* estimate, calibrate, train or configure comes
from the version's `fit_procedure`, not from the caller. A request cannot ask
for a kind of fitting the kernel does not do.

Three laws are checked before it is signed:

- **L-W3** — training data must come from a binding that can answer *what was
  known at time t*: `featureset`, `feature_namespace` or `dataset_snapshot`,
  and nothing else.
- **L-W9** — the read must be bounded in **both** clocks. An `as_of` of `0` is
  accepted, because 1970-01-01 is a real instant; an absent one is not.
- **L-W10** — the featureset must provide what the kernel declares it reads.

The third is the one people meet. Add a regressor to the kernel and forget the
featureset:

```json
{"error": "schema_not_satisfied",
 "detail": "'sb_core' does not provide sector_code, which this version declares
            it reads",
 "remediation": "bind a featureset whose schema covers the kernel's inputs, or
                 create a model version whose input schema matches this set —
                 adding a regressor is a model change, not a data change"}
```

That sentence is the whole point of separating `X` from `f`. It is the same
comparison `L-12` makes at an alias move and the same one an `input_to` edge
makes between two models: `core.domain.lattice.refines`, asked in three places
and implemented once.

The descriptor that comes back carries the slots, their types, which feature and
view version fills each, the entity, the grain, the label binding and the
outcome window. Names and types — never values. A signed credential is not a
wire format for a dataset.

---

## 6 · The fit

MAYA can run this one itself, because the kernel names the `estimator` runtime.
Assemble the training set first: the featureset supplies the columns, you supply
the **spine** and the `as_of`.

```bash
curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/sb_core/training-sets \
  -H 'Content-Type: application/json' \
  -d '{"version":1,"as_of":1736899200,"name":"sb_core-2025",
       "spine":[{"entity_id":"B0001","label_ts":1730000000,"label":0},
                {"entity_id":"B0002","label_ts":1730000000,"label":1}]}'
```

Each row is assembled by the point-in-time rule: the latest fact true by
`label_ts` and known by `min(label_ts, as_of)`. Both bounds are kept because
they refuse different things — `label_ts` is what the model could have known
when the decision was made, `as_of` is what the platform could have known when
the set was built. The `min` is the reproducibility guarantee: **every `as_of`
at or after the label gives the same answer**, so this set re-assembled a year
from now is byte-identical however many restatements arrive in between.

The snapshot comes back with `pit_verified`, and it is a gate rather than a
label:

```json
{"error": "snapshot_not_pit_verified",
 "detail": "snapshot 'sb_core-2025' did not pass point-in-time verification;
            suspected leakage in recovery_flag",
 "remediation": "assemble it again from a featureset version whose slots cannot
                 see the label, or fix the leak the report names; a model
                 fitted on leaked data scores well and then does not"}
```

A refusal rather than a warning, and the reason is specific: the diagnostics
travel with the parameter set, so a warning would print *possible leakage* in a
field beside coefficients somebody is about to approve.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/parameter-fits \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","snapshot_id":"01a0...",
       "environment":"prod","principal":"svc/model-lab",
       "declared_use":"model_development",
       "window":{"from":1546300800,"to":1735603200},
       "name":"ols_v1","kind":"coefficients"}'
```

```json
{"id": "ps-8817", "name": "ols_v1", "version": 1, "state": "proposed",
 "provenance": "fitted", "kind": "coefficients",
 "values_inline": {"intercept": 0.118, "dscr": -0.061,
                   "turnover": -8.0e-9},
 "diagnostics": {
   "n": 8420, "k": 3, "degrees_of_freedom": 8417,
   "r_squared": 0.11, "adjusted_r_squared": 0.1098,
   "residual_std_error": 0.1914,
   "standard_errors": {"intercept": 0.0107, "dscr": 0.0080,
                       "turnover": 1.1e-9},
   "t_statistics": {"intercept": 11.03, "dscr": -7.63, "turnover": -7.27},
   "condition_number": 34.9,
   "target": "defaulted", "regressors": ["dscr","turnover"],
   "family": "ols", "rows": 8420, "delta_version": 12,
   "pit_verified": true, "fitted_in_ms": 41.2},
 "digest": "sha256:1c9a…",
 "descriptor_id": "…", "family": "ols",
 "fitted_from": {"snapshot": "sb_core-2025", "rows": 8420,
                 "featureset": "sb_core", "featureset_version": 1}}
```

The order of what happened matters, and it is the four steps in
`core/parameters/fitting.py`: **the warrant resolved first**, then the snapshot
was read at the Delta version it pinned rather than at the head, then the
estimator ran through the ordinary runtime dispatch, then the result landed
`proposed`. Authority before data — a read performed under an authority that
turns out not to exist has already happened.

### Reading the diagnostics, which is the actual skill

**The condition number, before anything else.** It is the ratio of the largest
to the smallest singular value of the design matrix, and it is an *amplifier*: a
relative perturbation of size ε in the data moves the coefficients by up to
`κ · ε`. As a rule of thumb you lose `log₁₀ κ` decimal digits of precision in
the coefficients.

| κ | What it means |
|---|---|
| **34.9** | you lose about one and a half digits. The regressors are close to independent, the coefficients are a property of the world, and each one can be interpreted on its own |
| **~400** | two and a half digits. Interpret the coefficients jointly or not at all; the fit is fine, the *attribution* is not |
| **~4,000** | three and a half digits, and a 0.1% change in one borrower's turnover moves a coefficient in the third significant figure. These numbers are a solution to *this sample*. Refit on a different year and the signs can move |
| **`null`** | the smallest singular value was zero — but you never see this, because rank deficiency is refused before the solve |

MAYA solves by `lstsq` (QR) rather than by inverting `X'X`, and the reason is
exactly this number: the normal equations **square** the condition number, so a
design at κ = 400 is solved at κ² = 160,000, and a scorecard with two correlated
regressors is precisely where that stops being a textbook remark.

**Then the standard errors, not the R².** `dscr` at −0.061 with a standard error
of 0.0080 is a t of −7.6: real, and the sign is the one theory predicts. An R²
of 0.11 on a 0/1 default label is neither good nor bad — it is the wrong
statistic, because ordinary least squares on a binary outcome is a *linear
probability model*: its errors are heteroskedastic by construction, and its
fitted values can leave `[0, 1]` entirely. At a DSCR of 3.0 this fit predicts a
probability of default of **−6.7%**. MAYA will fit it and will not stop you.
The validator should, and §7 is where that happens.

MAYA does not judge the fit. It puts the numbers where somebody who can has to
look at them, and records that they looked.

### The refusals this family actually produces

Every one of these is in `core/execution/runtimes/estimator.py`, and every one
is a thing that goes wrong on a real scorecard.

| Refusal | When |
|---|---|
| `too_few_rows` | fewer than 30 rows. "A fit this small reports diagnostics that look like results" |
| `not_identified` | `n ≤ k`. The system is underdetermined, and any answer would be one of infinitely many |
| `collinear_regressors` | the design matrix is rank-deficient. Refused rather than letting the solver pick one of the infinitely many answers — a pseudo-inverse returns *an* answer, and it is not the one anybody meant |
| `target_is_a_regressor` | `defaulted` appears in `regressors`. The fit would predict the answer from the answer |
| `value_not_numeric` | a null, a boolean or a NaN in a column. **Not** dropped and **not** zeroed: dropping changes the population the fit speaks for without saying so, and the featureset's fill policy is where that decision belongs, because somebody chose it there and it is on the record |
| `fit_underspecified` | the kernel entry names no target or no regressors |

### Or fit it somewhere else

```bash
curl -u svc/model-lab:svc-pw \
  "localhost:5006/api/v1/featuresets/sb_core/versions/1/data?as_of=1736899200&format=parquet" \
  -o training.parquet

curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/parameters \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","semver":"1.0.0",
       "name":"ols_v1","kind":"coefficients","provenance":"fitted",
       "values":{"intercept":0.118,"dscr":-0.061,"turnover":-8.0e-9},
       "featureset":"sb_core","featureset_version":1,
       "warrant_id":"<the grant id>",
       "window":{"from":1546300800,"to":1735603200},"as_of":1736899200,
       "diagnostics":{"r_squared":0.11,"condition_number":34.9,"n":8420}}'
```

`as_of` is required on that export and is not defaulted, because an export is a
claim about what was known at a moment and defaulting it would make that moment
whatever the clock said when somebody happened to call.

A **fitted** set is accepted only against a warrant MAYA issued, and it must
name the featureset version it came from — `warrant_required` and
`featureset_required` are separate refusals because they answer separate
questions. Send the diagnostics: a set delivered without them asks somebody to
approve a number on trust.

---

## 7 · Four eyes on the numbers

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/parameter-sets/ps-8817/review \
  -H 'Content-Type: application/json' \
  -d '{"accept":true,
       "note":"condition number 34.9, signs as expected; LPM fitted values
               clipped downstream, noted as a finding"}'
```

Not by whoever recorded it:

```json
{"error": "self_approval",
 "detail": "d.raman recorded these parameters and cannot also approve them",
 "remediation": "a parameter set changes what the model does; approval is by
                 somebody other than whoever produced it"}
```

An approved set is immutable, because a run cited it. A second review is refused
with `already_reviewed`; the way to change your mind is a new set.

Then compile the record of the fit:

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/training-records/ps-8817
```

Six sections, all of them already in the register — what this is, under what
authority, what it read, what it produced, what the fit reported, who accepted
it. Compiled rather than written, so it exists whether or not anybody had time.
`GET /api/v1/training-records/ps-8817/preview` renders it without authoring it.

**Recording new parameters does not create a new model version.** The kernel did
not change. That is what lets a recalibration *procedure* be approved once
rather than pretending a committee meets every morning — and it is what the
[Hull–White tutorial](/tutorials/hull-white-end-to-end) leans its whole weight
on.

---

## 8 · Approve, promote, freeze

```bash
APPROVAL=$(curl -su s.iqbal:mrm-pw -X POST localhost:5006/api/v1/version-approvals \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","semver":"1.0.0",
       "statement":"Tier 2 initial approval"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/version-approvals/$APPROVAL/sign \
  -H 'Content-Type: application/json' -d '{"role":"model_risk_manager"}'
curl -u a.mehta:val-pw  -X POST localhost:5006/api/v1/version-approvals/$APPROVAL/sign \
  -H 'Content-Type: application/json' -d '{"role":"validator"}'

curl -u s.iqbal:mrm-pw -X PUT localhost:5006/api/v1/models/credit.pd.smallbiz/aliases \
  -H 'Content-Type: application/json' \
  -d '{"environment":"prod","alias":"champion","semver":"1.0.0",
       "justification":"first production version"}'

curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/featuresets/sb_core/seal \
  -H 'Content-Type: application/json' -d '{"note":"fitted against; frozen"}'
```

Tier 1 and Tier 2 versions need a quorum of two people in two named roles, and
the same person may not sign twice under two hats — a quorum is a number of
people, not a number of roles. Approving the version directly instead is refused
with `quorum_required`, and the refusal names the endpoint that does the right
thing rather than only saying no. Approving before *assessing* is refused with
`no_tier`, because choosing your own control depth is the one thing tiering
exists to prevent.

The alias move is a **proof obligation**: the replacement's contract must refine
the incumbent's (L-7) and its schemas must satisfy variance (L-12).

---

## 9 · Serve it

A standing entitlement first — resolution refuses `no_entitlement` without one,
and that is the check every consumer passes through however it was wired.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz#champion","environment":"prod",
       "principal":"svc/origination","declared_use":"origination_decision"}'

curl -u svc/origination:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz#champion","environment":"prod",
       "principal":"svc/origination","declared_use":"origination_decision",
       "inputs":{"features":{"dscr":1.4,"turnover":250000}}}'
```

```json
{"descriptor_id": "wd-4419",
 "model_urn": "maya://model/credit.pd.smallbiz",
 "version": "1.0.0",
 "prediction": {"family": "ols", "prediction": 0.0306, "target": "defaulted"},
 "boundary_ok": true, "boundary_violations": [], "latency_ms": 3.1}
```

Three things in that answer are the platform rather than the arithmetic.

**The digest is re-derived.** The warrant names the approved parameter set by id
and digest, and the engine recomputes that digest from the values before running
— it does not compare the stored digest against the warrant's copy, because
those are two copies of one claim and would agree happily over values somebody
had edited underneath them. A disagreement is `parameter_mismatch`, and it is a
409 rather than a 422 on purpose: nothing about the request is wrong, the
platform's own state is.

**`boundary_ok` is the contract.** `dscr` outside `[-5, 20]` is a
`boundary_violation` before the estimator is touched, because outside the
assumption the guarantee is void, and a scorecard silently extrapolating to a
DSCR of 80 is exactly the failure the contract exists to name.

**A declared use that does not match the grant is refused** with
`use_not_approved`, before the model runs and before the parameters are read.

---

## 10 · Watch it age

Monitors are defined by the owner or the model risk manager, not by the
validator, and a monitor's `test_key` must come from the catalogue — a
definition error is caught when somebody writes it down, not at three in the
morning when the batch fails.

```bash
curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","name":"score PSI",
       "kind":"score_drift","test_key":"stability.psi",
       "threshold":{"max":0.25},"owner":"person/j.okafor",
       "cadence_days":7,"breach_severity":"Medium","escalate_after":3,
       "reference":{"sample":[0.02,0.03,0.05,0.08,0.11]}}'

curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.smallbiz","name":"12m AUC",
       "kind":"performance","test_key":"discrimination.auc",
       "threshold":{"min":0.62},"owner":"person/j.okafor",
       "cadence_days":30,"label_delay_days":365,"breach_severity":"High"}'
```

A `performance` monitor with no `label_delay_days` is refused at definition:

```json
{"error": "label_delay_required",
 "detail": "a 'performance' monitor compares predictions to outcomes, so it
            must declare how long those outcomes take to arrive",
 "remediation": "set label_delay_days; for a 12-month PD model that is 365"}
```

And the second monitor **will not evaluate** until a cohort has matured:

```json
{"error": "cohort_immature",
 "detail": "no outcomes have matured yet — 0 of 4,180 rows have matured
            (365 day outcome window)",
 "remediation": "wait for the outcome window to close; the earliest maturity is
                 2026-11-14"}
```

Refused rather than annotated. A PSI number computed on a young cohort is noisy;
an AUC computed on one is **biased**, because the outcomes that arrive early are
the fast defaults, and publishing a biased number beside properly computed ones
is how a monitoring dashboard becomes untrustworthy in a way nobody notices. The
cohort is split row by row rather than batch by batch, so the older end of a
window is measured while the newer end waits.

A breach opens a **finding**, not a dashboard tile, and a Critical finding blocks
warrant resolution by default. Three consecutive breaches escalate the severity
by one level. When the metric recovers the breach closes and **the finding does
not** — a number coming back inside its threshold is not evidence that whatever
moved it was understood.

> **What is not built, and you should know it.** MAYA's telemetry carries two
> streams, `scores` and `outcomes`; it does not carry feature vectors. So an
> `input_drift` monitor evaluated from stored telemetry has nothing to read, and
> per-feature drift means handing the values in yourself at
> `POST /api/v1/monitors/<id>/evaluate`. The kind exists and the plumbing for it
> does not, and saying so beats a monitor that silently watches the wrong series.

---

## What this tutorial buys the next six

Everything above stays the same in the six that follow. What changes is exactly
one thing: **how `P` is inhabited** — and what that does to the refusals, the
diagnostics and the tier.

| Next | `P` becomes | Read it for |
|---|---|---|
| [GARCH](/tutorials/garch-end-to-end) | three numbers from an iterative search | a fit that can fail while looking like it succeeded, and state at scoring time |
| [Derivative pricing](/tutorials/derivative-pricing-end-to-end) | *empty* | what governance means with nothing to fit, and why the conventions are the risk |
| [Hull–White](/tutorials/hull-white-end-to-end) | a calibration set, refreshed daily | `L-W11`, and 250 governed acts a year that now have a readable record |
| [Monte Carlo](/tutorials/monte-carlo-end-to-end) | parameters **plus a seed** | what a standard error is a standard error *of* |
| [Neural network](/tutorials/neural-network-end-to-end) | millions of weights, as a file | `L-W12`, the content-addressed store, and where the sandbox stops |
| [LLM application](/tutorials/llm-end-to-end) | a configuration you assembled | `L-W13`, and what "the model" even refers to |
