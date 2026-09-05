---
title: A neural network, end to end
slug: neural-network-end-to-end
section: Worked models
order: 53
icon: diagram-2
summary: A transaction-fraud network trained outside MAYA, its weights uploaded into the content-addressed store, warranted and served — the case where P is twenty million numbers, so it is a file rather than a record. Where the bytes live and why their name is their hash, which formats run code when they load, law L-W12, and exactly where the sandbox stops protecting you.
audience: Data scientists, ML engineers, Validators
---

# A neural network, end to end

The reasonable objection to everything so far: *a neural network is not an
equation.* True, and it does not matter. The definition `f : P ⊗ X → D(Y)` is
indifferent to how big `P` is. What changes is the **medium**, and there is a
line in the source where it changes.

```python
# core/parameters/common.py
MAX_INLINE_VALUES = 4096
```

Below it, `P` is a record a reviewer reads. Above it, `P` is a file, and the
register holds its address:

```json
{"error": "parameters_too_large",
 "detail": "20117248 parameters is an artifact rather than a record; the
            register holds up to 4096 inline",
 "remediation": "store them in the artifact store and supply values_uri with
                 their digest"}
```

That refusal is this whole tutorial in five lines.

**What you are building.** A transaction-fraud classifier — a small feed-forward
network over aggregated card behaviour — trained outside MAYA, stored inside it,
and served with the same warrant machinery as the regression.

| | |
|---|---|
| `P` is | ~20 million weights |
| Filled by | a training run, in the bank's ML platform |
| `parameter_kind` | `learned_weights` |
| `fit_procedure` | `train` |
| `adaptive` | `false` — and §7 is about what happens when it is not |
| Derived class | **T3** — machine-learned |
| Runtime | `onnx` |
| Where `P` lives | in MAYA's artifact store, addressed by its own hash |

---

## 1 · Where the bytes actually live

Yes — the weights sit in well-structured folders under the data directory. The
layout is not decorative:

```
data/artifacts/
  9f/
    2c/
      9f2c8a71e4b0…d3       ← the file. Its name IS its sha256.
      9f2c8a71e4b0…d3.fmt   ← one word: the format it was declared as
  c4/
    1f/
      c41f0b93…7a
```

Three properties come out of naming a file after its own hash, and each removes
a control somebody would otherwise have to perform:

| Property | Because |
|---|---|
| Storing the same weights twice stores them once | the same bytes land on the same path — which matters when a challenger differs from its champion by a configuration rather than a file |
| An artifact cannot be edited in place | edited bytes are a different address, and the old one still resolves to what was approved |
| "These are the bytes the warrant names" is true by construction | the name is the hash, so there is no check to remember to write |

Two details in that listing are deliberate and worth understanding.

**The two-level fan-out** (`9f/2c/…`) exists because a single directory holding a
hundred thousand files is slow on every filesystem that has ever existed.

**The format lives in a sidecar rather than in the file.** The address is derived
from the content, so the content *cannot* carry the format: two uploads with
identical bytes and different declared formats are the **same artifact**, and
the first declaration is the one that stands. The sidecar lets the warrant
builder answer *how is this loaded* on every build without a database round trip.
Losing it costs a lookup, not an artifact — the format is also on the version
manifest.

**Uploads are streamed, never buffered.** Bytes are hashed and written as they
arrive, into a staging file that is moved into place only when the whole thing
has landed — so a reader never sees half an object under a digest that promises
the whole one, and the platform is not the process that discovers a model file
does not fit in memory twice.

---

## 2 · Train it, wherever you train things

MAYA does not train. It issues the warrant, hands over the data, and takes the
result back.

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/fit-warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/fraud.card.nn","environment":"prod",
       "principal":"svc/ml-platform","declared_use":"model_development",
       "featureset":"card_behaviour","featureset_version":3,
       "window":{"from":1672531200,"to":1735603200},"as_of":1736899200}'

curl -u svc/ml-platform:svc-pw \
  "localhost:5006/api/v1/featuresets/card_behaviour/versions/3/data?as_of=1736899200&format=parquet" \
  -o train.parquet
```

No `verb` field — a fit warrant's verb is `fit`, and that this fit is a
*training run* comes from the version's `fit_procedure`, which is the same fact
that makes the class T3. The three laws checked before signature are the same
three the regression met: `L-W3`, `L-W9` and `L-W10`.

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
 "detail": "the bytes hash to sha256:44b1c0be9d1f2a3e… and you said
            sha256:9f2c8a71e4b0d33c…",
 "remediation": "the upload was truncated or is not the file you meant; storing
                 it under the address of what arrived would give you an artifact
                 nobody asked for"}
```

