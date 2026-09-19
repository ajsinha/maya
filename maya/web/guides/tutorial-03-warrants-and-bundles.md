# Tutorial 3 — Warrants, parameters and a bundle

A model is trained under a **training warrant**: a signed permission that binds
one approved model version to one feature set, issues the data with a checksum,
certifies that no row leaks the future, escrows a holdout, and records every
step in a chain of custody. It is run under an **execution warrant** with
covenants that suspend it when they are breached. At the end, everything is
exported as a **bundle** that a regulator can verify without MAYA.

This tutorial continues from [Tutorial 2](/help/guides/tutorial-02-featureset-and-model):
`eq/linear@v1` is approved and `maya://featureset/eq/panel#q1/2026-02-28` is
sealed. It takes about thirty minutes.

## Who does what

| Person | Role | Does |
|---|---|---|
| devi | `model_developer` | draws the warrant, trains, uploads parameters |
| mgr | `model_manager` | approves parameters and the warrant, seals, issues the execution warrant |
| mgr2 | `model_manager` | the second person who approves the execution warrant |
| admin | `admin` | reinstates a suspended warrant |

```python
# One more manager: an execution warrant needs a second person
admin.admin.create_user("mgr2", password=PW, roles=["model_manager"])
mgr2 = connect_as("mgr2")
```

## Step 1: Draw the training warrant

```python
# devi binds the model to the pinned panel
tw = devi.training.create("eq", "linear_fit", "eq/linear@v1",
                          "maya://featureset/eq/panel#q1/2026-02-28",
                          spec={"target": "y", "seed": 7})
print(tw["name"], tw["state"])
print(tw["contract_report"]["ok"], tw["contract_report"]["mapping"])
cert = tw["leakage_certificate"]
print(cert["rule"], "|", cert["rows_examined"], cert["violations"], cert["status"])
```

```text
# Expected output
linear_fit draft
True {'x': 'x'}
every row's knowledge time ≤ its event date + 1 day(s) | 177 0 certified
```

Three things happened at creation:

* **The contract was checked.** The model's input `x` must be a numeric attribute
  of the set, and the `target` must exist. A mismatch refuses the warrant,
  listing every problem.
* **The leakage certificate was issued.** Every row's knowledge time was compared
  with its event date plus `leakage_lag_days` (default 1). All 177 rows were known
  on the evening of their own day, so the status is `certified`. It is signed
  with Ed25519.
* **The spec was completed with defaults.** Print `tw["spec"]` to see them all:

| Spec key | Default | Meaning |
|---|---|---|
| `split` | `{"train": 0.7, "validation": 0.15, "test": 0.15}` | a deterministic split by hashing the seed and the index key |
| `seed` | `42` | we set 7 |
| `holdout` | `escrowed` | the test rows are never downloaded; `none` releases them |
| `expiry_days` | `365` | after which the warrant must be cloned |
| `leakage_lag_days` | `1` | the allowed gap between event and knowledge |
| `bindings` | `{}` | model input → set attribute, when the names differ |
| `target` | none | the attribute scored against |
| `allow_non_causal` | `false` | with `non_causal_justification`, admits non-causal fills |
| `leakage_justification` | `""` | admits late rows as a justified exception |
| `metrics` | `["rmse"]` | recorded intent |
| `shape`, `environment`, `objective` | `tabular`, `{"python": "3.13"}`, `""` | recorded intent |

In the UI: **Warrants → New training warrant** (`/warrants/training/new`).

## Step 2: Fetch the data

```python
# Download the training data; the SDK verifies the checksum
table, manifest = devi.training_data(tw["id"])
print(manifest["rows"], manifest["escrowed_holdout"], manifest["checksum"][:16])
df = table.to_pandas()
print(df["_split"].value_counts().to_dict())
```

```text
# Expected output
151 True acb3cf3565dd62bf
{'train': 128, 'validation': 23}
```

The 26 test rows stayed behind: they are escrowed. The download was recorded in
the warrant's custody chain with its checksum, which is how MAYA will later know
the parameters were trained on data it issued.

```bash
# The same from the CLI
python -m maya.cli warrant fetch <warrant-id> --out train.parquet
```

```text
# CLI output
train.parquet: 151 rows; checksum verified acb3cf3565dd62bfd8ae2b577c3b2a3e854fd278b42a19a4d9668659aaff29b8
```

## Step 3: Train anywhere

Training happens on your own machine, with your own tools. Here a straight-line
fit on the training split:

```python
# Fit y = a*x + b on the train split
import numpy as np
train = df[df["_split"] == "train"]
a, b = np.polyfit(train["x"], train["y"], 1)
print(round(a, 6), round(b, 6))
```

```text
# Expected output
2.0 0.5
```

