# Warrants and bundles reference

Warrants are how MAYA governs the step from data to a running model. A **training warrant** is drawn up before anyone trains: it binds an approved model version to a feature set, fixes the terms of the run, certifies the data free of look-ahead, and is the only way to download training data. **Parameter sets** come back against it. An **execution warrant** licenses the trained model to run — where, on what inputs, until when — and fails closed the moment it should. A **reproducibility bundle** packages a training warrant so that someone without MAYA can check it.

## At a glance

| Instrument | Reference | Created by | Becomes useful when |
|---|---|---|---|
| Training warrant | `maya://warrant/train/<ns>/<name>@v<n>` | `C` on `training_warrant` (model developers) | approved; sealed once its parameters are approved |
| Parameter set | `maya://parameters/<id>` | `C` on `parameter_set` | approved |
| Execution warrant | `maya://warrant/exec/<ns>/<name>@v<n>` | `C` on `execution_warrant` (model managers) | approved and sealed: *live* |
| Bundle | a blob digest | anyone who can read the warrant | exported; verifiable anywhere |

Every warrant keeps a **custody log**: an append-only list of events with the actor, a checksum where one applies, and details. `GET /warrants/training/{id}` and `GET /warrants/execution/{id}` return it.

## Training warrants

### Creating one

```python
# Draw up a training warrant on a sealed feature set pin
import maya.sdk as maya
my = maya.connect(base_url="https://maya.example.com", api_key="maya_prod_…")
w = my.training.create(
    namespace="credit", name="pd-2026q1",
    model="maya://model/credit/pd_logit@v3",
    featureset="maya://featureset/credit/pd_panel#q1/2026-03-31",
    spec={"target": "default_12m", "bindings": {"ltv": "loan_to_value"},
          "holdout": "escrowed", "expiry_days": 365})
print(w["id"], w["state"], w["leakage_certificate"]["status"])
```

The feature set may be a version or a pin. Only a pin freezes the data; prefer `maya://featureset/<ns>/<name>#<pin>/<date>`. Each new warrant with the same namespace and name gets the next version number.

At creation MAYA, in order:

1. requires `create` on training warrants in the namespace;
2. requires the model version to be approved (`approved` or `published`), else `not_approved`;
3. refuses if the feature set's licence forbids derived works ("training a model on it");
4. resolves the feature set as you are allowed to see it;
5. validates the model's input contract against it — every miss is listed, and any miss refuses with `contract_mismatch`;
6. issues the signed leakage certificate;
7. records the backend set, the `created` custody event, lineage edges from the model and the feature set, and the audit entry `warrant.created`.

### The spec

Anything left out takes its default.

| Key | Default | Meaning |
|---|---|---|
| `split` | `{"train": 0.7, "validation": 0.15, "test": 0.15}` | Partition fractions; each ≥ 0, summing to 1. |
| `seed` | `42` | The split is a SHA-256 hash of `(seed, index key)`, so it reproduces anywhere. |
| `holdout` | `escrowed` | `escrowed` keeps the `test` rows inside MAYA; `none` includes them in the download. |
| `target` | none | The attribute the model predicts. Needed for holdout scoring. Must exist in the feature set. |
| `bindings` | `{}` | Model input name → feature-set attribute name, where they differ. |
| `expiry_days` | `365` | Counted from creation. After it the warrant refuses downloads and uploads (`warrant_expired`); clone it to continue. |
| `leakage_lag_days` | `1` | How long after its event date a value may become known. |
| `allow_non_causal` | `false` | Must be `true` if the feature set uses a non-causal fill, with a justification. |
| `non_causal_justification` | empty | The written reason for a non-causal fill. |
| `leakage_justification` | empty | The written reason that turns late-known rows into a certified exception. |
| `environment` | `{"python": "3.13"}` | The declared training environment, carried into bundles. |
| `objective` | empty | Free text. |
| `metrics` | `["rmse"]` | The metrics the trainer means to report. |

### The input contract

Every model input whose role is `feature` must map — directly or through `bindings` — to a feature-set attribute of a numeric type (`int32`, `int64`, `float32`, `float64`, `decimal`, `bool`). The contract report lists every missing attribute and every non-numeric one, and the `target` if it is absent. It is stored on the warrant and re-read by the `contract_valid` check.

