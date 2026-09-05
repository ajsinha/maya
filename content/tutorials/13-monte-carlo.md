---
title: A Monte Carlo engine, end to end
slug: monte-carlo-end-to-end
section: Worked models
order: 52
icon: shuffle
summary: A counterparty exposure simulation registered, warranted and resolved — where the seed, the path count and the scheme are part of P, the answer is an estimate with an interval rather than a number, and a patch release that passed eleven thousand tests still broke the netting sets. Including an honest account of which law does and does not catch a determinism claim on a container.
audience: Quants, Model developers, Validators
---

# A Monte Carlo engine, end to end

Every model so far had one answer per question. This one does not, and almost
everything interesting follows from that.

**What you are building.** A counterparty credit exposure simulation — potential
future exposure profiles across a netting set, driven by the
[Hull–White](/tutorials/hull-white-end-to-end) parameters calibrated each
morning.

| | |
|---|---|
| `P` is | the model parameters **plus the seed, the path count and the scheme** |
| Filled by | calibration, plus deliberate configuration |
| `parameter_kind` | `calibration_set` |
| `fit_procedure` | `calibrate` |
| Derived class | **T1** |
| Runtime | `container` — the bank's own engine |
| The catch | it is only reproducible if you make it so |

---

## 1 · The seed is a parameter, not a setting

This is the claim the tutorial rests on, so it is worth stating plainly.

A simulation with an unrecorded seed produces a number nobody can reproduce. A
simulation with a recorded seed produces a number anybody can. The seed is
therefore part of what determines the output — which is the definition of a
parameter, and not the definition of a runtime flag.

```bash
curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/xva.pfe/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver":"1.0.0",
       "kernel":{"parameter_kind":"calibration_set",
                 "fit_procedure":"calibrate",
                 "runtime":"container",
                 "entry":{"image":"registry.internal/xva-engine@sha256:9f2c..."},
                 "deterministic":true,
                 "seed":20260331,
                 "input_schema":[{"name":"netting_set","dtype":"structured"},
                                 {"name":"as_of","dtype":"timestamp"}],
                 "output_schema":[{"name":"epe_profile","dtype":"structured"},
                                  {"name":"pfe_97_5","dtype":"numeric"}]}}'
```

`deterministic` and `seed` are kernel keys, not entry keys, and they land on
every warrant this version ever produces:

```json
"operation": {"verb": "simulate", "determinism": "deterministic",
              "seed": 20260331, "mode": "batch"}
```

That is a **claim**, travelling to whatever runs the model, and it is the reason
`deterministic` belongs on the version rather than in a deployment file.

### The law that checks it, and the case it does not cover

`L-W5` refuses a determinism claim that nothing backs:

```json
{"law": "L-W5", "path": "operation.seed",
 "detail": "the 'llm.prompt' runtime is not deterministic unless it is pinned,
            but this operation claims determinism",
 "remediation": "set operation.seed, or declare determinism as 'stochastic'"}
```

**Read the runtime in that message, because it is not this one.**
`STOCHASTIC_RUNTIMES` in `core/execution/grammar/vocabulary.py` holds exactly
two values, `llm.prompt` and `llm.agent`. A `container` is not among them, so
`L-W5` **does not fire for this model**, and a version declaring
`deterministic: true` with no seed is signed without complaint.

That is not an oversight to paper over. MAYA cannot know your container is
stochastic: the platform sees an image digest and an entry point, and inferring
randomness from either would be a guess. The grammar refuses only what it can
*derive*, and here it can derive nothing. So the enforcement has to come from
somewhere else, and it does:

**The seed is in `P`, so it is in the digest.** Change the seed and the
parameter set's digest changes; a changed digest is a different parameter set,
which lands `proposed` and needs a second person. And the engine **re-derives**
the digest from the values before running, so a set edited underneath an
approval is refused rather than run:

```json
{"error": "parameter_mismatch",
 "detail": "the parameter set does not match the digest in the warrant, so the
            numbers about to run are not the numbers that were approved",
 "remediation": "do not run it; re-resolve the warrant and raise a security
                 incident if the values moved without an approval"}
```

409 rather than 422, deliberately: nothing about the request is wrong. The
platform's own state stopped agreeing with itself, and that is a security event.

The general shape is worth carrying: **a law that quantifies over derived facts
covers what the platform can see, and everything else has to be made structural
rather than checked.** Putting the seed in `P` is the structural version.

---

## 2 · The parameter set carries the whole configuration

```bash
curl -u svc/xva-calib:svc-pw -X POST localhost:5006/api/v1/parameters \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/xva.pfe","semver":"1.0.0",
       "name":"pfe_2026-03-31","kind":"calibration_set",
       "provenance":"calibrated",
       "values":{"mean_reversion":0.031,"sigma_1y":0.0062,
                 "paths":50000,
                 "seed":20260331,
                 "scheme":"sobol",
                 "time_grid":"monthly_to_10y_then_annual",
                 "antithetic":1,
                 "brownian_bridge":1},
       "featureset":"hw_calibration_grid","featureset_version":1,
       "warrant_id":"<the grant id>","as_of":1743382800,
       "diagnostics":{"standard_error_pfe":0.0031,
                      "standard_error_epe":0.0009,
                      "batches":50,"paths_per_batch":1000,
                      "converged":1}}'
```

Six of those values would be "engine configuration" in most estates, and all six
change the answer:

| Value | Change it and |
|---|---|
| `paths` | the standard error moves, and the quantile moves with it |
| `seed` | every number moves, within noise — and *which* noise is not knowable without it |
| `scheme` | `sobol` and `pseudo` converge at different rates at the same path count, and their errors are not distributed alike |
| `antithetic` | the variance falls and the estimate shifts |
| `brownian_bridge` | the path construction changes, which changes what a low-discrepancy sequence's early dimensions are spent on |
| `time_grid` | the exposure profile is only defined where you observe it |

If they are not in `P`, they are not in the digest, not in the warrant, and not
in the replay. The model would be reproducible in name only.

> **`antithetic: 1`, not `true`.** Truth values are integers throughout MAYA —
> the register, both SQL dialects, and the Delta tables. There is no `BOOLEAN`
> column anywhere, and `test_schema_discipline` walks the source to keep it that
> way. The service layer converts at its boundary, so no consumer has to know.

Note what this parameter set is *not*: it is nine values, comfortably under the
4,096 the register holds inline. The
[neural network](/tutorials/neural-network-end-to-end) is where that ceiling
bites and `P` stops being a record.

