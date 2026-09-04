---
title: Validation and findings
slug: validation
section: Assurance
order: 90
icon: clipboard-check
summary: Episodes of independent challenge — the test catalogue, the independence rule, why you cannot approve over a failure, reproducibility replay — and the findings register that turns what challenge found into a refusal.
audience: Model validation, Model risk, Model owners
---

# Validation and findings

Challenge produces two artifacts: a record of what was tested, and a list of what
was wrong with it. MAYA keeps them as separate objects because they have
different lifecycles — an episode concludes, a finding stays open until somebody
fixes it — and connects them at the one point that matters: an open blocking
finding stops the model being served at all.

## What a validation is

A validation is an **episode of independent challenge** against one model
version, recorded as an object with a lifecycle rather than as a document
attached to a model, because three things about it need to be enforceable.

### Rule 1 — independence

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

Concluding an episode is separately gated by segregation of duties, read from
the evidence chain: whoever created the version may not conclude the validation
of it, whatever roles they hold.

### The test catalogue

A validation may only run **registered** tests. They are published at
`GET /api/v1/tests`:

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

Seven of them take labels and scores. `stability.psi` is the exception: it
compares two samples, because stability is a question about distributions rather
than about outcomes.

These are computed from their definitions rather than imported from a library.
A result has to be reproducible years after the library that computed it is
gone, and a validator has to be able to show an examiner how the number was
arrived at.

Ties take average ranks throughout. Degenerate samples — one class present, a
zero base rate, too few points for the requested bins — return **not computable**
rather than a number, and a not-computable test does **not** pass:

```
not computable on this sample — a class may be absent, or the sample too
small for the requested bins
```

Absent evidence is not evidence of compliance.

### Recording a result

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
`{"target": t, "tolerance": e}`, and a threshold declaring none of the three is
refused. No threshold at all records the measurement and passes — an exploratory
number should not have to invent a limit to be recorded, and it must never look
like a test that met one.

### Rule 2 — no approval over a failure

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

### Rule 3 — no approval over a blocking finding

If something blocking is open against the model, approval is refused until it is
closed, naming the findings that stand in the way. Both rules fire only on
`approved`; rejecting a model over a failed test needs no permission from the
test.

### Results are immutable once concluded

Recording against a completed episode is refused — *its results are immutable* —
and a concluded episode cannot be concluded again. A validation that can be
edited after the fact is not evidence of anything.

### Reproducibility replay

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

## Findings

Every model risk framework requires findings to be tracked. Most systems track
them in a table that nothing reads.

The difference here is one column: **`blocking`**.

### An open blocking finding refuses two things

**Alias promotion.**

```
alias move refused: 1 blocking finding(s) open against
maya://model/credit.pd.smallbiz (Label leakage in the training set);
close them or downgrade them before promoting a version
```

**Warrant resolution.** HTTP 423, error code `blocked`:

```json
{
  "error": "blocked",
  "detail": "1 blocking finding(s) open against maya://model/credit.pd.smallbiz (...)",
  "remediation": "close the blocking findings, or withdraw the model from service"
}
```

A model that failed challenge cannot reach production by any route that does not
pass through this register. That is what makes it a control.

### Severity and default blocking

| Severity | Remediation window | Blocks by default |
|---|---|---|
| Critical | 30 days | **yes** |
| High | 90 days | no |
| Medium | 180 days | no |
| Low | 365 days | no |
| Observation | 365 days | no |

Blocking can be forced on any finding (`"blocking": true`), and set off a
Critical one explicitly. Only Critical blocks without anyone deciding — and the
default is what happens when nobody decides, which is the case worth designing
for.

Due dates are **derived from severity** rather than negotiated per finding, so a
Critical finding is not a diary entry.

```bash
POST /api/v1/findings
{
  "urn": "maya://model/credit.pd.smallbiz",
  "severity": "Critical",
  "title": "Label leakage in the training set",
  "owner": "person/j.okafor",
  "description": "The 90-day-arrears flag is computed after the label date.",
  "category": "data_quality",
  "source": "validation"
}
```

An owner is required. *A finding with no owner is a finding nobody will fix* — and
that is the refusal message.

### Closure needs someone else

```bash
POST /api/v1/findings/{id}/close
{"verified_by": "person/a.mehta", "evidence": {"pr": "1420", "rerun": "val-3391"}}
```

Two rules:

- **The owner may not verify their own closure.** The person who owns the
  remediation is the person with the strongest reason to declare it done, and a
  blocking finding is the only thing standing between a failed model and
  production.
- **Closure evidence is required.** An empty closure is refused.

There is also no back door: `set_status` will move a finding to
`in_remediation` or `resolved`, but attempting to set it to `closed` is refused
with *use close() — closure needs a verifier and evidence*.

### Sources

`validation`, `monitoring`, `audit`, `regulator`, `self_identified`. The source
matters for reporting: a regulator-raised finding and a self-identified one carry
very different weight in a supervisory conversation, and aggregating them
together loses exactly the distinction that matters.

Two of those five are raised by the platform itself rather than by a person —
monitoring breaches, and the scheduler's sweeps for lapsed attestations, stalled
monitors and missed remediation windows. See
[Monitoring](/help/monitoring) and
[The estate and what needs doing](/help/estate-and-worklist).

### Reading the register

```bash
GET /api/v1/findings?urn=maya://model/credit.pd.smallbiz
```

Returns the open list, the blocking subset, and a summary — open count, blocking
count, overdue count, worst severity, and a breakdown by severity. That summary
is what the model page shows, and what an inventory row needs.
