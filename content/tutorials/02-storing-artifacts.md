---
title: Storing model artifacts
slug: storing-artifacts
section: The register
order: 20
icon: archive
summary: "Where the model file lives: MAYA's content-addressed store for artifacts you own, a verified digest for the ones somebody else holds, which formats execute code when they load, and why documents are stored differently from artifacts."
audience: Engineers, Model owners
---

# Storing model artifacts

There are two honest answers to "where does the model file live", and MAYA
supports both. Which one you want depends on whether anybody else is already
custodian of the bytes.

| | **Hold it in MAYA** | **Name it, hold it elsewhere** |
|---|---|---|
| Use when | you trained it, and nothing else treats it as evidence | a vendor binary under licence, a checkpoint in your ML platform, a 40GB file you will not duplicate |
| MAYA has | the bytes, addressed by their hash | the digest and a URI |
| The engine | fetches from MAYA and verifies | resolves your URI and verifies |
| On the warrant | `held_by_maya: true`, with a `fetch` path | `held_by_maya: false` |

Neither is a fallback for the other, and the warrant says which one you have
rather than leaving an engine to guess from a URI scheme.

## Holding it in MAYA

The store is content-addressed: **a file's name is its own SHA-256**.

```bash
DIGEST=$(sha256sum pd_smallbiz_3.2.1.onnx | cut -d' ' -f1)

curl -u d.raman:… -X POST \
  "http://localhost:5006/api/v1/artifacts?format=onnx&digest=sha256:$DIGEST" \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @pd_smallbiz_3.2.1.onnx
```

```json
{"digest": "sha256:9f2c1a7e…", "size": 81443712, "format": "onnx",
 "uri": "maya://artifact/sha256:9f2c1a7e…", "executes_on_load": false,
 "stored": true, "detail": "81.4 MB"}
```

They land in well-structured folders under the data directory, two levels of
fan-out because a single directory holding a hundred thousand files is slow on
every filesystem that has ever existed:

```
data/artifacts/9f/2c/9f2c1a7e…      the file — its name IS its sha256
data/artifacts/9f/2c/9f2c1a7e….fmt  one word: the format it was declared as
```

Three properties follow from naming a file after its own hash, and each removes
a control somebody would otherwise have to perform:

- **The same weights stored twice are stored once**, because identical bytes land
  on an identical path. A challenger differing from its champion by a
  configuration does not double the storage.
- **An artifact cannot be edited in place**, because edited bytes are a different
  address.
- **"These are the bytes the warrant names" is true by construction**, rather
  than by a check somebody remembered to write.

Pass `digest` when you know what you are uploading. It is **checked**, not
trusted: a truncated upload is refused rather than stored under the address of
whatever arrived.

```bash
curl -u a.mehta:… http://localhost:5006/api/v1/artifacts/sha256:9f2c1a7e…/verify
curl -u a.mehta:… http://localhost:5006/api/v1/artifact-usage
```

Verification re-derives the hash from the bytes on disk. Content addressing makes
tampering hard rather than impossible — the filesystem is still a filesystem —
and this is how you find out. It is a separate call because re-hashing a
multi-gigabyte file is not something a read should do every time.

There is an **8 GiB ceiling**, deliberately. A governance platform is not a model
store of last resort, and somebody should have to think before putting a
foundation-model checkpoint in one.

### Which formats, and which of them run code

```bash
curl -u d.raman:… http://localhost:5006/api/v1/artifact-formats
```

| Format | For | Executes on load |
|---|---|---|
| `onnx` | a portable graph, loadable without its framework | no |
| `safetensors` | weights only, no code path on load | no |
| `pmml` / `pfa` | verbose, old, readable by anything | no |
| `json` | a rule set, a scorecard, a prompt bundle | no |
| `gguf` | quantised weights for local inference | no |
| `torchscript` | a TorchScript archive — carries code | **yes** |
| `tar` | several files: a tokenizer beside its weights | **yes** |

The last two are accepted and load **in the sandbox and nowhere else**. The
distinction is recorded so nobody has to remember it, and the warrant carries the
flag so an engine is not inferring it from a file extension.

The list is closed, and there is no `pickle`. An artifact's format decides how it
is loaded, and "we will work it out at load time" is how a pickle gets
deserialised in a control plane.

## Naming one you hold elsewhere

```json
{"artifact_digest": "sha256:9f2c1a7e4b3d0865ca19e2f7b04d3a61c8e5079fb2d4a136e0c85719ad3f2b4c",
 "artifact_uri": "s3://maya-artifacts/credit/pd_smallbiz_3.2.1.onnx"}
```

A digest MAYA cannot resolve is **not an error**. Plenty of artifacts live in a
model store somewhere else and are named here so the engine can check them on
load — and that remains checkable at execution time: the warrant carries the
digest, the engine verifies what it actually loaded, and a swapped artifact is
*detected* rather than assumed away.

When the digest **does** resolve in the store, MAYA fills in the URI and the size
itself. The store is the authority on its own contents; a caller who names both
and gets the URI wrong is corrected rather than believed.