`as_of` is here because `L-W11` requires it — the `parameter_kind` is
`calibration_set`, exactly as in
[Hull–White](/tutorials/hull-white-end-to-end#4-calibrate-and-deliver-the-set),
so a set delivered without it makes this model unresolvable. A simulation
running last month's calibration against today's book produces an entirely
ordinary-looking exposure number, which is the whole reason the law exists.

---

## 3 · A standard error is a standard error *of* something

This is the section that could only be about a simulation, and it is the part
reviewers most often get wrong.

A Monte Carlo answer is an estimate with a confidence interval, and a review
that does not see the interval is reviewing a point. But **the interval on the
EPE and the interval on the PFE are not the same statistic**, and the second is
much worse than people expect.

**The EPE is a mean.** It averages over every path, so its standard error falls
as `1/√N` for pseudo-random paths, and 50,000 paths buys you two decimal digits
comfortably. `standard_error_epe: 0.0009` — under a tenth of a percent — is what
that looks like.

**The PFE at 97.5% is a quantile, and quantiles are estimated from the tail.**
Only 2.5% of the paths sit above it: **1,250 of the 50,000**. The standard error
of a sample quantile scales as `√(q(1−q)/N) / f(x_q)` — it depends on the
*density* at the quantile, and in the far tail of an exposure distribution that
density is small. So the effective sample is a fortieth of the nominal one, and
`standard_error_pfe: 0.0031` against `standard_error_epe: 0.0009` is not a
rounding difference; it is the tail doing what tails do. Quadrupling the paths
halves it. If the limit you are checking sits within two standard errors of the
PFE, the answer is *not enough paths*, not *breach* or *no breach*.

**And with `sobol`, `1/√N` is not the right formula at all.** A low-discrepancy
sequence is not independent and identically distributed, so the textbook
standard error does not apply — it typically understates the accuracy, which is
the flattering direction and therefore the dangerous one to leave unexamined.
The honest construction is what the diagnostics above report: **50 randomised
batches of 1,000 paths**, with the standard error taken *across batch estimates*.
A set delivered with a `sobol` scheme and an iid standard error is a set whose
diagnostics do not describe what was run, and that is worth a rejection rather
than a note.

**`antithetic` is not free variance reduction.** It halves the variance of a
payoff that is close to linear in the driving factor, and does approximately
nothing for one that is symmetric about the mean — a straddle, or an exposure
profile dominated by absolute value. Recording it in `P` is what lets a reviewer
ask whether it was doing anything at all here.

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/parameter-sets/ps-8831/review \
  -H 'Content-Type: application/json' \
  -d '{"accept":true,
       "note":"SE 0.31% of PFE from 50 randomised batches of 1k Sobol paths;
               limit headroom is 8 SEs; convergence study attached"}'
```

The convergence evidence attaches to **the parameter set**, not to the model and
not to the version, so "how many paths did we decide were enough, and on what
basis" has an answer eighteen months later:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/attachments \
  -F 'urn=maya://model/xva.pfe' \
  -F 'kind=evidence_of_control' \
  -F 'subject_type=parameter_set' -F 'subject_id=ps-8831' \
  -F 'title=PFE convergence, 1k to 200k paths' \
  -F 'file=@convergence.pdf'

curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/attachments/<attachment_id>/review \
  -H 'Content-Type: application/json' -d '{"accept":true}'
```

Two duties there, and it is worth knowing which way round they go: the first
line holds `document:attach` and the second line holds `document:review`. A
validator cannot file the evidence they are about to accept.

---

## 4 · Resolving it, and where MAYA stops

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/xva.pfe#champion","environment":"prod",
       "principal":"svc/xva","declared_use":"counterparty_limit_check"}'

curl -u svc/xva:svc-pw -X POST \
  "localhost:5006/api/v1/resolve?verb=simulate" \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/xva.pfe#champion","environment":"prod",
       "principal":"svc/xva","declared_use":"counterparty_limit_check"}'