### The leakage certificate

MAYA checks every row of the resolved feature set: a value's knowledge time must be no later than the end of its event date plus `leakage_lag_days`.

| Field | Meaning |
|---|---|
| `rule` | The rule applied, in words. |
| `rows_examined`, `violations` | Rows checked; rows that broke the rule. |
| `examples` | Up to 20 violating rows (index and knowledge time). |
| `exceptions` | A non-causal fill, and late-known rows, each with its justification or `null`. |
| `status` | `certified`, `certified_with_exceptions` or `refused`. |
| `issued_at` | When. |
| `signature` | An Ed25519 signature over the certificate. Without the `cryptography` package it is `null`, with `unsigned_reason`. |

| Status | When |
|---|---|
| `certified` | No violations and no non-causal fills. |
| `certified_with_exceptions` | Violations or non-causal fills exist, and each carries a written justification (and `allow_non_causal` is set for a non-causal fill). |
| `refused` | Something is unjustified. The `leakage_certified` check then blocks `submit` and `approve`. |

A refused certificate is fixed by changing the data or the lag, or by adding a justification — then cloning the warrant, since the certificate is issued at creation.

### Status

A training warrant's `status` is computed, in this order: `revoked` if revoked; `expired` if past `expires_at`; `sealed` if sealed; otherwise its workflow `state`.

### Downloading the data

```python
# Download, verify and use the training data
table, manifest = my.training_data(w["id"])      # a pyarrow Table, checksum verified
print(manifest["rows"], manifest["checksum"], manifest["escrowed_holdout"])
df = table.to_pandas()                           # the _split column: train, validation, test
```

| Rule | Behaviour |
|---|---|
| Permission | `download` on the warrant. |
| Liveness | Refused if revoked (`not_approved`) or expired (`warrant_expired`). |
| Licence | The feature set's licence must allow `internal` redistribution. |
| Your conditions | Your grant conditions (row filters, masks, time bounds) apply: a download never shows what a direct read would have withheld. |
| Escrow | With `holdout: escrowed`, the `test` rows are not in the file. |
| Format | Parquet, with a `_split` column. |
| Checksum | A content hash over the table's canonical values, whatever the file format. |
| Record | A `downloaded` custody event carrying the checksum; audit `warrant.data_downloaded`. |

The manifest holds `warrant`, `rows`, `checksum`, `escrowed_holdout`, `split`, `seed`, `index`, `target`, `issued_at` and `issued_to`. The CLI equivalent is `python -m maya.cli warrant fetch <id> --out train.parquet`.

## Parameter sets

### Uploading parameters

Train anywhere, then upload the fitted values, naming the checksum you trained on:

```python
# Upload fitted parameters with the checksum they were trained on
ps = my.training.upload_parameters(w["id"], {"beta0": -3.1, "beta_ltv": 2.4},
                                   metrics={"auc": 0.81}, data_checksum=manifest["checksum"],
                                   notes="L2, C=1.0")
print(ps["verified_data"], ps["flag"])            # True None
```

| Field | Meaning |
|---|---|
| `values` | Parameter name → value. For a composite model, keys may be prefixed `<alias>.` with `member_alias` naming the member. |
| `metrics` | Whatever you measured. |
| `data_checksum` | The checksum of the data you trained on. |
| `name` | Defaults to `<warrant>-params-<timestamp>`. |
| `notes`, `member_alias` | Free text; the composite member these values are for. |

Uploading needs read access to the warrant and `C` on `parameter_set`, and is refused when the warrant is sealed, revoked or expired. Values are checked on upload: every declared parameter must be present and within its declared bounds, and every constant without a declared value must be supplied. Any problem refuses the upload, listing each one.

### Verified and unverified data

If `data_checksum` is one MAYA issued for this warrant's downloads, the set is `verified_data: true`. Otherwise — no checksum, or one MAYA never issued — it is flagged `unverified_data`, and `approve` passes `data_verified_or_justified` only with a written `justification` on the transition:

```python
# Approve an unverified set, on the record
my.training.parameter_transition(ps["id"], "approve",
                                 justification="Trained on the vendor's corrected file; see ticket 4411")
```

