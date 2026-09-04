---
title: Storing model artifacts
slug: storing-artifacts
section: The register
order: 20
icon: archive
summary: What MAYA stores, what it deliberately does not, why a digest beats a copy, and how each artifact format is reached.
audience: Engineers, Model owners
---

# Storing model artifacts

## MAYA stores the digest, not usually the bytes

```json
{"artifact_digest": "sha256:9f2c1a7e4b3d0865ca19e2f7b04d3a61c8e5079fb2d4a136e0c85719ad3f2b4c"}
```

That is a deliberate choice, and it is worth understanding before you fight it.

**It works for artifacts MAYA must not hold.** A vendor binary under licence, a
container in a registry someone else runs, a 40GB checkpoint you are not going to
duplicate into a governance database.

**It is checkable at execution time.** The warrant carries the digest; the engine
verifies what it actually loaded against it. A swapped artifact is *detected*
rather than assumed away — which a copy in a governance store cannot do, because
nothing forces production to read from that copy.

**It is stable.** The same model registered twice from two pipelines produces the
same digest, which is how duplicate registration is caught rather than
accumulated.

## Where the bytes actually live

Wherever your organisation already puts them. The warrant carries the location:

```json
"artifact": {
  "uri": "s3://maya-artifacts/credit/pd_smallbiz_3.2.1.onnx",
  "digest": "sha256:9f2c1a...",
  "format": "onnx"
}
```

`data/artifacts/` exists for a local development store and is git-ignored. A real
deployment points `uri` at object storage, a package registry, a git ref or a
container registry.

## Formats, and how each is reached

The `realisation.runtime` says how an engine turns an artifact into something
callable, and each runtime declares the keys it needs. This is the second of the
grammar's four axes — see [the warrant grammar](/help/warrant-grammar).

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
[feature contracts](/help/feature-contracts) exist to prevent — which is why the
corpus is pinned by revision too.

## What is never stored

Personal data never goes inline into the evidence chain. Law L-18: an evidence
node carrying personal data holds an **erasable pointer**, not the data — so an
erasure request can be honoured without breaking the hash chain that everything
else depends on.
