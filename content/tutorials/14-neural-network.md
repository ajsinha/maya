---
title: A neural network, end to end
slug: neural-network-end-to-end
section: Worked models
order: 53
icon: diagram-2
summary: A transaction-fraud network trained, its weights uploaded into MAYA's content-addressed store, warranted and served — the case where P is twenty million numbers, so it is an artifact rather than a record. Where the file lives on disk, why the digest is its address, and which formats run code when they load.
audience: Data scientists, ML engineers, Validators
---

# A neural network, end to end

The reasonable objection to everything so far: *a neural network is not an
equation.* True, and it does not matter. The definition `f : P ⊗ X → D(Y)` is
indifferent to how big `P` is. What changes is the **medium**: three numbers are
a record, twenty million are a file.

**What you are building.** A transaction-fraud classifier — a small feed-forward
network over aggregated card behaviour — trained outside MAYA, stored inside it,
and served with the same warrant machinery as the regression.

| | |
|---|---|
| `P` is | ~20 million weights |
| Filled by | a training run, in the bank's ML platform |
| `parameter_kind` | `learned_weights` |
| `fit_procedure` | `train` |
| Derived class | **T4** — trained |
| Runtime | `onnx` |
| Where `P` lives | in **MAYA's artifact store**, addressed by its own hash |

---

## 1 · Where the bytes actually live

Yes — the weights sit in well-structured folders under the data directory. The
layout is not decorative:

```
data/artifacts/
  9f/
    2c/
      9f2c8a71e4b0…d3   ← the file. Its name IS its sha256.
      9f2c8a71e4b0…d3.fmt  ← one word: the format it was declared as
  c4/
    1f/
      c41f0b93…7a
```

Three properties come out of naming a file after its own hash, and each removes
a control somebody would otherwise have to perform:

| Property | Because |
|---|---|
| Storing the same weights twice stores them once | the same bytes land on the same path |
| An artifact cannot be edited in place | edited bytes are a different address |
| "These are the bytes the warrant names" is true by construction | the name is the hash |

The two-level fan-out (`9f/2c/…`) exists because a single directory holding a
hundred thousand files is slow on every filesystem that has ever existed.

---

## 2 · Train it, wherever you train things

MAYA does not train. It issues the warrant, hands over the data, and takes the
result back.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/fraud.card.nn","environment":"prod",
       "principal":"svc/ml-platform","featureset":"card_behaviour",
       "featureset_version":3,"verb":"train",
       "window":{"from":1672531200,"to":1735603200},"as_of":1736899200}'

curl -u svc/ml-platform:svc-pw \
  "localhost:5006/api/v1/featuresets/card_behaviour/versions/3/data?as_of=1736899200&format=parquet" \
  -o train.parquet
```

Train, then **export to a format that does not execute on load**:

```python
torch.onnx.export(model, sample, "fraud_v3.onnx", opset_version=17)
```

---

## 3 · Put the weights in MAYA

```bash
DIGEST=$(sha256sum fraud_v3.onnx | cut -d' ' -f1)

curl -u d.raman:dev-pw -X POST \
  "localhost:5006/api/v1/artifacts?format=onnx&digest=sha256:$DIGEST" \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @fraud_v3.onnx
```

```json
{"digest": "sha256:9f2c8a71e4b0…d3",
 "size": 81443712,
 "format": "onnx",
 "uri": "maya://artifact/sha256:9f2c8a71e4b0…d3",
 "means": "an ONNX graph. Portable, typed, and loadable without the framework that produced it",
 "executes_on_load": false,
 "stored": true,
 "detail": "81.4 MB"}
```

**Pass the digest.** It is *checked*, not trusted — a truncated upload is refused
rather than stored under the address of whatever arrived:

```json
{"error": "artifact_digest_mismatch",
 "detail": "the bytes hash to sha256:44b1c0… and you said sha256:9f2c8a71…",
 "remediation": "the upload was truncated or is not the file you meant; storing
                 it under the address of what arrived would give you an artifact
                 nobody asked for"}
```

### Which formats, and which of them run code

```bash
curl -u d.raman:dev-pw localhost:5006/api/v1/artifact-formats
```

| Format | For | Executes on load |
|---|---|---|
| `onnx` | a portable graph, loadable without its framework | no |
| `safetensors` | weights only, no code path — the reason to prefer it over a pickle | no |
| `pmml` / `pfa` | verbose, old, readable by anything | no |
| `json` | a rule set, a scorecard, a configuration | no |
| `gguf` | quantised weights for local inference | no |
| `torchscript` | a TorchScript archive — carries code | **yes** |
| `tar` | several files together: tokenizer beside weights, adapter beside base | **yes** |

The last two are accepted, and they load **in the sandbox and nowhere else**. The
platform records which is which so that nobody has to remember, and the warrant
carries the flag so an engine is not inferring it from a file extension.

There is no `pickle`. The format list is closed on purpose: an artifact's format
decides how it is loaded, and "we will work it out at load time" is how a pickle
gets deserialised in a control plane.

---

## 4 · The version names the artifact

```bash
curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/fraud.card.nn/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver":"3.0.0",
       "artifact_digest":"sha256:9f2c8a71e4b0…d3",
       "kernel":{"parameter_kind":"learned_weights","fit_procedure":"train",
                 "runtime":"onnx","artifact_format":"onnx",
                 "entry":{"graph":"fraud_v3.onnx"},
                 "input_schema":[{"name":"txn_velocity_1h","dtype":"numeric"},
                                 {"name":"mcc_entropy_30d","dtype":"numeric"},
                                 {"name":"geo_jump_score","dtype":"numeric"}],
                 "output_schema":[{"name":"fraud_probability","dtype":"numeric"}],
                 "environment":{"opset":17,"exporter":"torch 2.4.1"}}}'