The store's other refusals are worth knowing before you meet them at three in
the morning: `malformed_digest` (an address is `sha256:` and exactly 64
lowercase hex characters, checked before any path is built — a digest is
untrusted input and a path derived from one is a file-read primitive),
`empty_artifact`, `unknown_format`, and `artifact_too_large` above the **8 GiB**
ceiling, whose remediation says why the ceiling is there: *a governance platform
is not a model store of last resort.*

### Which formats, and which of them run code

```bash
curl -u d.raman:dev-pw localhost:5006/api/v1/artifact-formats
```

| Format | For | Executes on load |
|---|---|---|
| `onnx` | a portable graph, loadable without its framework | no |
| `safetensors` | weights only, no code path — the reason to prefer it over a pickle | no |
| `pmml` | verbose, old, readable by anything | no |
| `pfa` | a PFA document | no |
| `json` | a rule set, a scorecard, a configuration | no |
| `gguf` | quantised weights for local inference | no |
| `torchscript` | a TorchScript archive — carries code | **yes** |
| `tar` | several files together: a tokenizer beside its weights, an adapter beside its base | **yes** |

Eight formats, and the list is **closed on purpose**: an artifact's format
decides how it is loaded, and "we will work it out at load time" is how a pickle
gets deserialised in a control plane. There is no `pickle`.

The last two are accepted and flagged, and the platform records which is which
so nobody has to remember. What it does with the flag is the subject of §6, and
the honest answer is narrower than you would hope.

---

## 4 · The version names the artifact

```bash
curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/fraud.card.nn/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver":"3.0.0",
       "artifact_digest":"sha256:9f2c8a71e4b0…d3",
       "kernel":{"parameter_kind":"learned_weights","fit_procedure":"train",
                 "adaptive":false,
                 "runtime":"onnx","artifact_format":"onnx",
                 "entry":{"graph":"fraud_v3.onnx"},
                 "input_schema":[{"name":"txn_velocity_1h","dtype":"numeric"},
                                 {"name":"mcc_entropy_30d","dtype":"numeric"},
                                 {"name":"geo_jump_score","dtype":"numeric"}],
                 "output_schema":[{"name":"fraud_probability","dtype":"numeric"}],
                 "environment":{"opset":17,"exporter":"torch 2.4.1"}},
       "contract":{"assumptions":[{"key":"txn_velocity_1h","minimum":0,"maximum":400}],
                   "guarantees":[{"key":"auc","minimum":0.88}]}}'

curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/fraud.card.nn/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure":400000000,"purpose_class":"risk_management",
       "feature_count":180,"interpretable":false}'
```

```json
{"tier": 1, "materiality": "moderate", "complexity": "advanced",
 "rationale": "materiality=moderate (exposure 400,000,000 in band moderate,
               purpose risk_management); complexity=advanced (class T3);
               tau(moderate,advanced)=Tier 1 under ruleset 2026.09.1"}
```

**Tier 1 at a fifth of the regression's exposure.** Complexity is a meet over its
declared components and this model scores on three of them — an opaque class,
more than fifty features, and no claim of interpretability — which puts it at
`advanced`, and `tau(moderate, advanced)` is Tier 1. The
[pricer](/tutorials/derivative-pricing-end-to-end) reached Tier 1 through
materiality at £8bn; this one reaches it through complexity at £400m. That is
what keeping the two orders apart buys, and why collapsing them into a single
score would lose it.

**You do not send `artifact_uri`.** The store is the authority on its own
contents: MAYA resolves the digest, fills in the URI and the size, and takes the
format from the store when the kernel did not declare one. A caller who names
both and gets the URI wrong is **corrected rather than believed**.

A digest MAYA cannot resolve is **not** an error — plenty of checkpoints live in
a model store elsewhere and are named here so an engine can verify them on load.
The distinction is recorded rather than forbidden, and the warrant carries it as
`held_by_maya`.

---

## 5 · What the warrant tells the engine

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/fraud.card.nn#champion","environment":"prod",
       "principal":"svc/fraud","declared_use":"transaction_screening"}'

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
   "environment": {"opset": 17, "exporter": "torch 2.4.1"}},
 "parameters": {"kind": "learned_weights", "mutable": false,
                "source": {"binding": "artifact",
                           "uri": "maya://artifact/sha256:9f2c8a71e4b0…d3"}}}
