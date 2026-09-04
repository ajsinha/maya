---
title: Execution engines
slug: execution-engines
section: Execution
order: 110
icon: cpu
summary: What an engine must check before it touches an artifact, what the captive engine is for, and why it holds no privileged access.
audience: Engineers
---

# Execution engines

An execution engine is anything that takes a warrant and runs a model. MAYA
ships one — the **captive engine** — but it is a reference consumer of the public
contract, not a privileged component.

## The order of checks

An engine must do these before it touches the artifact, in this order:

1. **Verify the signature.** An unsigned or tampered warrant is not a warrant.
2. **Check the local revocation list.** Before expiry, because of the revocation
   floor: a revoked warrant is refused regardless of grace state.
3. **Check expiry, including grace.** Past `expires_at + grace_seconds`, refuse.
4. **Check the operating boundary.** Inputs outside the contract's assumptions
   mean the guarantees are void. Refuse rather than produce a number nobody
   should rely on.
5. **Only then** load the artifact, verify its digest against the warrant, and
   run.

The ordering is the design. Every check that can be made without touching the
artifact is made first, so a refusal is cheap and an artifact is never loaded on
an authorisation that was never valid.

## The captive engine

```bash
POST /api/v1/execute
{
  "urn": "maya://model/credit.pd.smallbiz#champion",
  "environment": "prod",
  "principal": "svc/origination",
  "declared_use": "origination_decision",
  "inputs": {"dscr": 1.4}
}
```

It resolves a warrant through the same public endpoint an external engine uses,
then performs the five checks above.

Structurally, it holds **no reference to the registry, the store or the evidence
engine**. It has the warrant and nothing else. There is a test asserting exactly
that, because the boundary is only real if it is enforced by construction rather
than by intention — the moment the bundled engine can reach past the contract,
the contract stops describing what actually happens.

Switch it off with one key:

```yaml
execution:
  captive:
    enabled: false
```

Nothing else changes. External engines are unaffected, because they were never
using it.

## What the captive engine is not

It runs registered Python callables. It does not load ONNX, PMML, a container,
a spreadsheet or a pricing library, and there is no sandbox.

It is a reference implementation of the **protocol**, not of artifact execution.
Running a real estate means a real engine — one with the runtimes, the isolation
and the capacity your models actually need. The point of the captive engine is
that a fresh deployment demonstrates the whole governed path end to end without
anyone building that first.

## Writing your own engine

The contract is the warrant document and the five checks. An engine needs:

- **A signature verifier** sharing the signing key with MAYA.
- **A revocation cache**, refreshed often enough that the floor means something.
  Warrants carry the epoch they were minted under, so a cached epoch behind the
  current one tells the engine its view is stale.
- **A boundary checker** reading `constraints` from the warrant.
- **A digest check** comparing the loaded artifact against `realisation`.
- **Runtimes** for the model families you actually run.

What it does **not** need is any access to MAYA's database, and it should not
have any. If your engine needs to query the registry to do its job, something
that should have been in the warrant is missing — and that is a bug in the
warrant, not a reason to widen the engine's reach.
