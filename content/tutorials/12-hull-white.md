---
title: A calibrated term-structure model, end to end
slug: hull-white-end-to-end
section: Worked models
order: 51
icon: sliders
summary: Hull–White registered, calibrated against the swaption grid every morning, and served — the case where P is refreshed daily by a solver rather than trained once on history. Law L-W11 and why a calibration that cannot state its as_of cannot be resolved at all; the training record that gives 250 governed acts a year something readable; and an honest account of which parts of approval by exception are built.
audience: Quants, Model developers, Model risk managers
---

# A calibrated term-structure model, end to end

The question this model answers is organisational as much as mathematical: **if
the numbers change every morning, who approves them?**

Answering "a committee" is how banks end up with a control nobody performs.
Answering "nobody" is how a model drifts without a record. The platform's answer
is neither, and §5 sets out exactly how much of it is built.

**What you are building.** A one-factor Hull–White short-rate model, calibrated
each morning to the co-terminal swaption grid, feeding an XVA engine.

| | |
|---|---|
| `P` is | mean reversion `a`, and a term structure of `σ` |
| Filled by | a solver, against market quotes |
| `parameter_kind` | `calibration_set` |
| `fit_procedure` | `calibrate` |
| Derived class | **T1** — market-calibrated |
| Runtime | `quantlib` |
| Cadence | daily |

---

## 1 · Why T1 is its own class

A trained model learns a relationship from history and is expected to hold for a
while. A calibrated model **reproduces today's market** and is expected to be
wrong tomorrow — that is not degradation, it is the design.

| | Trained (T2/T3) | Calibrated (T1) |
|---|---|---|
| The fitting morphism `φ` | an estimator over a dataset snapshot | a solver over the calibration instruments, re-run daily |
| Refit cadence | occasional, an event | daily, a process |
| Drift means | the world moved away from the fit | the calibration stopped fitting |
| The signal | performance against realised outcomes | the residual across the grid |
| What is approved | each parameter set, individually | the procedure — and each set still needs a second signature |

Recording new parameters is never a new model version. For a T2 that is a
convenience; for a T1 it carries the operational load of the whole design.
**Two hundred and fifty parameter sets a year, one approved kernel.**

---

## 2 · The calibration instruments are the input

The market quotes are governed exactly like features, because they are the data
the parameters come from.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/features \
  -H 'Content-Type: application/json' \
  -d '{"name":"swaption_vol","entity":"grid_point","dtype":"numeric",
       "description":"Normal implied vol, co-terminal swaption grid",
       "owner":"person/j.okafor"}'

curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/feature-views \
  -H 'Content-Type: application/json' \
  -d '{"name":"swaption_grid","entity":"grid_point","owner":"person/j.okafor",
       "features":["swaption_vol"]}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/feature-views/swaption_grid/data \
  -H 'Content-Type: text/csv' --data-binary @grid_2026-03-31.csv
```

```csv
entity_id,event_ts,ingest_ts,swaption_vol
1Yx5Y,1743379200,1743382800,0.00612
2Yx5Y,1743379200,1743382800,0.00658
10Yx10Y,1743379200,1743382800,0.00704
```

The two clocks are doing real work here even though the lag is minutes. A
morning calibration snapped at 07:00 must **not** see a quote that arrived at
09:30, and a re-run of yesterday's calibration must see yesterday's snap. That
is not a convention: because the point-in-time read bounds ingestion at
`min(event, as_of)`, a re-run at any later moment returns exactly the same
quotes. Without the `min`, a re-run would quietly *improve* on the original —
the least useful kind of reproducibility, because the numbers then agree with
nothing, including themselves.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' \
  -d '{"name":"hw_calibration_grid","entity":"grid_point",
       "slots":{"swaption_vol":"numeric"},"grain":"daily"}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/featuresets/hw_calibration_grid/versions \
  -H 'Content-Type: application/json' \
  -d '{"bindings":{"swaption_vol":"swaption_vol"}}'
```

