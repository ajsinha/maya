---
title: Versions and artifacts
slug: versions-and-artifacts
section: The register
order: 40
icon: layers
summary: Why versions are immutable, what a manifest digest buys you, how the operating contract is declared, and how artifacts are referenced.
audience: Engineers, Model owners
---

# Versions and artifacts

## Immutability is the whole point

A version is created once and never edited. Attempting to create `3.2.1` twice
is refused:

```
version 3.2.1 already exists for maya://model/credit.pd.smallbiz;
versions are immutable
```

This is not fastidiousness. Three things depend on it:

1. **The manifest digest means something.** If a version could be edited, a
   digest recorded last March would prove nothing about what runs today.
2. **A warrant can name a version.** An execution engine that resolved
   `3.2.1` in January and again in June got the same model, and can prove it.
3. **Evidence stays attached.** A validation result is about a specific
   artifact. Let the artifact change underneath and the result becomes a
   statement about nothing.

Need a change? Create `3.2.2`. Versions are cheap; ambiguity is not.

## The kernel specification

Every model in MAYA is one shape:

> a parameter object **P**, an input **X**, an output **Y**, and a kernel
> **f : P ⊗ X → Y**

The version declares how that shape is filled in.

```json
{
  "semver": "3.2.1",
  "kernel": {
    "parameter_kind": "estimated_coefficients",
    "fit_procedure": "estimate",
    "output_kind": "point_estimate",
    "deterministic": true,
    "adaptive": false,
    "input_schema":  [{"name": "dscr", "dtype": "float", "minimum": -5, "maximum": 20}],
    "output_schema": [{"name": "pd_12m", "dtype": "float"}]
  },
  "contract": { ... },
  "artifact_digest": "sha256:9f2c1a..."
}
```

`parameter_kind` — how P is inhabited. One of `none`, `calibration_set`,
`estimated_coefficients`, `learned_weights`, `llm_configuration`, `rule_set`,
`elicited_weights`, `opaque`.

`fit_procedure` — how it got that way: `none`, `calibrate`, `estimate`,
`train`, `elicit`, `configure`, `author`.

Together these **derive** the trainability class. You do not declare T3; the
system works out that a model with learned weights obtained by training is T3.
A class you can declare is a class someone will declare conveniently.

## Schemas are contracts, not documentation

The input and output schemas are checked when an alias moves. Input schemas are
**contravariant** and output schemas **covariant** — the replacement must accept
at least everything the incumbent accepted and promise at least everything it
promised. A version that narrows an input range is not a drop-in replacement,
however much better it scores, and the alias move is refused with the field that
broke it.

## The operating contract

```json
"contract": {
  "assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
  "guarantees":  [{"key": "gini", "minimum": 0.42}],
  "on_boundary_violation": "reject"
}
```

Read as: *given* inputs within the assumptions, the model *guarantees* the stated
properties. Outside the assumptions, the guarantee is void — which is a much more
honest statement than a model that silently extrapolates.

The contract travels in the warrant, so an execution engine can check the
boundary **before** invoking the artifact, and refuse rather than produce a
number nobody should rely on.

Contracts also compose. When an alias moves, the replacement's contract must
**refine** the incumbent's: assume no more, guarantee no less.

## Artifacts

MAYA stores the **digest** and the reference; it is not a binary store by
default. `artifact_digest` is the content hash of whatever actually runs —
the ONNX graph, the pickle, the prompt bundle, the JAR, the workbook.

Why a digest rather than the bytes:

- It works for artifacts MAYA must not hold — a vendor binary under licence, a
  container in a registry, a model too large to duplicate.
- It is checkable at execution time. The engine verifies what it loaded against
  what the warrant said, so a swapped artifact is detected rather than assumed
  away.
- It is stable. The same model registered twice from two pipelines produces the
  same digest, which is how duplicate registration gets caught.

For `origin: vendor` models with no obtainable artifact, `artifact_digest` may be
null and the version is marked descriptor-only. That is an honest state, and the
platform records it as a limitation rather than pretending to an assurance it
does not have.

## Approval

```bash
POST /api/v1/models/{name}/versions/{semver}/approve
```

A version is `draft` until approved. An alias may only point at an approved
version — see [Warrants](/help/warrants) for what happens when it does not.
