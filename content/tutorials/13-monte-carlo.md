---
title: A Monte Carlo engine, end to end
slug: monte-carlo-end-to-end
section: Worked models
order: 52
icon: shuffle
summary: A counterparty exposure simulation registered, warranted and served — where the seed and the path count are part of P, "deterministic" becomes a claim the grammar checks, and a patch release that passed eleven thousand tests still broke the netting sets. The tutorial about reproducibility.
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
| Runtime | `python.callable` or `container` — the bank's own engine |
| The catch | it is only reproducible if you make it so |

---

## 1 · The seed is a parameter, not a setting

This is the claim the tutorial rests on, so it is worth stating plainly.

A simulation with an unrecorded seed produces a number nobody can reproduce.
A simulation with a recorded seed produces a number anybody can. The seed is
therefore part of what determines the output — which is the definition of a
parameter, not the definition of a runtime flag.

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
                 "input_schema":[{"name":"netting_set","dtype":"structured"},
                                 {"name":"as_of","dtype":"timestamp"}],
                 "output_schema":[{"name":"epe_profile","dtype":"structured"},
                                  {"name":"pfe_97_5","dtype":"numeric"}]}}'
```

Note `deterministic: true`. That is a **claim**, and the grammar checks it:

```json
{"error": "grammar_violation",
 "clause": "L-W6",
 "detail": "the warrant claims determinism but binds no seed",
 "remediation": "pin the seed in the parameter set, or declare the version
                 non-deterministic and accept a tolerance on replay"}
```

You may declare either. What you may not do is claim reproducibility and leave
the thing that would provide it unbound.

---

## 2 · The parameter set carries the whole configuration

```bash
curl -u svc/xva-calib:svc-pw -X POST localhost:5006/api/v1/parameters \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/xva.pfe","semver":"1.0.0",
       "name":"pfe_2026-03-31","kind":"calibration_set",
       "provenance":"calibrated",
       "values":{"hull_white":{"mean_reversion":0.031,"sigma_1y":0.0062},
                 "paths":50000,
                 "seed":20260331,
                 "scheme":"sobol",
                 "time_grid":"monthly_to_10y_then_annual",
                 "antithetic":1},
       "featureset":"hw_calibration_grid","featureset_version":1,
       "warrant_id":"<the grant id>","as_of":1743382800,
       "diagnostics":{"standard_error_pfe":0.0031,
                      "convergence_paths":50000,
                      "brownian_bridge":1}}'
```

Four of those values would be "engine configuration" in most estates, and all
four change the answer:

| Value | Change it and |
|---|---|
| `paths` | the standard error moves; the PFE quantile moves with it |
| `seed` | every number moves, within noise |
| `scheme` | `sobol` and `pseudo` converge differently at the same path count |
| `antithetic` | the variance halves and the estimate shifts |

If they are not in `P`, they are not in the digest, not in the warrant, and not
in the replay. The model would then be reproducible in name only.

> **`antithetic: 1`, not `true`.** Truth values are stored as integers
> throughout MAYA — the register, the schemas, the Delta tables. The service
> layer converts at its boundary so no consumer has to know.

---

## 3 · Standard error is a first-class diagnostic

A Monte Carlo answer is an estimate with a confidence interval, and a review
that does not see the interval is reviewing a point.

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/parameter-sets/<id>/review \
  -H 'Content-Type: application/json' \
  -d '{"accept":true,
       "note":"SE 0.31% of PFE at 50k Sobol paths; convergence plot attached"}'
```

The convergence evidence attaches to the parameter set as a document, so
"how many paths did we decide were enough, and on what basis" has an answer
eighteen months later:

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/attachments \
  -F 'kind=convergence_evidence' \
  -F 'subject_type=parameter_set' -F 'subject_id=<id>' \
  -F 'title=PFE convergence, 1k to 200k paths' \
  -F 'file=@convergence.pdf'
```

---

## 4 · Serving it, and what comes back

```bash
curl -u svc/xva:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/xva.pfe#champion","environment":"prod",
       "principal":"svc/xva","declared_use":"counterparty_limit_check",
       "verb":"simulate",
       "inputs":{"as_of":"2026-03-31",
                 "netting_set":{"id":"NS-4471","trades":["T-1","T-2","T-3"]}}}'
```

The verb is `simulate`, not `score` — "draw from the model's output
distribution" is a different operation from "give me the point estimate", and
the warrant names which one is authorised. A warrant for `score` will not
`simulate`.

```json
{"outputs": {"epe_profile": [...], "pfe_97_5": 4182000.0},
 "parameters": {"id": "ps-8831", "digest": "sha256:c41f…"},
 "reproducibility": {"seed": 20260331, "paths": 50000, "scheme": "sobol"}}
```

---

## 5 · The failure this tutorial exists for

A real shape of incident, and the reason single-case testing is not enough.

The engine seeded its random generator **once at process start**. Somebody
replaced that with a **per-request seed** — a pure performance change: removes a
lock, halves latency, touches nothing about the model or its calibration.
Labelled a patch.

The nightly regression suite ran **eleven thousand single-trade valuations** and
reproduced every one within tolerance. Of course it did: a single valuation
averages over paths either way.

What changed was the **correlation between valuations in one batch**. Two trades
in the same netting set used to be simulated against common paths and now were
not. Netting-set exposure moved materially, in the direction of understatement.

**Eleven thousand tests could not detect it, and no number of tests of that
shape could have.** The defect was not that the suite was too small. It was that
every element of it had length one.

### What the platform does about it

- The seed policy is **in `P`**, so changing it changes the digest, and a
  changed digest is a changed parameter set requiring review — not a patch.
- Replay works on **sequences**, not cases, and the validation record says which
  sequences were replayed.
- The version's `deterministic` claim is checked against the binding, so
  "reproducible" cannot be asserted without the thing that makes it true.

The general rule, worth carrying past this page: *if a thing remembers, or if
its answers to different questions are related, you cannot learn what it does by
asking it questions one at a time.*

---

## 6 · Monitoring a simulation

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/xva.pfe","kind":"performance",
       "test":"backtest_breach","threshold":0.025,
       "label_delay_days":1,
       "reference":{"nominal":0.975,"horizon_days":10}}'
```

Exposure backtesting compares the realised exposure against the simulated
quantile. Breaches above the nominal rate mean the simulation is understating —
the finding that the incident above would have produced, a quarter later and
after the limits had already been wrong.

A second monitor watches the **standard error itself**. An engine quietly
dropping paths under load degrades the estimate without changing anything a
price monitor would see.

---

## Next

[The neural network](/tutorials/neural-network-end-to-end) is where `P` stops
fitting in the register at all, and MAYA has to hold the bytes.