---

## 3 · The version, and Tier 1

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.rates.hullwhite","name":"Hull-White 1F",
       "model_class":"markets.term_structure","domain":"markets",
       "owner":"person/j.okafor","legal_entity":"LE-UK-01",
       "purpose":"Short-rate dynamics for XVA and Bermudan exercise"}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/markets.rates.hullwhite/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver":"1.0.0",
       "kernel":{"parameter_kind":"calibration_set",
                 "fit_procedure":"calibrate",
                 "runtime":"quantlib",
                 "entry":{"instrument":"swaption","pricing_engine":"black"},
                 "input_schema":[{"name":"swaption_vol","dtype":"numeric"}],
                 "output_schema":[{"name":"npv","dtype":"numeric"}]}}'

curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/markets.rates.hullwhite/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure":12000000000,"purpose_class":"regulatory_capital",
       "feature_count":1,"interpretable":true}'
```

Tier 1: critical exposure, and materiality dominates the map. So a two-role
quorum on the version, and every resolved warrant lives **sixty seconds with no
grace**. That last number is not arbitrary either — grace extends how long a
descriptor's *authorisation* stays current when the platform is unreachable, and
at Tier 1 the answer is that it does not.

---

## 4 · Calibrate, and deliver the set

MAYA's captive engine does not solve Hull–White. That is deliberate: a
calibration engine is a serious piece of quant software and the register is not
the place for it. So the bank's own engine calibrates and delivers the result
back.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.rates.hullwhite","environment":"prod",
       "principal":"svc/rates-calib","declared_use":"daily_calibration",
       "featureset":"hw_calibration_grid","featureset_version":1,
       "window":{"from":1743379200,"to":1743379200},"as_of":1743382800}'
```

There is no `verb` on that request, and it would be wrong if there were. A fit
warrant's verb is always `fit`; that this fit *is* a calibration comes from the
version's `fit_procedure`, which is also what makes the class T1. The engine
reads the pinned grid, solves, and posts back:

```bash
curl -u svc/rates-calib:svc-pw -X POST localhost:5006/api/v1/parameters \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.rates.hullwhite","semver":"1.0.0",
       "name":"hw_2026-03-31","kind":"calibration_set",
       "provenance":"calibrated",
       "values":{"mean_reversion":0.031,
                 "sigma_1y":0.0062,"sigma_5y":0.0071,"sigma_10y":0.0069},
       "featureset":"hw_calibration_grid","featureset_version":1,
       "warrant_id":"<the grant id>","as_of":1743382800,
       "diagnostics":{"rmse_bp":0.42,"max_abs_error_bp":1.7,
                      "worst_point":"10Yx10Y","instruments":36,
                      "converged":1,"iterations":18,
                      "prior_mean_reversion":0.030}}'
```

`provenance: "calibrated"` is not decoration. It says the numbers reproduce a
market rather than summarise a history, and every downstream reader branches on
it — the monitoring, the reporting, the validator's checklist and the training
record in §6.

> **One asymmetry worth knowing.** Only `fitted` sets are *required* to name a
> warrant; `NEEDS_WARRANT` in `core/parameters/common.py` is that one value.
> A calibrated set may arrive without one, which is coherent — the procedure is
> approved, not each morning's solve. Quote it anyway, and §6 shows exactly what
> it costs you not to.

### The `as_of` is not optional, and the consequence is total

`as_of` on that parameter set is what **L-W11** requires, and it is worth
understanding rather than satisfying.

A calibrated model reproduces a market rather than summarising a history, so the
moment it was solved for is part of what the numbers *mean*. Two warrants naming
this same set on different mornings are not the same run. Without the stamp,
staleness is silent: the engine runs yesterday's swaption fit against today's
book, produces an entirely ordinary-looking number, and nothing in the record
says which market it came from.