The upload writes a `parameters_uploaded` custody event with the checksum and the verification result, a lineage edge, and the audit entry `warrant.parameters_uploaded` (an event).

### Blind holdout scoring

```python
# Score against the escrowed test rows: metrics out, rows never
print(my.training.score_holdout(w["id"], parameter_set_id=ps["id"]))
# {'metrics': {'rmse': …, 'mae': …, 'rows': …}, 'attempt': 1, 'note': …}
```

MAYA evaluates the model on the `test` partition inside MAYA and returns RMSE, MAE and the row count — never rows. Pass a `parameter_set_id` or raw `values`. Every attempt is numbered, stored on the warrant and written to custody (`holdout_scored`), so repeated peeking is visible. Scoring needs a `target`, a non-empty test partition, and a model with a closed form: a declared black box is refused.

## Training warrant lifecycle

| Step | Call | Rule |
|---|---|---|
| Submit | `training.transition(id, "submit")` | Runs `contract_valid` and `leakage_certified`. |
| Approve | `training.transition(id, "approve", rationale=…)` | Adds `no_open_blocking_comments` and one `model_manager` approval, under SoD. |
| Parameter set | `training.parameter_transition(ps_id, "submit")`, then `"approve"` | Runs `parameters_within_bounds`, then `data_verified_or_justified`; one `model_manager` approval. |
| Seal | `training.seal(id)` | Needs `seal` (`P`) on the warrant and an approved warrant; a model with parameters also needs an approved parameter set. After sealing, no more parameters can be uploaded. |
| Revoke | `training.revoke(id, reason)` | The model owner (a `revoke` grant) or an administrator, with a reason. **Cascades:** every execution warrant drawn on it that is not already revoked is revoked too, and its owner notified. |
| Clone | `training.clone(id, **changes)` | A new draft version in the same family, `clone_of` the original. `changes` override spec keys; `featureset=` changes the feature set. The clone is created afresh: contract and certificate are re-issued. |

Every transition that moves writes a custody event named after it.

## Execution warrants

### Creating one

```python
# License the trained model to run in UAT and production
ew = my.execution.create(
    namespace="credit", name="pd-scoring",
    training_warrant_id=w["id"], parameter_set_id=ps["id"],
    spec={"environments": ["uat", "prod"], "valid_days": 90,
          "contact": "credit-model-owners@example.com",
          "limits": {"max_calls_per_day": 24, "max_rows_per_day": 500000},
          "covenants": [
              {"kind": "input_null_rate", "attr": "ltv", "max": 0.05},
              {"kind": "input_range", "attr": "ltv", "min": 0, "max": 2.5},
              {"kind": "output_range", "attr": "pd", "min": 0, "max": 1},
              {"kind": "staleness_days", "attr": "ltv", "max": 3}]})
```

Name a training warrant (and its parameter set) for a trainable model. A model with no parameters can be named directly with `model=`; naming a trainable model that way is refused.

| Spec key | Default | Meaning |
|---|---|---|
| `valid_days` | `90` | Validity, counted from sealing. |
| `environments` | `["dev"]` | Where it may run: any of `dev`, `uat`, `prod`. |
| `contact` | empty | Who callers are told to contact when it refuses them ("the model owner" when empty). |
| `limits` | `{}` | Rate and volume allowances: `max_calls_per_day`, `max_rows_per_call`, `max_rows_per_day`, each a positive whole number. |
| `covenants` | `[]` | Bounds evaluated on every execution report. |

The warrant's **manifest** freezes what it licenses: the model's name, version, IR hash, artifact hash and whether it is a black box; the parameter set's id, values hash and verification; the input contract, bindings, outputs and composite structure; the environments, covenants, limits and escalation contact.

### Covenants

Each covenant has a `kind`, usually an `attr`, and bounds. They are evaluated against the statistics you report with each run.

| Kind | Breached when |
|---|---|
| `input_null_rate` | the reported `null_rate` of `attr` exceeds `max` |
| `input_range` | the reported `min` of `attr` is below `min`, or its `max` is above `max` |
| `output_range` | the same, against the output statistics |
| `max_rows_per_day` | today's reported rows, including this report, exceed `max` |
| `staleness_days` | the reported `age_days` of `attr` exceeds `max` |

