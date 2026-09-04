---
title: Validation
slug: validation
section: Assurance
order: 120
icon: clipboard-check
summary: Episodes of independent challenge — the test catalogue, the independence rule, why you cannot approve over a failure, and reproducibility replay.
audience: Model validation
---

# Validation

A validation is an **episode of independent challenge** against one model
version. MAYA records it as an object with a lifecycle rather than as a document
attached to a model, because three things about it need to be enforceable.

## Rule 1 — independence

A validator may not be the person who built the version.

```bash
POST /api/v1/validations
{
  "urn": "maya://model/credit.pd.smallbiz",
  "semver": "3.2.1",
  "validators": ["person/a.mehta"],
  "kind": "initial",
  "scope": ["discrimination", "calibration"]
}
```

If any named validator is the version's `created_by`, the episode is refused:

```
independence failed: person/d.raman built this version; effective challenge
requires a validator who did not build the version
```

This is SS1/23 Principle 4 and SR 26-2's *effective challenge*, in the only form
a system can actually check. The attestation is stored on the episode either
way, so the record shows who validated and what the independence position was.

## The test catalogue

A validation may only run **registered** tests. They are published:

```bash
GET /api/v1/tests
```

| Key | Measures | Direction |
|---|---|---|
| `discrimination.auc` | Area under the ROC curve | higher is better |
| `discrimination.gini` | 2 × AUC − 1 | higher is better |
| `discrimination.ks` | Kolmogorov–Smirnov separation | higher is better |
| `calibration.brier` | Brier score of the probability forecast | lower is better |
| `calibration.expected_vs_actual` | Predicted rate ÷ observed rate | target 1.0 |
| `stability.psi` | Population Stability Index | lower is better |
| `accuracy.rmse` | Root mean squared error | lower is better |
| `accuracy.mae` | Mean absolute error | lower is better |

These are computed from their definitions rather than imported from a library.
A result has to be reproducible years after the library that computed it is
gone, and a validator has to be able to show an examiner how the number was
arrived at.

Ties take average ranks throughout. Degenerate samples — one class present, a
zero base rate, too few points for the requested bins — return **not computable**
rather than a number, and a not-computable test does **not** pass. Absent evidence
is not evidence of compliance.

## Recording a result

```bash
POST /api/v1/validations/{id}/results
{
  "test_key": "discrimination.gini",
  "threshold": {"min": 0.42},
  "left":  [0, 0, 1, 1, ...],
  "right": [0.02, 0.05, 0.61, 0.94, ...],
  "slice": {"region": "EMEA"}
}
```

**The test is a measurement; the threshold is a policy.** Thresholds are declared
per run, because the Gini floor that is right for a Tier 3 marketing propensity
model is not the one that is right for a Tier 1 IRB PD model.

Thresholds take one of three forms: `{"min": x}`, `{"max": x}`, or
`{"target": t, "tolerance": e}`. No threshold at all records the measurement and
passes — an exploratory number should not have to invent a limit to be recorded,
and it must never look like a test that met one.

## Rule 2 — no approval over a failure

```bash
POST /api/v1/validations/{id}/conclude
{"outcome": "approved"}
```

If any recorded test failed:

```
cannot approve: 1 test(s) failed (discrimination.gini); conclude
'approved_with_conditions' with the conditions written down, or 'rejected'
```

The legitimate route out is always offered. `approved_with_conditions` is a real
outcome — it just forces the conditions to be written down, which is the whole
point.

## Rule 3 — no approval over a blocking finding

If something blocking is open against the model, approval is refused until it
is closed. See [Findings](/help/findings).

## Results are immutable once concluded

Recording against a completed episode is refused. A validation that can be
edited after the fact is not evidence of anything.

## Reproducibility replay

```bash
POST /api/v1/validations/{id}/replay
{"data": {"discrimination.gini": [[labels...], [scores...]]}}
```

Each recorded result is recomputed and compared **on its digest**, which covers
the test key, the value, the threshold, the parameters and the slice. So replay
catches more than a changed number — it catches a threshold that moved after the
fact, and a slice definition that drifted, both of which leave the value intact
and the conclusion wrong.

A test whose data cannot be supplied is reported **skipped**, never reproduced:

```json
{"reproducible": false, "reproduced": 1, "skipped": [...],
 "detail": "1 could not be checked"}
```

"We could not check" and "we checked and it matched" are opposite findings. A
replay report that blurs them is worse than no replay at all.
