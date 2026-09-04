---
title: Baseline import and compliance debt
slug: baseline-import
section: Getting started
order: 25
icon: box-arrow-in-down
summary: Getting an existing estate of 1,200 models into the register without pretending it arrived compliant — and without turning every dashboard red on day one.
audience: Model risk, Programme
---

# Baseline import and compliance debt

## The problem this exists for

Adversarial review of this design found one omission judged more dangerous than
any error in it:

> On import day, 1,200 existing models arrive with no evidence graph, no feature
> contracts, no reproducible runs, and documentation in Word files. Every gate
> fails. Every dashboard is red. Every KRI breaches. The model risk office
> concludes the platform is broken; developers conclude it blocks them; the
> programme dies in month seven.

A platform can be technically correct and organisationally unusable, and this is
how.

## The answer is not to lower the gates

It is to make the register **honest about what it does not know**.

A baselined model is in the inventory, tiered, and governed *going forward* — and
it carries explicit, dated **debt** for every piece of evidence it does not have.

> **Existing use is not blocked. Change is.**

That sentence is the whole policy. A baselined model keeps running, because
stopping 1,200 models was never going to happen and pretending otherwise makes
the platform something people route around. Its *next material change* goes
through the full path: submit, approve, attest.

## Debt is not breach

This distinction is preserved on every view, and it is the reason the register
stays believable.

A Tier 1 model that arrived last week with no validation history, and a Tier 1
model that missed its scheduled validation, are completely different situations.
A dashboard that renders them the same colour is one the model risk office stops
believing within a month.

| | Debt | Breach |
|---|---|---|
| What it means | we know this is missing and when it will be fixed | a control that should have operated did not |
| Raises a finding | no | yes |
| Blocks | nothing | warrant resolution, alias promotion |
| Becomes the other | **yes** — at its expiry | — |

Board-approved expiry by tier, because it is a board decision:

```yaml
Tier 1: 18 months     Tier 3: 36 months
Tier 2: 30 months     Tier 4: 36 months
```

Past that date, debt stops being debt. It raises a finding, and a finding can
block.

## Gaps are computed, not declared

The obvious design lets whoever imports a model declare its gaps. That design
produces a register in which every imported model has exactly two gaps, because
declaring a third is work and nobody is checking.

So MAYA works out what is missing from the register itself:

| Gap | Materiality |
|---|---|
| no accountable owner | Critical |
| no version — nothing pinned, nothing digested | Critical |
| no risk tier — the depth of control is undecided | Critical |
| no declared purpose — no approved use to check against | High |
| no artifact digest — what runs cannot be checked against what was approved | High |
| no operating contract — no stated assumptions | High |
| no validation episode | High |
| no monitors — degradation would not be detected | High |
| never attested | High |
| no feature contract — serving is not pinned | Medium |
| no compiled documentation | Medium |

An importer cannot under-declare, and does not have to know the list.

## Importing

```bash
POST /api/v1/baseline/imports
{
  "source": "legacy-inventory-2026-01.csv",
  "models": [
    {"urn": "maya://model/legacy.pd.corporate", "name": "Corporate PD",
     "owner": "person/j.okafor", "legal_entity": "LE-US-01",
     "purpose": "PD for corporate lending", "domain": "credit", "tier": 1}
  ]
}
```

One bad row does not stop the batch. 1,199 models must not fail because of one,
so a failure is recorded against that model and the import continues:

```json
{"models": 1199, "debt_items": 8412,
 "skipped": [{"urn": "…", "reason": "already in the register"}],
 "detail": "1199 model(s) baselined carrying 8412 debt item(s). These are
            governed going forward: existing use is not blocked, the next
            material change is."}
```

## Debt closes by itself

A debt item is a claim that something is missing, and the register can tell
whether it still is:

```bash
POST /api/v1/baseline/reconcile?urn=maya://model/legacy.pd.corporate
# → {"closed": [...], "breached": [], "remaining": 5,
#    "detail": "3 item(s) closed because the evidence arrived; 0 passed their
#               expiry"}
```

Nobody marks an item done. It closes because the evidence is there — which means
the burn-down chart is a **measurement** rather than a self-report. Reconcile is
idempotent and safe on a schedule: it only makes the stored position agree with
what the register can already see.

## The number a programme is judged on

```bash
GET /api/v1/baseline
# → {"models_baselined": 1199, "debt_raised": 8412, "debt_closed": 3106,
#    "debt_breached": 12, "burn_down": 0.369,
#    "detail": "3106 of 8412 baseline debt items closed (37%); 12 expired into
#               breaches"}
```

Not *how many models are compliant* — on day one, none of them are, and saying so
loudly is what kills the programme. **Is the debt going down.**

## `baselined` is a mutable state

A baselined model arrived without a version, a tier or a validation. Freezing it
would mean the only route to closing that debt is an amendment to a record that
was never attested — nonsense, and exactly how a cold-start capability quietly
becomes unusable.

So `baselined` sits beside `draft` and `amending` in the mutable set, and leaves
through the same path as anything else: **submit → approve → attest**. See
[approval and attestation](/help/approval-and-attestation).