```

The verb is a **query parameter on `/resolve`** and it is `simulate`, not
`score`. "Draw from the model's output distribution" is a different operation
from "give me the point estimate", and the warrant names which one is
authorised. Ten verbs exist; the grammar knows which the class admits.

What comes back is a signed descriptor carrying the image digest, the parameter
set with its own digest and its `as_of`, the io contract, the operating boundary
and a sixty-second expiry. Your engine acts on it.

> **`/execute` is not the route here, and the refusal says so.** The convenience
> endpoint runs MAYA's captive engine, which implements **five** runtimes —
> bound callables, ONNX, PMML, QuantLib and the estimator — and `container` is
> not one of them:
>
> ```json
> {"error": "no_runtime",
>  "detail": "this engine does not implement the 'container' runtime",
>  "remediation": "it implements callable, estimator, onnx, pmml, quantlib;
>                  route this warrant to an engine that has the runtime, or
>                  register the version against one of these"}
> ```
>
> Refused **by name**, listing what it does have, rather than failing three
> layers down inside an artifact loader. The grammar names eighteen runtimes and
> no engine implements all of them; an engine's usefulness is in being precise
> about which it has.

Your engine, holding that descriptor, returns whatever it returns — and the
reproducibility block it should echo back is exactly the part of `P` that made
the answer what it is:

```json
{"epe_profile": [], "pfe_97_5": 4182000.0,
 "reproducibility": {"parameter_set": "ps-8831",
                     "digest": "sha256:c41f…",
                     "seed": 20260331, "paths": 50000, "scheme": "sobol",
                     "as_of": 1743382800}}
```

---

## 5 · The failure this tutorial exists for

A real shape of incident, and the reason single-case testing is not enough.

The engine seeded its random generator **once at process start**. Somebody
replaced that with a **per-request seed** — a pure performance change: it removes
a lock, halves latency, and touches nothing about the model or its calibration.
Labelled a patch.

The nightly regression suite ran **eleven thousand single-trade valuations** and
reproduced every one within tolerance. Of course it did: a single valuation
averages over its own paths either way.

What changed was the **correlation between valuations in one batch**. Two trades
in the same netting set used to be simulated against common paths and now were
not, so the offsetting positions stopped offsetting. Netting-set exposure moved
materially, in the direction of understatement.

**Eleven thousand tests could not detect it, and no number of tests of that shape
could have.** The defect was not that the suite was too small. It was that every
element of it had length one, and the property that broke is a property *of a
sequence*.

### What the platform does about it

- **The seed policy is in `P`**, so changing it changes the digest, and a changed
  digest is a changed parameter set requiring a second signature — not a patch.
- **Replay works on sequences**, not cases: the validation episode records which
  sequences were replayed, and `replay-from-storage` re-reads the snapshot the
  episode pinned rather than accepting data from whoever is asking.
- **The `deterministic` claim travels** on every warrant, so an engine that
  cannot honour it is holding a document that says so.

And one thing it does not do: nothing in MAYA would have caught the change
itself. The image digest changes on any rebuild, the parameter set did not, and
the platform has no view inside a container. What it gives you is the place the
seed policy is written down and the signature that says somebody looked — which
is the difference between an incident with a cause and an incident with a
mystery.

The general rule, worth carrying past this page: *if a thing remembers, or if
its answers to different questions are related, you cannot learn what it does by
asking it questions one at a time.* The
[GARCH scorer](/tutorials/garch-end-to-end#4-scoring-and-the-state-problem) is
the same lesson with three numbers instead of fifty thousand paths.

---

## 6 · Monitoring a simulation

```bash
curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/xva.pfe","name":"10d exposure coverage",
       "kind":"calibration","test_key":"calibration.expected_vs_actual",
       "threshold":{"target":1.0,"tolerance":0.4},
       "owner":"person/j.okafor","cadence_days":7,"label_delay_days":10,
       "breach_severity":"High","escalate_after":2,
       "reference":{"nominal":0.025,"horizon_days":10}}'
```

Exposure backtesting compares realised exposure against the simulated quantile.
Each row is one counterparty-day: `score` is the nominal exceedance probability
the simulation implied (0.025), `label` is whether the realised exposure actually
exceeded the PFE. `label_delay_days: 10` is the horizon, and it is a refusal
rather than a convention — a `calibration` monitor without it is rejected at
definition with `label_delay_required`, and evaluating one before the cohort has
matured is rejected with `cohort_immature` and the date it becomes measurable.

A ratio below 1 means the simulation is **understating** — the exceedances are
more frequent than the model implied — which is the finding the incident in §5
would eventually have produced, a quarter later and after the limits had already
been wrong for a quarter.

A second monitor watches the **standard error itself**, as a `performance`
monitor with `accuracy.rmse` over the batch estimates. An engine quietly dropping
paths under load degrades the estimate without changing anything an exposure
monitor would see, and the first symptom is a standard error that has doubled
while every number still looks plausible.

---

## Next

[The neural network](/tutorials/neural-network-end-to-end) is where `P` stops
fitting in the register at all — nine values here, twenty million there — and
MAYA has to hold the bytes.
