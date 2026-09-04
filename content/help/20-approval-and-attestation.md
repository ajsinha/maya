---
title: Approval and attestation
slug: approval-and-attestation
section: The register
order: 45
icon: patch-check
summary: The record's lifecycle — draft to attested, why an attested model is immutable, and how an amendment is the only way to change one.
audience: Model owners, Model risk
---

# Approval and attestation

A model record moves through six states, and the whole design turns on one
distinction: an **attested** record is immutable, and a **mutable** record is one
somebody explicitly opened for change and will have to attest again.

```
draft ──submit──▶ submitted ──approve──▶ approved ──attest──▶ attested
  ▲                   │                                          │
  └──────return───────┘                                          │
                                                                 │
amending ◀──────────────── open an amendment ────────────────────┘
  │                                                              │
  └──submit──▶ submitted ──▶ approved ──▶ attested        retired ◀── retire
```

| State | Means |
|---|---|
| `draft` | being written; open to change and **not in force** |
| `submitted` | put forward for approval; **frozen** while it is considered |
| `approved` | approved but not yet attested; **not in force until it is** |
| `attested` | in force and **immutable** |
| `amending` | an amendment is open; the record is changeable again |
| `retired` | withdrawn from use; kept for the record, never deleted |

## Why immutability is a state, not a flag

The question a supervisor asks is not "is this record locked". It is *what is in
force, who said so, and when did they say it*. A state machine answers all
three. A flag answers none of them.

And it is what makes the record mean anything: "this is the model" and "this is
what we said about the model" are the same document only while nobody can edit
one of them quietly.

## Approval and attestation are different acts

**Approval** is one authorised person in the second line saying the work is sound.

**Attestation** is the set of people who will be asked about this model in a
supervisory meeting each putting their name to it — the owner that the controls
are operating, the second line that challenge was effective.

A button one person presses is not that. So attestation is a **quorum**:

```yaml
lifecycle:
  attestation:
    required_roles: [model_owner, model_risk_manager]
    validity_days: 365
```

Every named role signs; the model becomes attested only when all of them have.
**One decline ends it** and sends the record back to be worked on.

Two rules make the quorum real rather than decorative:

- **A principal may only sign for a role they actually hold.** An attestation
  where one person signed twice under two hats is not a quorum.
- **Each required role signs once.**

```bash
POST /api/v1/models/{name}/attest
{"role": "model_owner", "statement": "Controls are operating and the model is
                                      used only for its approved purpose."}
```

## What "immutable" actually blocks

An attested record refuses:

- **field changes** — `PATCH /api/v1/models/{name}` is refused
- **new versions** — because *a new version is a change to the model*

That second one is the one people are surprised by, and it is the important one.
Letting a version be added to an attested record is exactly how the record
quietly stops describing what runs.

```json
{
  "error": "registry_refused",
  "detail": "cannot add a version to maya://model/credit.pd.smallbiz: this model
             is attested and therefore immutable; open an amendment to change it"
}
```

Some fields are never editable in any state: the URN is permanent, the status
moves only through the lifecycle, and the tier comes from an assessment.

## Amendments

An amendment is a **declared act**. It says what is changing and why, returns the
record to `amending`, and creates an obligation: the amendment must itself be
submitted, approved and attested before the model is back in force.

```bash
POST /api/v1/models/{name}/amend
{"reason": "Recalibrate for the 2026 cycle", "scope": ["kernel", "thresholds"]}
```

Amendments get a reference (`AMD-001`) because they get quoted in committee
minutes. One is open at a time per model — two concurrent amendments to the same
record produce a document nobody can reconstruct. Nothing is edited in place and
nothing is lost; a withdrawn amendment stays in the history as a withdrawn
amendment.

## Who can do what

| Act | Permission | Held by |
|---|---|---|
| `submit` | `model:submit` | model owner |
| `approve` / `return` | `model:approve` | model risk manager |
| `attest` | `model:attest` | model owner **and** model risk manager |
| `amend` | `model:amend` | model owner |
| `retire` | `model:retire` | model owner, model risk manager |
| `delete` | `model:delete` | **administrator only** |

Segregation applies on top: the person who created a version may not approve it
or promote it, whatever roles they hold. See
[Roles and segregation of duties](/help/authorisation).

## Nothing is ever deleted

**Retirement** is a state. It withdraws a model from use and keeps everything —
the record, the versions, the evidence, the findings. This is what almost every
situation calls for, and it is available to model owners and risk managers.

**Deletion** is the one act with no workflow, no reversal and no second
signature, and it is administrators only. It is checked against the role rather
than only the permission: a permission can be granted to a role by mistake, and
requiring `admin` explicitly means the mistake has to be made twice.

Even then, the evidence survives. A `model_deleted` entry is appended to the
chain **before** the rows go, so the chain records the intent even if the removal
fails halfway — and afterwards the model's whole history is still there, ending
with who deleted it and why.

```json
{"deleted": true, "urn": "maya://model/...", "reason": "registered in error",
 "evidence_retained": true}
```

## Renewal

An attestation carries an expiry, defaulting to a year. Once it lapses, the
model page says so. Renewal is a periodic attestation against the unchanged
record — the same quorum, signing again that the model is still fit for its
purpose.