Omit it and this model becomes **unservable**, which is stronger than a warning
and stronger than a finding. `check_calibration_as_of` runs before the
signature, so no descriptor is ever minted:

```json
{"law": "L-W11", "path": "parameters.source.as_of",
 "detail": "this model's parameters are a calibration, and the warrant does not
            say what they were calibrated as of, so nothing downstream can tell
            a current calibration from a stale one",
 "remediation": "record the calibration's as_of on the parameter set; a set
                 delivered without one cannot be told apart from any other solve
                 of the same grid"}
```

The law requires the age to be **statable**, not small — how old is too old
depends on your cadence, and that is a policy question rather than a law. So the
resolved warrant carries both the stamp and the arithmetic, because a reader
should not have to subtract two epochs to discover they are running last
quarter's fit:

```json
"parameters": {
  "kind": "calibration_set",
  "mutable": false,
  "source": {"binding": "parameter_set",
             "parameter_set": "ps-8817",
             "name": "hw_2026-03-31",
             "version": 1,
             "digest": "sha256:1c9a…",
             "as_of": 1743382800,
             "age_seconds": 3600}}
```

A **fit** warrant is exempt, and the exemption is not a loophole: the
calibration being solved for cannot state when it was solved, because it does
not exist yet.

Two more things about that block. `mutable: false` for every verb except `fit`,
because a fit writes a *new* parameter object rather than editing this one. And
the digest is **re-derived** from the values by the engine before anything runs,
never compared against the stored copy — those would be two copies of one claim,
and they would agree happily over values somebody had edited underneath them.

### Reading a calibration's diagnostics

There is no R², no AUC and no convergence-of-a-likelihood here. There is a
**residual surface**, and three numbers describe it.

**`rmse_bp` is the fit; `max_abs_error_bp` is the risk.** An RMSE of 0.42bp over
36 instruments with a worst point at 1.7bp is a grid fitting comfortably. The
same RMSE with a worst point at 9bp is a *different* situation with the same
average: one instrument is being mispriced by an amount that matters, and the
mean is hiding it. Always read them together, and always with `instruments` —
0.42bp over 36 points and 0.42bp over 4 points are not the same claim.

**`worst_point` is the diagnosis.** Where the residual is worst tells you which
kind of problem you have:

| Worst point | What it usually means |
|---|---|
| the same corner every morning — 10Yx10Y for six weeks | a **form** error. One factor cannot fit both the level and the curvature of that surface, and no amount of re-solving will fix it. This is a model finding |
| wherever the market moved overnight | a **data** error, or a stale quote in the grid. Check the snap before touching the model |
| scattered, different each day | the solver is finding different local minima. Look at `iterations` and at the starting point, not at the market |

**Parameter stability is the fourth diagnostic, and it lives across sets rather
than in one.** Mean reversion moving from 0.030 to 0.031 overnight is a market.
Mean reversion moving from 0.030 to 0.042 overnight is almost always a different
local minimum, and the giveaway is that `rmse_bp` barely changed — the objective
is flat in `a` over a wide range, so the solver is nearly indifferent and the
number you get is whichever basin it started in. That is why
`prior_mean_reversion` is carried in the diagnostics: the comparison is the
control, and it needs both numbers in one place.

---

## 5 · Approval by exception — and what is actually built

This is the part that makes a daily model workable, and it is the part most
worth being precise about, because it is easy to describe a control that does
not exist.

**What is built, in order.**

**Every set still needs a second signature.** The four-eyes rule on a parameter
set is not relaxed for a T1:

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/parameter-sets/ps-8817/review \
  -H 'Content-Type: application/json' \
  -d '{"accept":true,"note":"rmse 0.42bp, worst 1.7bp at 10Yx10Y, a stable"}'
