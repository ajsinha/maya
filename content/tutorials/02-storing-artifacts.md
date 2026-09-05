---
title: Storing model artifacts
slug: storing-artifacts
section: The register
order: 20
icon: archive
summary: "Three kinds of bytes — the artifact that runs, the numbers it runs at, and the document somebody wrote about it — and the one digest that has to survive the journey from an upload to a load inside an engine you do not control."
audience: Engineers, Model owners
---

# Storing model artifacts

A model estate produces three kinds of bytes, and conflating any two of them
loses something specific.

| | What it is | Where it lives | Why not the others |
|---|---|---|---|
| **Artifact** | the thing that runs — a graph, a scorecard document, a checkpoint | content-addressed store, **or** somebody else's store with the digest named here | can be gigabytes; usually already has a custodian |
| **Parameter set** | the point of `P` a run is at — three coefficients, a calibration | a record in the register, reviewed and approved | three numbers are not a file, and a reviewer has to read them |
| **Document** | what somebody wrote about it | content-addressed store, always held here | small, has no other custodian that treats it as evidence, and is what a supervisor asks to see |

This page is mostly about the first. The through-line is a single **SHA-256**,
and the argument is that it gets checked in four places, by four parties, none
of whom has to trust the others.

---

## 1 · Two honest answers to "where does the file live"

|  | **Hold it in MAYA** | **Name it, hold it elsewhere** |
|---|---|---|
| Use when | you trained it, and nothing else treats it as evidence | a vendor binary under licence, a checkpoint in your ML platform, a 40 GB file you will not duplicate |
| MAYA has | the bytes, addressed by their hash | the digest and a URI |
| The engine | fetches from MAYA and verifies | resolves your URI and verifies |
| On the warrant | `held_by_maya: true` | `held_by_maya: false` |

Neither is a fallback for the other, and the warrant **says which** rather than
leaving an engine to infer it from a URI scheme.

---

## 2 · The store: a file's name is its own hash

```bash
DIGEST=$(sha256sum pd_smallbiz_3.2.1.onnx | cut -d' ' -f1)

curl -u d.raman:… -X POST \
  "localhost:5006/api/v1/artifacts?format=onnx&digest=sha256:$DIGEST" \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @pd_smallbiz_3.2.1.onnx
```

```json
{"digest": "sha256:9f2c1a7e…", "size": 81443712, "format": "onnx",
 "uri": "maya://artifact/sha256:9f2c1a7e…",
 "means": "an ONNX graph. Portable, typed, and loadable without the framework
           that produced it",
 "executes_on_load": false, "stored": true, "detail": "81.4 MB"}
```

Or, in Python, where the digest is computed for you in chunks because a model
file does not fit in memory twice:

```python
maya.artifacts.put("pd_smallbiz_3.2.1.onnx", format="onnx")
```

On disk, two levels of fan-out — a single directory holding a hundred thousand
files is slow on every filesystem that has ever existed:

```
data/artifacts/9f/2c/9f2c1a7e…       the file — its name IS its sha256
data/artifacts/9f/2c/9f2c1a7e….fmt   one word: the format it was declared as
```

Three properties follow from naming a file after its own hash, and each removes
a control somebody would otherwise have to perform:

- **The same weights stored twice are stored once.** A challenger differing from
  its champion only by a configuration does not double the storage, and the
  answer says `"stored": false` so a retry after a failed run is free rather
  than wasteful.
- **An artifact cannot be edited in place**, because edited bytes are a
  different address.
- ***These are the bytes the warrant names* is true by construction**, rather
  than by a check somebody remembered to write.

There is an **8 GiB ceiling**, deliberately. A governance platform is not a
model store of last resort, and somebody should have to think before putting a
foundation-model checkpoint in one. Over it, `artifact_too_large`.

---

## 3 · The four checkpoints

This is the part worth internalising. One number, checked four times, by parties
who do not trust each other.

**One — at the upload.** `digest` is optional and is *checked* rather than
trusted. A truncated upload is refused rather than stored under the address of
whatever arrived:

```json
{"error": "artifact_digest_mismatch",
 "detail": "the bytes hash to sha256:3b8e40f1c2…  and you said sha256:9f2c1a7e4b…",
 "remediation": "the upload was truncated or is not the file you meant; storing
   it under the address of what arrived would give you an artifact nobody asked for"}
```

**Two — when the version is created.** Name the digest and leave the URI out:

```json
{"semver": "3.2.1", "kernel": {…},
 "artifact_digest": "sha256:9f2c1a7e4b3d0865ca19e2f7b04d3a61c8e5079fb2d4a136e0c85719ad3f2b4c"}
```

If the store holds it, MAYA fills in the URI, the size and — if you did not say
— the `artifact_format`, from what it actually holds. The store is the authority
on its own contents; a caller who names both and gets the URI wrong is corrected
rather than believed.

A digest MAYA **cannot** resolve is not an error. Plenty of artifacts live in a
model store elsewhere and are named here precisely so an engine can check them.