A breach **suspends** the warrant at once. **Limits** are different: they throttle and never suspend.

### Lifecycle and status

| Step | Rule |
|---|---|
| Submit | Runs `parameters_approved`. |
| Approve | One `model_manager` approval, plus one `model_owner` approval in a production namespace; SoD applies. |
| Seal | Needs `seal` (`P`) and an approved warrant. Sets `valid_from` to now and `valid_to` to now plus `valid_days`. |

The computed `status` is, in order: `revoked`, `suspended`, `expired` (past `valid_to`), `live` (sealed), otherwise the workflow state.

### Running under a warrant

| Call | Returns |
|---|---|
| `execution.token(id, environment)` | A signed token valid for 15 minutes, its claims and the public key. |
| `execution.bundle(id, environment)` | Everything needed to run: the manifest, the formula IR (and member IRs for a composite), the parameter values, a token and the status. |
| `execution.report(id, environment, rows, input_stats, output_stats)` | Whether it was accepted, any breaches, any limits exceeded, and the resulting status. |

Every one of these first checks the warrant, failing closed and naming the contact:

| Refusal | When |
|---|---|
| `not_approved` (409) | revoked, or not sealed and live |
| `warrant_suspended` (423) | a covenant was breached; the message carries the reason |
| `warrant_expired` (410) | past `valid_to` |
| `permission_denied` (403) | the environment is not one the warrant allows |
| `quota_exceeded` (429) | token and bundle only: today's `max_calls_per_day` or `max_rows_per_day` is used; resets at midnight UTC |

The token's claims are `warrant`, `id`, `env`, `model_ir_hash`, `params_hash`, `sub` (who asked) and `exp`. The token is the canonical JSON of the claims, base64url-encoded, a dot, and an Ed25519 signature over those bytes.

### Reporting a run

```python
# Report a run so covenants and limits are evaluated
out = my.execution.report(ew["id"], environment="prod", rows=184_220,
                          input_stats={"ltv": {"null_rate": 0.002, "min": 0.1, "max": 1.9,
                                               "age_days": 1}},
                          output_stats={"pd": {"min": 0.0004, "max": 0.61}})
print(out["status"], out["breaches"], out["limits_exceeded"])
```

A report is always recorded — it happened. It counts toward today's usage, increments the warrant's execution count and links the run into lineage. Then:

- **Limits exceeded** by this run (`max_rows_per_call`, or the day's totals including it) are returned in `limits_exceeded` and audited as `warrant.limit_exceeded` (an event). Nothing is suspended.
- **Covenant breaches** suspend the warrant: a `suspended` custody event by `covenant-monitor`, the audit entry `warrant.suspended` (an event), and a notification to the owner. Every later call fails with `warrant_suspended`.

### Reinstating, revoking and expiry

| Action | Rule |
|---|---|
| `execution.reinstate(id, reason)` | The model owner (a `grant` on the warrant) or an administrator, with a written reason. Clears the suspension; custody `reinstated`, audit `warrant.reinstated`. |
| `execution.revoke(id, reason)` | The model owner (`revoke`) or an administrator, with a reason. Permanent; custody `revoked`, audit `warrant.exec_revoked`. |
| Expiry notice | The scheduler notifies the owner once, 30 days before `valid_to`. |

## Custody events

| Warrant | Events |
|---|---|
| Training | `created`, `downloaded` (with checksum), `parameters_uploaded` (with checksum), `holdout_scored`, one per workflow transition taken (`submit`, `approve`, …), `sealed`, `revoked`, `bundle_exported` (with the bundle's digest) |
| Execution | `created`, one per workflow transition taken, `sealed`, `suspended`, `reinstated`, `revoked` |

## Reproducibility bundles

A bundle is a signed zip exported from a training warrant: what a validator or a regulator needs to check the warrant without MAYA.

```python
# Export a bundle and save it
out = my.training.export_bundle(w["id"])
open("pd-2026q1.zip", "wb").write(my.admin.blob(out["blob"])["data"])
print(out["size"], out["manifest"]["reexecutable"], out["manifest"]["not_reexecutable_reason"])
```

Export needs read access to the warrant and an `external` redistribution licence on its feature set — a bundle leaves the firm. It uses the warrant's approved parameter set (or, failing that, the most recent upload), writes a `bundle_exported` custody event and the `bundle.exported` audit entry, and stores the zip as a blob. The CLI equivalent is `python -m maya.cli export bundle <id> --out pd-2026q1.zip`.

### Contents

| File | Holds |
|---|---|
| `manifest.json` | File hashes, data content hash, output hash, re-executability and its reason, model inputs, bindings, the sealed feature set reference, and the signature |
| `warrant.json` | The warrant: URI, name, version, spec, feature set reference, contract report, backends, custody log |
| `certificate.json` | The signed leakage certificate |
| `data/training.parquet` | The training data, **all partitions**, including the escrowed test rows |
| `model/model_version.json` | Version, maturity, IR hash, artifact hash, input contract, definition hash |
| `model/formula_ir.json` | The model's mathematics as the typed IR |
| `model/reference_model.py` | Python generated from the IR — only when re-executable |
| `model/parameters.json`, `model/parameter_set.json` | The parameter values, and the parameter set record |
| `model/spec.tex` | The specification source |
| `environment.json` | The export's Python version, the declared environment and the backend set |
| `lib/canonical.py`, `lib/chunker.py` | MAYA's canonical hash and chunker — they define the hash, so they ship |
| `verify.py` | The offline verifier |

The manifest's signature is Ed25519 over the canonical JSON of the file-hash list, with the public key and key id beside it.

!!! warning "The test rows travel in the bundle"
    A bundle carries every partition, so that the recipient can re-hash and re-execute everything. The escrow that keeps test rows out of a trainer's download does not apply to a bundle.

### When a bundle cannot re-execute

| Case | `not_reexecutable_reason` |
|---|---|
| A declared black box | MAYA holds no executable specification; the bundle verifies inputs only and says so. |
| A composite model | Composite re-execution in `verify.py` is not shipped in this build. |
| A trainable model with no parameter set | No parameter set has been uploaded against the warrant. |

### Verifying a bundle

`verify.py` needs Python, `pyarrow` and `numpy`; with `cryptography` installed it also checks the signature. It prints a JSON report and exits non-zero on any failure.

| Check | What it proves |
|---|---|
| `file hash <name>` | Each listed file matches its SHA-256. |
| `Ed25519 signature over the file list` | The file list is unchanged since it was signed by the key in the manifest (`not checked` without `cryptography`). |
| `data content hash (canonical, value-based)` | The data's values re-hash, with the shipped canonical encoder, to the recorded content hash. |
| `re-execution output hash` | The reference model, run on the data with the parameters, reproduces the recorded output hash (values rounded to 10 decimal places). Reported as not performed when the bundle is not re-executable. |

```bash
# Verify with nothing from MAYA installed
unzip -p pd-2026q1.zip verify.py > verify.py
python verify.py pd-2026q1.zip
```

!!! note "Whose key signed it"
    The signature is checked against the public key the manifest carries. To know the bundle came from your MAYA, compare the manifest's `signature.public_key` or `key_id` with your instance's, which `GET /api/v1/custody/anchors` reports as `public_key` and `key_id`.

| Where | How it verifies |
|---|---|
| `python verify.py bundle.zip` | The bundle's own verifier, on your machine. |
| `python -m maya.cli export verify bundle.zip` | The same: runs the bundle's own `verify.py` in a clean interpreter. It executes code from the bundle — use it only on bundles you chose. |
| `POST /api/v1/bundles/verify` (`training.verify_bundle`) | Executes only for a bundle signed by this instance's key whose every file matches its signed hash and which has no unlisted files — and then with MAYA's own verifier, never the uploaded one. Any other bundle is reported with `"executed": false` and the reason. |
| `maya.sdk.offline(bundle)` | Checks every file hash and the signature before serving anything, never runs code from the bundle, and serves the read calls: `training.get`, `training.data`, `training_data`, `models.get`, `parameters`, `certificate`, `predict`. |

```python
# Read a bundle offline and evaluate the signed formula
import numpy as np
import maya.sdk as maya
with maya.offline("pd-2026q1.zip") as off:
    print(off.verify()["verified"])
    table, manifest = off.training_data()
    print(off.predict({"ltv": np.array([0.5, 0.9])}))
```