```

You do not send `artifact_uri`. **The store is the authority on its own
contents**: MAYA resolves the digest, fills in the URI and the size, and takes
the format from the store if the kernel did not declare one. A caller who names
both and gets the URI wrong is corrected rather than believed.

A digest MAYA cannot resolve is **not** an error — plenty of checkpoints live in
a model store elsewhere and are named here so the engine can verify them on
load. The distinction is recorded rather than forbidden, and the warrant carries
it as `held_by_maya`.

---

## 5 · What the warrant tells the engine

```bash
curl -u svc/fraud:svc-pw -X POST localhost:5006/api/v1/resolve \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/fraud.card.nn#champion","environment":"prod",
       "principal":"svc/fraud","declared_use":"transaction_screening"}'
```

```json
{"realisation": {
   "runtime": "onnx",
   "entry": {"graph": "fraud_v3.onnx"},
   "artifact": {
     "uri": "maya://artifact/sha256:9f2c8a71e4b0…d3",
     "digest": "sha256:9f2c8a71e4b0…d3",
     "format": "onnx",
     "size": 81443712,
     "executes_on_load": false,
     "held_by_maya": true,
     "fetch": "/api/v1/artifacts/sha256:9f2c8a71e4b0…d3"},
   "environment": {"opset": 17, "exporter": "torch 2.4.1"}}}
```

An engine holding this warrant needs nothing else. It knows **what** the bytes
are, **how big** they are before it starts fetching, **whether loading them runs
code**, and **where to get them** — and it verifies the digest before the graph
is loaded, so a changed file is refused rather than run.

---

## 6 · Validating twenty million numbers

You cannot read the parameters. That is a real difference, and pretending
otherwise produces a validation report full of things nobody did.

What the platform actually supports:

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/validations \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/fraud.card.nn","semver":"3.0.0","scope":"full",
       "plan":"held-out replay; stability under input perturbation;
               subgroup performance; benchmark against the logistic incumbent"}'

curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/validations/<id>/replay-from-storage \
  -H 'Content-Type: application/json' \
  -d '{"featureset":"card_behaviour","version":3,"as_of":1736899200,
       "sample":5000}'
```

- **Replay** is bit-exact, because the artifact is content-addressed and the
  graph is deterministic. If a replay of the champion does not reproduce the
  recorded scores, either the file moved or the runtime did — and both are
  findings.
- **Benchmark against the incumbent**, registered as a `benchmark_for` edge.
  A network that beats nothing has not earned its opacity.
- **Subgroup performance** is a finding-generating check rather than a metric on
  a dashboard, because a gap that nobody is obliged to close is a gap.
- **Explanation attaches as a document**, not as a claim inside the model. The
  SHAP study is evidence with an author and a date, reviewable like any other.

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/attachments \
  -F 'kind=validation_evidence' -F 'subject_type=model_version' \
  -F 'subject_id=<version id>' -F 'title=SHAP attribution study, v3' \
  -F 'file=@shap_v3.pdf'
```

---

## 7 · Retraining is a new version, not a new parameter set

This is where a network differs from the regression, and it is worth being
precise about why.

For an OLS model the kernel is the *equation* and the coefficients are a point
of `P`; refitting moves the point. For a network the artifact **is** `P`, and it
is also, inseparably, the computation graph. A retrained network is new weights
*and* potentially a different graph in the same file.

So: **retraining a network creates a new version.** Not because retraining is
more dangerous, but because the medium does not let you separate the two, and
pretending it does would let a graph change arrive labelled as a recalibration.

```bash
curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/fraud.card.nn/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver":"3.1.0","artifact_digest":"sha256:c41f0b93…7a", ... }'
```

The old artifact stays. Nothing deletes it, the old version keeps naming it, and
a replay of a decision made last March still finds the file that made it.

---

## 8 · Serve and monitor

```bash
curl -u svc/fraud:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/fraud.card.nn#champion","environment":"prod",
       "principal":"svc/fraud","declared_use":"transaction_screening",
       "inputs":{"features":{"txn_velocity_1h":11,"mcc_entropy_30d":2.7,
                             "geo_jump_score":0.83}}}'

curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/fraud.card.nn","kind":"score_drift",
       "test":"psi","threshold":0.2,
       "reference":{"featureset":"card_behaviour","version":3}}'
```

Score drift is the leading indicator here. Fraud labels arrive with a chargeback
lag measured in months, so a `performance` monitor is correct and slow; the
score distribution moves first, and moves for reasons worth investigating before
the labels confirm them.

Check the bytes periodically as well — content addressing makes tampering hard,
not impossible:

```bash
curl -u a.mehta:val-pw \
  localhost:5006/api/v1/artifacts/sha256:9f2c8a71e4b0…d3/verify
```

```json
{"intact": false, "recomputed": "sha256:11ee…",
 "detail": "the bytes on disk are NOT what this address promises;
            do not run this artifact and raise a security incident"}
```

---

## Next

[An LLM application](/tutorials/llm-end-to-end), where the base model is
somebody else's, the artifact you hold is a configuration, and the hard question
is what "the model" even refers to.