**Three — in the warrant.** Law **L-W12**: if a run's parameters come from the
artifact — which is what `learned_weights` in an ONNX graph and a PMML
scorecard's coefficients both are — the warrant must carry the artifact's
digest, or issuance is refused:

```json
{"law": "L-W12", "path": "realisation.artifact.digest",
 "detail": "this run's parameters come from the artifact, and the warrant does
   not carry the artifact's digest -- so an engine cannot check that what it
   loaded is what was approved",
 "remediation": "register the version with an artifact_digest, or upload the
   file to MAYA and name it by its address; a location with no digest cannot be
   verified, only fetched"}
```

The law is deliberately **not written in terms of the trainability class**. It
bites hardest on a neural network, and a PMML scorecard is T2 and carries
exactly the same exposure — keying it on the class would have missed that, and
the miss would have looked like coverage.

**Four — at load, inside the engine.** The engine re-derives the hash from what
it fetched. That is the only checkpoint outside MAYA's process, and it is the
one that matters: a swapped artifact is *detected* rather than assumed away.

You can perform the store's own check at any time:

```bash
curl -u a.mehta:… localhost:5006/api/v1/artifacts/sha256:9f2c1a7e…/verify
curl -u a.mehta:… localhost:5006/api/v1/artifact-usage
```

Verification re-derives the hash from the bytes on disk. Content addressing
makes tampering hard rather than impossible — the filesystem is still a
filesystem — and this is how you find out. It is a separate call because
re-hashing a multi-gigabyte file is not something a read should do every time.

---

## 4 · Eight formats, and which of them run code

```bash
curl -u d.raman:… localhost:5006/api/v1/artifact-formats
```

| Format | For | Executes on load |
|---|---|---|
| `onnx` | a portable graph, loadable without its framework | no |
| `safetensors` | weights only, with no code path on load | no |
| `pmml` | verbose and old and readable by anything | no |
| `pfa` | a PFA document | no |
| `json` | a rule set, a scorecard, a configuration | no |
| `gguf` | quantised weights for local inference | no |
| `torchscript` | a TorchScript archive — carries code | **yes** |
| `tar` | several files: a tokenizer beside its weights, an adapter beside its base | **yes** |

The last two are accepted and load **in the sandbox and nowhere else**. The
distinction is recorded so nobody has to remember it, and the warrant carries
`executes_on_load` so an engine is not inferring it from a file extension.

The list is closed, and there is no `pickle`. An artifact's format decides how
it is loaded, and *we will work it out at load time* is how a pickle gets
deserialised in a control plane.

---

## 5 · How an engine reaches it

`realisation.runtime` says how an engine turns an artifact into something
callable — the second of the grammar's four axes. Each of the eighteen runtimes
declares the keys its `entry` block must carry, and a warrant whose entry is
missing one is refused at issuance rather than at the artifact loader.

| `runtime` | `entry` must carry |
|---|---|
| `onnx` | `graph` |
| `pmml` / `pfa` | `document` |
| `python.callable` | `module`, `attr` |
| `container` | `image` |
| `rest` | `endpoint` |
| `quantlib` | `instrument`, `pricing_engine` |
| `estimator` | `family` |
| `solver` | `formulation`, `solver` |
| `sql` | `statement`, `dialect` |
| `spreadsheet` | `workbook`, `sheet`, `input_cells`, `output_cells` |
| `rules` | `ruleset`, `engine` |
| `llm.prompt` | `provider`, `base_model`, `prompt_digest` |
| `llm.agent` | `provider`, `base_model`, `graph`, `max_steps` |
| `descriptor_only` | *nothing* |

`sas`, `r` and `matlab` are the remaining three, and `estimator` is the only one
whose job is to *inhabit* a parameter object rather than read one.

Declare `runtime` and `entry` in the kernel and they travel in every warrant:

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

---

## 6 · When there is no artifact to supply

Leave the runtime out and warrants are issued **descriptor-only**. MAYA carries
the governance, the schemas, the operating boundary and the authority; the
engine supplies the model. This is the honest state for a vendor black box, and
it is a legitimate state rather than a defect — `descriptor_only` is one of the
eighteen runtimes, not the absence of one.

What it cannot be warranted for is `fit`, by **L-W6**: you cannot instruct
something to inhabit a parameter object that nothing on this side can reach.

Guessing would be worse. A warrant asserting `python.callable` with an entry
nobody filled in fails at the artifact loader, which is the most expensive place
to discover that a registration was incomplete.

---

## 7 · The generative case, where the artifact is a bundle

For a T5 model the "artifact" is a prompt, its few-shot examples, its output
schema and its tool manifest. Digest the bundle and version it in git like any
other source:

```json
"parameters": {
  "kind": "llm_configuration",
  "source": {"binding": "artifact",
             "uri": "git://internal/kyc-prompts@a71f0c9",
             "components": ["system_prompt", "few_shot_examples",
                            "output_schema", "tool_manifest"]},
  "digest": "sha256:7c1b04ea…"
}
```