## Formats, and how each is reached

The `realisation.runtime` says how an engine turns an artifact into something
callable, and each runtime declares the keys it needs. This is the second of the
grammar's four axes — see [the warrant grammar](/help/warrants#the-four-axes).

| Artifact | `runtime` | `entry` carries |
|---|---|---|
| ONNX graph | `onnx` | `graph`, opset, input/output names |
| PMML scorecard | `pmml` | `document`, model name, PMML version |
| Python source bundle | `python.callable` | `module`, `attr`, hyperparameters |
| Container image | `container` | `image`, command |
| Pricing library | `quantlib` | `instrument`, `pricing_engine`, term structures |
| SQL | `sql` | `statement`, `dialect` |
| Spreadsheet | `spreadsheet` | `workbook`, `sheet`, `input_cells`, `output_cells` |
| Rulebook | `rules` | `ruleset`, `engine` |
| Prompt bundle | `llm.prompt` | `provider`, `base_model`, `prompt_digest`, decoding |
| Agent graph | `llm.agent` | `provider`, `base_model`, `graph`, `max_steps` |
| Optimisation | `solver` | `formulation`, `solver` |
| Vendor black box | `descriptor_only` | *nothing* |

Declare `runtime` and `entry` in the version's kernel and they travel in every
warrant:

```json
"kernel": {
  "parameter_kind": "learned_weights",
  "fit_procedure": "train",
  "runtime": "onnx",
  "entry": {"graph": "pd_smallbiz_3.2.1.onnx", "opset": 18,
            "input_names": ["features"], "output_names": ["probability"]},
  "artifact_format": "onnx"
}
```

## When you cannot supply an artifact

Leave the runtime out and the warrant is issued **descriptor-only**. MAYA carries
the governance, the schemas, the operating boundary and the authority; the engine
supplies the model.

This is the honest state for a vendor black box, and it is recorded as such
rather than papered over. What a descriptor-only model cannot be warranted for is
`fit` — you cannot inhabit a parameter object nothing on this side can reach.

Guessing would be worse. A warrant asserting `python.callable` with an entry
nobody filled in fails at the artifact, which is the most expensive place to
discover that a registration was incomplete.

## The prompt bundle case

For a T5 model the "artifact" is a prompt, its few-shot examples, its output
schema and its tool manifest. Digest the bundle and version it in git like any
other source:

```json
"parameters": {
  "kind": "llm_configuration",
  "source": {"binding": "artifact", "uri": "git://internal/kyc-prompts@a71f0c9",
             "components": ["system_prompt", "few_shot_examples", "output_schema",
                            "tool_manifest"]},
  "digest": "sha256:7c1b04ea..."
}
```

A prompt change is a **version change**. A RAG corpus that moves without one is a
model whose behaviour changed without a version, which is the generative
equivalent of the feature-store failure that
[feature contracts](/help/features-and-two-clocks#feature-contracts) exist to prevent — which is why the
corpus is pinned by revision too.

## Documents are stored, and stored differently

The artifact is the thing that runs. The **document** is the thing somebody
wrote about it, and MAYA does store those bytes rather than a reference to them.

The difference is deliberate. An artifact can be huge, is already held by
whatever built it, and is reached through a URI the engine resolves; MAYA holds
the digest so it can check that what ran is what was approved. A document is
small, has no other custodian that treats it as evidence, and is the thing a
supervisor asks to see. Keeping only a link to it would put the evidence on
somebody else's share drive.

So documents go into a content-addressed store under `data/attachments`, keyed by
the SHA-256 of their bytes:

```bash
curl -u j.okafor:… -X POST http://localhost:5006/api/v1/attachments \
  -F urn="maya://model/credit.pd.smallbiz" \
  -F kind=model_development_document \
  -F title="SB PD — Model Development Document" \
  -F file=@mdd.md
```

With no `semver`, it lands on the **current version**, because a development
document describes the coefficients it printed rather than their replacement.
Pass `model_level=true` for something genuinely about the model — a board paper —
and you have to pass it deliberately.

The response carries the digest. That digest is the storage key, which means the
same file attached to forty models is one stored object, a byte cannot change
without becoming a different document, and a read re-hashes before returning.
What an approver accepted is what a reader later fetches — checked, not assumed.

Filing is not accepting. Somebody holding `document:review` — and never the
person who filed it — has to accept it:

```bash
curl -u a.mehta:… -X POST \
  http://localhost:5006/api/v1/attachments/$ID/review \
  -H 'Content-Type: application/json' \
  -d '{"accept": true, "note": "back-testing section complete"}'
```

See [Documents on file](/help/documentation#documents-on-file) for supersession, rejection and
what the platform can and cannot read.

## What is never stored

Personal data never goes inline into the evidence chain. Law L-18: an evidence
node carrying personal data holds an **erasable pointer**, not the data — so an
erasure request can be honoured without breaking the hash chain that everything
else depends on.