## Step 4: Upload the parameters

Quote the checksum you trained on.

```python
# Upload a parameter set
ps = devi.training.upload_parameters(tw["id"], {"a": 2.0, "b": 0.5},
                                     metrics={"rmse_train": 0.0},
                                     data_checksum=manifest["checksum"])
print(ps["state"], ps["verified_data"], ps["flag"])
```

```text
# Expected output
draft True None
```

```bash
# The same from the CLI, with params.json holding values, metrics and data_checksum
python -m maya.cli warrant upload-params <warrant-id> params.json
```

```text
# CLI output
parameter set <id> uploaded; verified data
```

!!! warning "Unverified data"
    A checksum MAYA never issued (or none) gives `verified_data: false` and the
    flag `unverified_data`. Such a set can be submitted, but approval is blocked
    by the `data_verified_or_justified` check unless a justification is given
    (`parameter_transition(..., justification="…")`). Values outside a
    parameter's declared `bounds` are refused at upload.

## Step 5: Approve the parameters

```python
# devi submits, mgr approves
devi.training.parameter_transition(ps["id"], "submit")
r = mgr.training.parameter_transition(ps["id"], "approve")
print(r["state"])
for c in r["checks"]:
    print(" ", c["check"], "-", c["detail"])
```

```text
# Expected output
approved
  parameters_within_bounds - all parameters within declared bounds
  data_verified_or_justified - trained on data MAYA issued (checksum matched)
  no_open_blocking_comments - no open blocking comments
```

## Step 6: Score blind on the holdout

MAYA evaluates the model on the escrowed rows and returns only metrics. Every
attempt is counted and shown on the warrant, so repeated peeking is visible.

```python
# Blind scoring
print(devi.training.score_holdout(tw["id"], parameter_set_id=ps["id"]))
```

```text
# Expected output
{'metrics': {'rmse': 0.0, 'mae': 0.0, 'rows': 26}, 'attempt': 1, 'note': 'Every attempt is counted and shown on the warrant.'}
```

## Step 7: Approve and seal the warrant

```python
# Submit, approve, seal
r = devi.training.transition(tw["id"], "submit")
print(r["state"], [(c["check"], c["detail"]) for c in r["checks"]])
print(mgr.training.transition(tw["id"], "approve")["state"])
print(mgr.training.seal(tw["id"])["sealed_at"] is not None)
```

```text
# Expected output
in_review [('contract_valid', 'contract satisfied'), ('leakage_certified', 'leakage certificate: certified; 0 violating row(s)')]
approved
True
```

Sealing freezes the warrant: no further parameters can be uploaded (clone it to
train again). A trainable model's warrant seals only once a parameter set is
approved. `python -m maya.cli warrant seal <warrant-id>` does the same.

## Step 8: Issue an execution warrant

An execution warrant authorizes running the model with the approved parameters,
in named environments, under limits and covenants.

```python
# mgr issues it
ew = mgr.execution.create("eq", "linear_live", training_warrant_id=tw["id"],
                          parameter_set_id=ps["id"],
                          spec={"environments": ["dev"], "contact": "risk@example.com",
                                "limits": {"max_calls_per_day": 100},
                                "covenants": [
                                    {"kind": "input_null_rate", "attr": "x", "max": 0.1},
                                    {"kind": "output_range", "attr": "yhat",
                                     "min": -1000, "max": 1000}]})
print(ew["state"], ew["spec"]["valid_days"])
```

```text
# Expected output
draft 90
```

| Spec key | Default | Values |
|---|---|---|
| `environments` | `["dev"]` | `dev`, `uat`, `prod` |
| `valid_days` | `90` | the life of the sealed warrant |
| `contact` | `""` | named in every refusal |
| `limits` | `{}` | `max_calls_per_day`, `max_rows_per_call`, `max_rows_per_day`: positive whole numbers; they throttle |
| `covenants` | `[]` | `input_null_rate`, `input_range`, `output_range`, `max_rows_per_day`, `staleness_days`: a breach suspends |

```python
# Two people: mgr submits, mgr2 approves; then seal
mgr.execution.transition(ew["id"], "submit")
r = mgr2.execution.transition(ew["id"], "approve")
print(r["state"], [c["check"] for c in r["checks"]])
print(mgr.execution.seal(ew["id"])["valid_to"])
```

```text
# Expected output
approved ['parameters_approved', 'no_open_blocking_comments']
2026-12-18T15:35:07.421567+00:00
```

In a production environment the policy also requires a `model_owner` approval.

## Step 9: Run under the warrant

The execution bundle is everything a runtime needs in one call: the manifest, the
IR, the parameters and a signed token valid for 15 minutes.