```

An engine holding that needs nothing else. It knows **what** the bytes are,
**how big** they are before it starts fetching, **whether loading them runs
code**, and **where to get them** — and `held_by_maya` tells it whether the
platform that authorised the run can also serve the file, rather than leaving it
to infer that from a URI scheme.

**The digest is not optional here, and that is `L-W12`:**

```json
{"law": "L-W12", "path": "realisation.artifact.digest",
 "detail": "this run's parameters come from the artifact, and the warrant does
            not carry the artifact's digest -- so an engine cannot check that
            what it loaded is what was approved",
 "remediation": "register the version with an artifact_digest, or upload the
                 file to MAYA and name it by its address; a location with no
                 digest cannot be verified, only fetched"}
```

When the parameter object **is** the file, *which numbers did this run at* and
*which bytes did it load* are the same question, and an artifact binding with no
digest answers neither.

**Notice the law is not written in terms of the class.** It bites hardest on a
network, but a PMML scorecard is **T2** and carries exactly the same exposure —
its coefficients are inside a document the engine loads. Keying `L-W12` on T3
would have missed that, and the miss would have looked like coverage. The law
quantifies over `parameters.source.binding == "artifact"`, which is a fact about
where `P` lives rather than a fact about how it was filled.

There is also a case where the *builder* refuses before any law runs: a version
whose `parameter_kind` is not `none`, with no approved parameter set and no
artifact at all, produces

```json
{"error": "no_approved_parameters",
 "detail": "this version's parameter object is 'learned_weights' and nothing
            inhabits it: no approved parameter set, and no artifact to carry one",
 "remediation": "record a parameter set and have somebody other than its author
                 approve it, or register the version against an artifact"}
```

rather than an artifact binding pointing at nothing. Naming the absent approval
is a better answer than a malformed document two steps later.

---

## 6 · The engine's side, and exactly where protection stops

An engine acting on that warrant does three things before the graph is loaded,
and one of them is not what people assume.

**It verifies the digest.** `verify_artifact` re-hashes the file and refuses:

```json
{"error": "artifact_mismatch",
 "detail": "9f2c8a71e4b0d33c… does not match the digest in the warrant
            (expected sha256:9f2c8a71e4b0d33c…, found sha256:11ee0a…)",
 "remediation": "the artifact has changed since it was approved; do not run it
                 and raise a security incident"}
```

and refuses just as firmly when there is nothing to check against —
`artifact_unverifiable`, because a warrant that names a digest and an engine
that does not check it is a chain of custody with its last link missing, and it
is the only link that touches what actually executes.

**It refuses a path outside its root.** The URI arrives inside a warrant, and a
warrant is a document from elsewhere; treating a path inside it as trustworthy
is how a governance system becomes a file-read primitive. The check is
`is_relative_to` rather than a string prefix, because `/srv/artifacts-backup/x`
begins with `/srv/artifacts` and is a different directory —
`artifact_outside_root`.

**It caches the session by digest, not by path.** Two versions that share a file
share a session; a version whose file changed gets a new one — and since the
digest is verified first, a changed file is refused rather than cached.

### The sandbox, described honestly

`SANDBOXED_RUNTIMES` holds **two** values: `onnx` and `pmml`. Those are the
runtimes that load bytes, so those are the ones that run in a child process with
the limits read off the warrant — `max_seconds` comes from the grant's tier, and
`max_memory_mb` falls back to the engine's own default because nothing puts one
on the warrant yet. QuantLib is deliberately absent because it loads no
artifact, and bound callables cannot be isolated at all: you cannot sandbox a
function handed to you in your own address space, which is one more reason not
to use them for anything real.

`GET /api/v1/engine` publishes what that boundary is and is not, rather than
implying a guarantee the process model does not provide:

```json
{"captive_engine": "enabled", "sandbox": "subprocess", "isolates": true,
 "protects_against": ["runaway cpu", "unbounded memory", "artifact crash"],
 "does_not_protect_against": [
   "a deliberately hostile artifact: the child shares the filesystem and the
    network namespace",
   "bound callables, which run unisolated by construction"]}
```

**So the `executes_on_load` flag is a statement, not a containment.** The store
records that `torchscript` and `tar` execute code when they load, and the warrant
carries it — and MAYA's captive engine implements **neither runtime**, so it
cannot run one at all. Whatever engine you point at a TorchScript archive is the
thing that has to isolate it, and the flag exists so that engine is not inferring
the risk from a file extension. Export to `onnx` or `safetensors` and the
question does not arise, which is the actual recommendation.

---

## 7 · Retraining is a new version — and `adaptive` is a new class

This is where a network differs from the regression, and it is worth being
precise about why.

For an OLS model the kernel is the *equation* and the coefficients are a point of
`P`; refitting moves the point. For a network the artifact **is** `P`, and it is
also, inseparably, the computation graph — a retrained network is new weights
*and* potentially a different graph in the same file, and nothing in the bytes
distinguishes the two.

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

### The one bit that changes the class

A network that updates **in flight** — online learning, a nightly incremental
pass against streaming feedback — is not T3:

```json
"kernel": {"parameter_kind": "learned_weights", "fit_procedure": "train",
           "adaptive": true}
```

`train` plus `adaptive` derives **T4**, and it is one boolean rather than a
different parameter kind because the distinction it draws is precise: whether
`P` moves *without a fit warrant*. A T3 model's parameters change when somebody
asks for them to; a T4 model's change because the world did. That is why it
earns its own class rather than a note in a field.

It shows up immediately in the tier, because `adaptive` scores a second point on
the complexity meet. The same twenty-feature uninterpretable network at moderate
materiality is `complex` and **Tier 2** as T3, and `advanced` and **Tier 1** as
T4 — a boolean on the kernel moving the control depth, derived rather than
argued.

---

## 8 · Validating twenty million numbers

You cannot read the parameters. That is a real difference, and pretending
otherwise produces a validation report full of things nobody did.

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/validations \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/fraud.card.nn","semver":"3.0.0","kind":"initial",
       "validators":["a.mehta","r.oyelaran"],
       "scope":["replay","stability","subgroup","benchmark"],
       "plan":{"replay":"held-out cohort from card_behaviour@v3, 5,000 rows",
               "stability":"score movement under +/-1% input perturbation",
               "subgroup":"performance by issuing country and card product",
               "benchmark":"against the logistic incumbent, same cohort"}}'

curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/validations/<id>/replay-from-storage
```

- **Replay is bit-exact**, because the artifact is content-addressed and the
  graph is deterministic. `replay-from-storage` re-reads the snapshot the episode
  pinned and takes nothing from the caller, so a mismatch is about the test
  rather than about who handed over which file. If a replay of the champion does
  not reproduce the recorded scores, either the file moved or the runtime did —
  and both are findings. `GET …/replayable` says up front whether the ground has
  moved under it.
- **Benchmark against the incumbent**, registered as a `benchmark_for` edge —
  which deliberately does *not* propagate, so the challenger will not appear in
  anybody's blast radius. A network that beats nothing has not earned its
  opacity.
- **Subgroup performance is a finding-generating check** rather than a metric on
  a dashboard, because a gap nobody is obliged to close is a gap.
- **Explanation attaches as a document**, not as a claim inside the model. The
  SHAP study is evidence with an author and a date, reviewable like any other —
  and filed by the first line, accepted by the second:

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/attachments \
  -F 'urn=maya://model/fraud.card.nn' \
  -F 'kind=model_development_document' -F 'semver=3.0.0' \
  -F 'title=SHAP attribution study, v3' -F 'file=@shap_v3.pdf'

curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/attachments/<attachment_id>/review \
  -H 'Content-Type: application/json' -d '{"accept":true,"note":"reproduced"}'
```

Filing is **version-level by default**, so a caller that says nothing files
against `3.0.0` rather than floating free of it — which is how an MDD describing
v2.1 ends up against a model serving v2.4. And a validator holds
`document:review` and **not** `document:attach`: the person who files a document
is not the person who accepts it, here as everywhere.

---

## 9 · Serve and monitor

```bash
curl -u svc/fraud:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/fraud.card.nn#champion","environment":"prod",
       "principal":"svc/fraud","declared_use":"transaction_screening",
       "inputs":{"features":{"txn_velocity_1h":11,"mcc_entropy_30d":2.7,
                             "geo_jump_score":0.83}}}'

curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/fraud.card.nn","name":"score PSI",
       "kind":"score_drift","test_key":"stability.psi",
       "threshold":{"max":0.2},"owner":"person/j.okafor",
       "cadence_days":1,"breach_severity":"Medium","escalate_after":3,
       "reference":{"sample":[0.01,0.02,0.04,0.09,0.21,0.44]}}'
```

**Score drift is the leading indicator here, and the reason is the label clock.**
Fraud labels arrive with a chargeback lag measured in months, so a `performance`
monitor is correct and slow — and MAYA will refuse to evaluate it early, with
`cohort_immature` and the date the cohort matures, rather than reporting an AUC
computed from whichever chargebacks happened to arrive first. The score
distribution moves before the labels do, and moves for reasons worth
investigating while there is still time.

PSI bins come from the **reference** sample's quantiles rather than today's,
which is what keeps the number comparable across evaluations, and empty bins are
floored rather than dropped — dropping them understates movement precisely when
the movement is total.

Check the bytes periodically as well. Content addressing makes tampering hard,
not impossible: the filesystem is still a filesystem.

```bash
curl -u a.mehta:val-pw \
  localhost:5006/api/v1/artifacts/sha256:9f2c8a71e4b0…d3/verify
```

```json
{"digest": "sha256:9f2c8a71e4b0…d3", "intact": false,
 "recomputed": "sha256:11ee0a…", "size": 81443712,
 "detail": "the bytes on disk are NOT what this address promises; do not run
            this artifact and raise a security incident"}
```

A separate call rather than something a read does every time, because re-hashing
a multi-gigabyte file on every fetch would be a control nobody could afford to
leave switched on.

---

## Next

[An LLM application](/tutorials/llm-end-to-end), where the base model is
somebody else's, the artifact you hold is a prompt, and the hard question is what
"the model" even refers to.