A prompt change is a **version change**, and a RAG corpus that moves without one
is a model whose behaviour changed without a version — which is why the corpus
is pinned by revision too.

There is a second moving part here that no digest of yours can cover. **L-W13**
refuses a generative warrant that names `base_model` and no build:

> `'gpt-class-4'` names a family of weights rather than a build, so this warrant
> cannot tell two different models apart.

Pinning `base_model_version` does not stop the host retiring it. It makes the
retirement *visible* as a mismatch instead of invisible as a drift. Where the
provider exposes nothing to pin, say so and expect the drift monitor to be your
only warning — see [an LLM application](/tutorials/llm-end-to-end).

---

## 8 · When `P` is not a file at all

Three coefficients are not an artifact and should not be made into one. They go
into the register as a **parameter set**, with the featureset version and window
that produced them, and somebody other than whoever recorded them approves them:

```bash
curl -u a.mehta:… -X POST \
  localhost:5006/api/v1/parameter-sets/$ID/review \
  -H 'Content-Type: application/json' \
  -d '{"accept": true, "note": "condition number 34.9; signs as expected"}'
```

The warrant then names the set by **id and digest**, and the engine re-derives
that digest from the values before running — it does not compare the stored
digest against the warrant's copy, because those are two copies of one claim and
would agree happily over values somebody had edited underneath them. A mismatch
is `parameter_mismatch`, and it is a security event rather than a bad request.

The line between a record and an artifact is not whether the method is called
machine learning. It is whether a reviewer can read the numbers.

---

## 9 · Documents are stored too, and differently

The artifact is the thing that runs. The **document** is the thing somebody
wrote about it, and MAYA holds those bytes rather than a link to them — because
a document is small, has no other custodian that treats it as evidence, and is
the thing a supervisor asks to see. Keeping only a link would put the evidence
on somebody else's share drive.

```bash
curl -u j.okafor:… -X POST localhost:5006/api/v1/attachments \
  -F urn="maya://model/credit.pd.smallbiz" \
  -F kind=model_development_document \
  -F title="SB PD — Model Development Document" \
  -F file=@mdd.md
```

Content-addressed under `data/attachments`, keyed by the SHA-256 of the bytes,
64 MB per document. The same file attached to forty models is one stored object;
a byte cannot change without becoming a different document; and a read re-hashes
before returning. What an approver accepted is what a reader later fetches —
checked, not assumed.

**File it against what it is about.** With no `semver` it lands on the current
version, because a development document describes the coefficients it printed
rather than their replacement. Pass `model_level=true` for something genuinely
about the model — a board paper — and you have to pass it deliberately. And for
the two cases that used to have nowhere to go:

```bash
# the convergence study for one fit
curl -u d.raman:… -X POST localhost:5006/api/v1/attachments \
  -F urn="maya://model/credit.pd.smallbiz" -F kind=other \
  -F title="ols_v1 — convergence and influence" \
  -F subject_type=parameter_set -F subject_id=01a06d51f9c3 \
  -F file=@convergence.md

# the data dictionary for one filled featureset
curl -u d.raman:… -X POST localhost:5006/api/v1/attachments \
  -F urn="maya://model/credit.pd.smallbiz" -F kind=other \
  -F title="sb_core v1 — data dictionary" \
  -F subject_type=featureset_version -F subject_id=… \
  -F file=@dictionary.md
```

`GET /api/v1/document-subjects` publishes the six and says which are **pinned**.
`featureset_version` is in the vocabulary and `featureset` deliberately is not:
a document filed against the set would describe something that has since moved.

Filing is not accepting. Somebody holding `document:review` — never the person
who filed it — has to accept it:

```bash
curl -u a.mehta:… -X POST \
  localhost:5006/api/v1/attachments/$ID/review \
  -H 'Content-Type: application/json' \
  -d '{"accept": true, "note": "back-testing section complete"}'
```

See [documents on file](/help/documentation#documents-on-file) for supersession,
rejection and what the platform can and cannot read out of a document.

---

## 10 · What is never stored

Personal data never goes into the evidence chain. **L-18**: a node flagged
`contains_personal_data` is stored with an **empty payload**, and the content
hash is taken over what was *stored* rather than what was passed — so the node
verifies against itself, and an erasure request needs no action at all, because
there was never anything to erase. An export pack carries the empty node and
says so, rather than quietly omitting it and reading as complete.

**This section used to say "an erasable pointer".** There is no pointer: no
`payload_uri` column in either dialect, no per-subject key, no shred path. The
payload is discarded. That is stronger than the law asks for — nothing to leak —
and weaker than the old sentence implied, because it also means the data cannot
be resolved later under any authority. Which of those you are getting is worth
knowing, and the sentence that named a mechanism nobody built made it
impossible to tell.

---

Next: [running several versions at once](/tutorials/managing-versions), where the
digest that survived all four checkpoints has to survive being replaced.