```python
# Fetch the execution bundle and score three rows
bundle = devi.execution.bundle(ew["id"], "dev")
print(bundle["warrant"], bundle["status"], bundle["parameters"])
x = np.array([1.0, 2.0, 3.0])
yhat = bundle["parameters"]["a"] * x + bundle["parameters"]["b"]
print(yhat)
```

```text
# Expected output
maya://warrant/exec/eq/linear_live@v1 live {'a': 2.0, 'b': 0.5}
[2.5 4.5 6.5]
```

Report each run back. Covenants are evaluated on what you report:

```python
# A healthy run
print(devi.execution.report(ew["id"], "dev", rows=3,
                            input_stats={"x": {"null_rate": 0.0}},
                            output_stats={"yhat": {"min": 2.5, "max": 6.5}}))
```

```text
# Expected output
{'accepted': True, 'breaches': [], 'limits_exceeded': [], 'status': 'live'}
```

Now a run where 40% of `x` was missing:

```python
# A run that breaches a covenant
r = devi.execution.report(ew["id"], "dev", rows=3, input_stats={"x": {"null_rate": 0.4}})
print(r["status"], r["breaches"][0]["detail"])
devi.execution.bundle(ew["id"], "dev")
```

```text
# Expected output, then the bundle call raises
suspended null rate of 'x' 0.400 > 0.1
WarrantSuspended: Warrant suspended: null rate of 'x' 0.400 > 0.1. Contact risk@example.com.
```

The warrant is suspended until the model owner or an administrator reinstates it
with a written reason:

```python
# Reinstate after investigating
admin.execution.reinstate(ew["id"], "vendor file arrived late; checked")
print(devi.execution.bundle(ew["id"], "dev")["status"])
```

```text
# Expected output
live
```

## Step 10: Export the reproducibility bundle

```python
# Export and save the bundle
ex = devi.training.export_bundle(tw["id"])
print(ex["size"], sorted(ex["manifest"]["files"]))
open("linear_fit.zip", "wb").write(devi.admin.blob(ex["blob"])["data"])
```

```text
# Expected output
12671 ['certificate.json', 'data/training.parquet', 'environment.json', 'lib/canonical.py', 'lib/chunker.py', 'model/formula_ir.json', 'model/model_version.json', 'model/parameter_set.json', 'model/parameters.json', 'model/reference_model.py', 'model/spec.tex', 'verify.py', 'warrant.json']
```

```bash
# The same from the CLI
python -m maya.cli export bundle <warrant-id> --out linear_fit.zip
```

```text
# CLI output
linear_fit.zip: signed bundle, 12671 bytes
```

## Step 11: Verify it offline

The bundle carries its own `verify.py`, which needs Python, `pyarrow` and `numpy`
and nothing from MAYA. It checks every file hash, the Ed25519 signature over the
file list, the data's content hash (recomputed with the canonical encoder shipped
in the bundle), and re-executes the model to compare its output hash.

```bash
# Verify on any machine
python -m maya.cli export verify linear_fit.zip
```

```text
# Expected output
  [ok] file hash certificate.json
  [ok] file hash data/training.parquet
  …
  [ok] file hash warrant.json
  [ok] Ed25519 signature over the file list
  [ok] data content hash (canonical, value-based)
  [ok] re-execution output hash
verified: True
```

Unzip it and `python verify.py` gives the same answer. Change one byte of
`model/parameters.json` and verification fails.

## Step 12: Open the bundle as an offline MAYA

```python
# A read-only, network-free MAYA over the bundle
import maya.sdk as maya
with maya.offline("linear_fit.zip") as off:
    t, m = off.training_data()
    print(t.num_rows, off.parameters())
    print(off.predict({"x": [1.0, 2.0]}))
    print(off.verify()["verified"])
```

```text
# Expected output
177 {'a': 2.0, 'b': 0.5}
{'yhat': array([2.5, 4.5])}
True
```

Offline mode evaluates the IR with MAYA's own evaluator; it never executes code
shipped in the bundle. Every call that would need a server is refused.

## On screen

| Step | Screen |
|---|---|
| Training warrants | **Warrants** (`/warrants`), `/warrants/training/new`, `/warrants/training/{id}` |
| Data download | `/warrants/training/{id}/data` |
| Execution warrants | `/warrants/execution/new`, `/warrants/execution/{id}` |
| Verify a bundle | **Warrants → Verify** (`/warrants/verify`) |

## What you learned

* A training warrant checks the contract, certifies against leakage and escrows
  the holdout before any data leaves.
* The checksum cycle ties parameters to the data MAYA issued.
* Blind scoring counts every attempt.
* An execution warrant throttles on limits and suspends on covenants.
* A bundle proves itself, anywhere, without MAYA.

Next: [Tutorial 4 — A governed change](/help/guides/tutorial-04-governed-change).
