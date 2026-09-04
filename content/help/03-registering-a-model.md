---
title: Registering a model
slug: registering-a-model
section: The register
order: 30
icon: box-seam
summary: What counts as a model, what the register asks for, and why each field is there rather than being one more box to tick.
audience: Model owners
---

# Registering a model

## What counts as a model

Supervisory guidance is broad on purpose. SR 26-2 and its predecessors define a
model as a quantitative method that applies statistical, economic, financial or
mathematical theories to process input data into quantitative estimates.

Read literally — and it is meant literally — that includes a great deal that no
inventory captures:

| It looks like | It is still a model |
|---|---|
| A pricing library call (Black–Scholes, SABR, Hull–White) | Yes — theory-derived parameters, quantitative estimate |
| A spreadsheet an analyst maintains | Yes — this is the classic end-user-computed model |
| A vendor black box you cannot open | Yes — opacity is a control problem, not an exemption |
| A prompt bundle with a foundation model behind it | Yes — configured, not trained, but a model |
| A rules engine encoding credit policy | Yes — authored parameters |
| A regulatory capital calculator (SA-CCR, RWA) | Yes — and usually Tier 1 |

MAYA registers all of them in one population. They differ in what evidence is
appropriate, not in whether they are governed. See
[Trainability classes](/help/trainability-classes).

## The URN

```
maya://model/credit.pd.smallbiz
```

This is the permanent handle. It is chosen once and never changes, because
consumers bind to it and everything downstream — warrants, evidence, findings —
hangs off it.

Conventions that hold up over time:

- **Domain first**, then subject, then variant: `credit.pd.smallbiz`,
  `market.var.equities`, `ops.kyc.summariser`.
- **No version in the URN.** Versions are separate objects; a URN that says
  `_v2` is a URN you will have to abandon.
- **No environment in the URN.** The same model runs in dev and prod; the
  environment is a coordinate on the alias, not on the identity.

A version or alias can be *appended* when resolving:

```
maya://model/credit.pd.smallbiz          the environment's champion
maya://model/credit.pd.smallbiz@3.2.1    a pinned version
maya://model/credit.pd.smallbiz#challenger   a named alias
```

## The fields, and why

```json
{
  "urn": "maya://model/credit.pd.smallbiz",
  "name": "Small Business PD",
  "model_class": "credit.pd.scorecard",
  "domain": "credit",
  "owner": "person/j.okafor",
  "legal_entity": "LE-US-01",
  "purpose": "12-month PD at origination",
  "description": "Logistic scorecard over financial and behavioural features.",
  "origin": "internal"
}
```

**owner** — a person, not a team. A model owned by "Credit Analytics" is a model
nobody will be asked about. Findings need an owner who can be paged.

**legal_entity** — because model risk aggregates by entity, not by org chart.
The same model used by two entities is two exposures to two supervisors.

**purpose** — the *declared* use. This is load-bearing: a warrant carries a
`declared_use`, and resolution refuses if the use presented is not the use
approved. A model approved for origination decisioning that starts being used
for pricing has changed its risk profile without changing a line of code, and
this is the field that catches it.

**domain** and **model_class** — how the estate is sliced for reporting and how
class-appropriate evidence expectations are chosen.

**origin** — `internal`, `vendor`, `open_source`, or `hybrid`. Determines what
evidence is obtainable at all. You cannot ask a vendor black box for its
coefficients; you can ask for its validation report and its version notes.

## What registration does not do

Registration creates a **proposed** model with no tier and no versions. It is
deliberately cheap, because the alternative — a heavyweight intake form — is
what drives people to route around the platform, and an estate governed by a
platform people avoid is worse than one governed by a spreadsheet they use.

Everything consequential attaches to the *version*:
[Versions and artifacts](/help/versions-and-artifacts).