```

`self_approval` refuses whoever recorded it, and `already_reviewed` refuses a
second verdict — an approved set is immutable because a run cited it.

**Resolution refuses when nothing is approved.** A `warrant:resolve` policy is a
versioned, published gate over facts the platform derives, and
`has_approved_parameters` is one of them:

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/policies \
  -H 'Content-Type: application/json' \
  -d '{"gate":"warrant:resolve",
       "reason":"a Tier 1 calibrated model may not serve production from an
                 unapproved solve",
       "rule":"has_approved_parameters and blocking_findings == 0
               if environment == \"prod\" else True",
       "cases":[{"name":"approved solve in prod",
                 "facts":{"environment":"prod","has_approved_parameters":true,
                          "blocking_findings":0},
                 "expect":"allow"},
                {"name":"nothing approved yet",
                 "facts":{"environment":"prod","has_approved_parameters":false,
                          "blocking_findings":0},
                 "expect":"refuse"}]}'

curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/policies/<id>/publish
```

Read what that policy is and is not:

- **Authoring and publishing are different duties.** A validator drafts; the
  model risk manager puts it in force. A rule authored and enacted by one person
  is a rule nobody reviewed.
- **It is versioned**, so *which rule was in force on 31 March* has an answer,
  and the publish response carries a diff of the outgoing policy's cases
  replayed against the incoming rule — so a change that loosens a gate is
  something somebody decided rather than something somebody discovered.
- **It ships with cases**, at least two, and a policy whose own cases do not pass
  is refused at draft with `cases_do_not_pass`. It also requires **at least one
  refusing case**: a gate that has never refused anything is indistinguishable
  from no gate, and `no_refusing_case` is the check that stops one being written.
- **It can only tighten.** The checks written into the registry are the floor; a
  policy adds a condition and can never remove one.
- **It reads a closed vocabulary.** `has_approved_parameters`, `tier`,
  `environment`, `declared_use`, `blocking_findings`, `attested`,
  `version_status`, `principal` — and nothing else. A name outside that list is
  refused with `unknown_fact` when the rule is *written*, not when a governance
  decision is being made.

**A monitor watches the residual after the fact** — §7.

**And now the gap, stated plainly.** There is **no `parameter_acceptance` gate**.
The gate vocabulary in `core/policy/common.py` is closed to four acts:

```json
{"error": "unknown_gate",
 "detail": "'parameter_acceptance' is not a gate",
 "remediation": "expected one of version:approve, alias:move, model:mutate,
                 warrant:resolve"}
```

So a rule of the form *accept the solve automatically when the RMSE is inside
the envelope, and hold it for a human otherwise* **cannot be written in MAYA
today.** The envelope has to be enforced by your calibration engine before it
delivers — deliver only what passes, and raise a finding for the mornings it
does not — or after the fact by the monitor in §7.

That is a real limitation, and it is the honest shape of "approval by exception"
in this release: the *record* of two hundred and fifty acts a year is complete
and readable, the *four eyes* are enforced on every one of them, and the
*automation* of the accept/hold decision is your engine's job. Naming it beats
describing a gate that would refuse an unknown-gate error.

---

## 6 · The record none of these acts used to have

This is the change that matters most for a daily model, and it could not matter
for any of the other six.

Every other compiled document is about a model or a version. A **training
record** is about a *parameter set*:

```bash
curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/training-records/ps-8817
```

Six sections, compiled from what the register already holds: what this is, under
what authority, what it read, what it produced, what the fit reported, who
accepted it. `GET /api/v1/training-records/ps-8817/preview` renders the same
content without authoring it, which is what the dossier and the export pack use.

**Compiled rather than written, and that is the whole point.** A model
recalibrated every morning produces two hundred and fifty governed acts a year,
each with a warrant behind it and a signature on it, and until now none of them
had a record anybody could read. Compiling means all of them exist whether or
not somebody had time to write one — and the one morning that needs a human note
has somewhere to put it, as an attachment against the same subject:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/attachments \
  -F 'urn=maya://model/markets.rates.hullwhite' \
  -F 'kind=evidence_of_control' \
  -F 'subject_type=parameter_set' -F 'subject_id=ps-8817' \
  -F 'title=31 March: long end would not fit, and what we did' \
  -F 'file=@note_2026-03-31.pdf'
