# ADR-009 — Sandbox-only artifact loading and a format policy

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Status:** accepted · **Date:** 2026-09

## Context
Research shows roughly 45% of popular public models still ship as pickle, that pickle deserialisation is
arbitrary code execution, that malicious `.pth` files with embedded remote-access payloads have been
published to trusted hubs, and that model scanners have both false positives and false negatives. MAYA
ingests internal, open-source and vendor artifacts, and holds credentials to the bank's governance data.

## Decision
1. The **control plane never deserialises a model artifact.** All introspection and execution happens in an
   ephemeral, network-isolated, credential-free sandbox (gVisor/Kata, read-only rootfs, seccomp, hard limits).
2. A **format policy** per environment: ONNX, PMML, PFA and safetensors preferred; pickle/joblib **denied in
   production**, permitted below with scanning; exceptions are dual-authorised, expiring, and carry a
   migration plan.
3. All artifacts are content-addressed, scanned, signed, and digest-verified on every load.

## Consequences
- **+** The highest-severity threat (T1) is structurally mitigated rather than detected.
- **+** Preferring declarative formats also improves portability and reproducibility.
- **−** Some teams must convert models to ONNX to reach production. This is friction we accept, and it is
  friction with an independent benefit.
- **−** Sandbox infrastructure has real operational cost. Justified by the impact of the alternative.