```

`parameter_set` is one of six document subjects, and three of them —
`model_version`, `parameter_set`, `featureset_version` — are **pinned by
construction**: naming one names a fixed thing that cannot move underneath the
document describing it. `featureset` is deliberately absent from the vocabulary,
because a document filed against the set would describe something that has since
moved.

**And here is what the warrant buys you in the record.** The authority section
is compiled from `warrant_id`. Deliver a calibrated set without one — which, per
§4, MAYA permits — and the section is not blank, it is a **named gap**:

> **This section is required and could not be filled.** Nothing in the register
> supports an `authority` section for this parameter set. That is a statement
> about the record of this fit, not about this document.

The record's `coverage` reports `complete: false` and lists `authority` under
`missing_required`. A page that silently omitted what it could not find would
read as complete, and a reader could not tell a thin fit from a thin page.

---

## 7 · What reads what

An XVA engine consumes this model. Which relation you record decides what
propagates, and the two candidates behave differently:

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/model-relations \
  -H 'Content-Type: application/json' \
  -d '{"from_urn":"maya://model/markets.rates.hullwhite",
       "to_urn":"maya://model/xva.pfe","kind":"calibrated_by",
       "note":"the PFE engine runs at the parameters this model solves"}'

curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/blast-radius \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.rates.hullwhite"}'
```

**`calibrated_by` propagates but does not compose.** A calibration solves
parameters rather than handing an output to an input, so there is no wire to
type-check — and the register says so rather than pretending: `COMPOSING` holds
`input_to` alone. Try `input_to` here instead and it is refused, because this
model's output schema is an NPV and the simulation reads a netting set:

```json
{"error": "registry_refused",
 "detail": "… does not compose with maya://model/xva.pfe: what it produces is
            missing {netting_set}. An `input_to` edge asserts that the output
            arrives where the input is read, and an edge that does not
            type-check is a wire to nowhere"}
```

Both relations propagate, so both appear in the blast radius. `challenger_of`
and `benchmark_for` do not, deliberately: a challenger counted as a dependency
would inflate every blast radius it appeared in.

**Recalibrating does not fire the edge**, because the kernel did not change.
Changing the calibration instrument set does, and so does moving to two factors —
and both of those *are* new versions.

---

## 8 · Monitoring: residuals, not accuracy

There is no label to wait for and no accuracy to compute. The signal is the
residual, watched over time:

```bash
curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/markets.rates.hullwhite","name":"grid residual",
       "kind":"performance","test_key":"accuracy.rmse",
       "threshold":{"max":1.0},"owner":"person/j.okafor",
       "cadence_days":1,"label_delay_days":1,
       "breach_severity":"Medium","escalate_after":5}'
```

The "label" is the market quote and the "score" is the model's re-price of the
same instrument, so RMSE in basis points is exactly the residual. MAYA insists
on a `label_delay_days` for anything that compares predictions to outcomes; here
the honest answer is 1, because the comparison is against the morning snap.

**Read the trend, not the day.** An RMSE that has been climbing for six weeks
means the one-factor form is running out of grid — a model finding, not a bad
day — and `escalate_after: 5` says so mechanically: one breach is a data point,
five consecutive ones raise the severity a level and the finding with it. When
the residual comes back inside the threshold the breach closes and **the finding
does not**, because a number returning to range is not evidence that anybody
understood why it left.

---

## Next

[The Monte Carlo engine](/tutorials/monte-carlo-end-to-end) runs at exactly
these parameters — and adds the one thing a calibration does not have: a random
seed, which turns out to be a governed input rather than a detail, and to be
governed by a mechanism other than the one you would expect.
