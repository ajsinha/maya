---
title: Approval, attestation and segregation of duties
slug: approval-and-attestation
section: The register
order: 50
icon: patch-check
summary: The record's lifecycle from draft to attested, why an attested record is immutable, the quorum that puts it in force, and the roles, scopes and segregation rules that decide who may move it.
audience: Model owners, Model risk, Administrators
---

# Approval, attestation and segregation of duties

Two questions decide whether a governance act happens. *Is the record in a state
that allows it?* — the lifecycle. And *is this the right person to do it?* —
authorisation. The first is about the model; the second is about you; and the
most important rules in the platform live at the point where they meet.

## The states

A model record moves through seven states, and the whole design turns on one
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

| State | Means | Mutable |
|---|---|---|
| `draft` | being written; open to change and **not in force** | yes |
| `baselined` | imported from an existing estate; governed going forward, not asserting historical evidence | yes |
| `submitted` | put forward for approval; **frozen** while it is considered | no |
| `approved` | approved but not yet attested; **not in force until it is** | no |
| `attested` | in force and **immutable** | no |
| `amending` | an amendment is open; the record is changeable again | yes |
| `retired` | withdrawn from use; kept for the record, never deleted | no |

`baselined` sits in the mutable set deliberately. A baselined model arrived
without a version, a tier or a validation; freezing it would mean the only route
to closing that debt is an amendment to a record that was never attested —
nonsense, and exactly how a cold-start capability quietly becomes unusable. It
leaves through the same path as anything else. See
[The estate and what needs doing](/help/estate-and-worklist).

## Why immutability is a state, not a flag

The question a supervisor asks is not "is this record locked". It is *what is in
force, who said so, and when did they say it*. A state machine answers all
three. A flag answers none of them.

And it is what makes the record mean anything: "this is the model" and "this is
what we said about the model" are the same document only while nobody can edit
one of them quietly.

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
**One decline ends it** and sends the record back to be worked on — to `amending`
if the attestation was for an amendment, otherwise to `draft`.

Two rules make the quorum real rather than decorative:

- **A principal may only sign for a role they actually hold.** The refusal says
  *sign for a role you hold; an attestation signed under a borrowed hat is not a
  quorum.* An attestation where one person signed twice under two hats is not a
  quorum.
- **Each required role signs once.**

```bash
POST /api/v1/models/{name}/attest
{"role": "model_owner", "statement": "Controls are operating and the model is
                                      used only for its approved purpose."}
```

## Amendments

An amendment is a **declared act**. It says what is changing and why, returns the
record to `amending`, and creates an obligation: the amendment must itself be
submitted, approved and attested before the model is back in force.

```bash
POST /api/v1/models/{name}/amend
{"reason": "Recalibrate for the 2026 cycle", "scope": ["kernel", "thresholds"]}
```

Amendments get a reference (`AMD-001`) because they get quoted in committee
minutes. A reason is required. One is open at a time per model — two concurrent
amendments to the same record produce a document nobody can reconstruct. Nothing
is edited in place and nothing is lost; a withdrawn amendment stays in the
history as a withdrawn amendment.

## Renewal

An attestation carries an expiry, defaulting to a year. Once it lapses, the
model page says so, and the scheduler raises a finding rather than waiting for
somebody to notice. Renewal is a periodic attestation against the unchanged
record — the same quorum, signing again that the model is still fit for its
purpose.

## Nothing is ever deleted

**Retirement** is a state. It withdraws a model from use and keeps everything —
the record, the versions, the evidence, the findings. This is what almost every
situation calls for, and it is available to model owners and risk managers.

**Deletion** is the one act with no workflow, no reversal and no second
signature, and it is administrators only. It is checked against the **role**
rather than only the permission — *only an administrator may delete a model;
everyone else retires it* — because a permission can be granted to a role by
mistake, and requiring `admin` explicitly means the mistake has to be made twice.

Even then, the evidence survives. A `model_deleted` entry is appended to the
chain **before** the rows go, so the chain records the intent even if the removal
fails halfway — and afterwards the model's whole history is still there, ending
with who deleted it and why.

```json
{"deleted": true, "urn": "maya://model/...", "reason": "registered in error",
 "evidence_retained": true}
```

## Authorisation asks three questions

In this order:

1. **May this principal do this at all?** — permission, from their roles.
2. **May they do it to this model?** — scope, by legal entity and domain.
3. **May they do it given what they already did?** — segregation of duties, read
   from the evidence chain.

Cheapest first, and each refusal is more specific than the last. A principal who
fails on permission never learns whether the model exists, which is the right
disclosure boundary: an inventory of model names is itself sensitive.

## The roles

Deliberately few. A permission system with forty roles is one nobody can reason
about, and the question that matters at an audit — *who could have approved
this?* — becomes unanswerable.

| Role | Line | May | May not |
|---|---|---|---|
| `model_developer` | 1st | Create versions, define and materialise features, assemble training sets, attach documents | Approve, tier, promote, validate |
| `model_owner` | 1st | Everything a developer can, plus register models, request a tier, issue warrants, raise findings, define and evaluate monitors, propose and measure overlays, compile documents | Approve, promote, conclude a validation, approve an overlay |
| `validator` | 2nd | Read everything; open, record and conclude validations; raise and close findings; review documents; approve parameter sets; generate and attest machine assistance | Build anything |
| `model_risk_manager` | 2nd | Everything a validator can, plus approve versions, move aliases, approve models, set tiers, certify features, revoke warrants, approve overlays, register assist capabilities, activate regimes | Create versions |
| `auditor` | 3rd | Read everything, raise findings | Close a finding, approve, build |
| `operator` | — | The batch-runner set: read models, warrants and evidence, and evaluate monitors | Any other governance act |
| `service` | — | Resolve and execute warrants, evaluate monitors | Sign in to the interface |
| `admin` | — | Everything, including principal management | — |

Roles **compose**: a principal holds a set and gets the union. That is how a
small firm gives one person two hats visibly, rather than inventing a hybrid
role that hides the fact.

Some pairs are refused, because holding both defeats the control they exist to
enforce:

```
model_developer + model_risk_manager   a first line approving its own work
model_owner     + model_risk_manager   an owner approving and tiering their own models
model_developer + auditor              the third line must not build what it audits
model_owner     + auditor              the third line must not own what it audits
```

Granting one anyway requires `allow_conflicts: true` — so the exception is
explicit, deliberate, and recorded on the evidence chain rather than accidental.
A principal holding `admin` is not checked against these pairs at all.

## Scope

A permission says what someone may do. A scope says what they may do it **to**.
Conflating them is how a validator in the UK entity ends up able to approve a US
model because they hold the right role globally.

```json
{"username": "uk.validator", "roles": ["validator"],
 "legal_entities": ["LE-UK-02"], "domains": ["credit", "market"]}
```

An empty list means unrestricted on that dimension. That default is deliberate:
enumerating every entity for every principal is the design that makes people
grant a wildcard to get on with their day, and a wildcard granted in haste is
indistinguishable from no control at all.

Scope filters **listings**, not just detail pages. A model outside your scope is
not merely unopenable — it is not visible, and its existence is not disclosed by
a count that does not add up.

## Segregation of duties

This is the part that role separation alone cannot do.

The usual way to build it is a separate table of who-did-what, consulted when
someone attempts a conflicting act. That table is a second source of truth about
history, and the moment it disagrees with the record, the control is worthless.

MAYA already has an append-only, hash-chained record of every governance act
with its actor and its subject. So segregation is checked **against the evidence
chain itself**. The artifact that proves what happened decides who may act next.
There is nothing to keep in step, and tampering to clear a conflict breaks the
chain.

| Act | Refused if the same person previously | Because |
|---|---|---|
| `version:approve` | created that version | a first line must not approve its own work |
| `alias:move` | created that version | the builder must not promote their own build |
| `validation:conclude` | created that version | effective challenge requires independence |
| `finding:close` | raised **that** finding | closure must be attested by someone other than the raiser |

The refusal cites the record:

```json
{
  "error": "segregation_of_duties",
  "detail": "the person who created a version may not approve it — solo recorded
             'version_created' against this subject at evidence #12",
  "remediation": "route the approval to someone in the second line who did not build it"
}
```

### When the subject is not where the evidence lives

The last row needs a word, because it is where this design nearly failed
silently. A finding is raised against the **model** — that is where a reader
looks for it, and what a compiled document cites — while the act being checked is
about one finding. Searching the chain under the finding's own id therefore found
nothing and permitted everything: the rule was in the table, in the tests, and
inert in production for three milestones.

So a rule may name the payload field carrying the identity it is about. The check
searches the model's evidence and narrows to nodes whose `finding_id` matches the
one being closed. Raising one finding on a model does not disqualify you from
closing another — that would be a different and much broader rule, and not the
one anybody wrote down.

A rule that needs that discriminator and is given none matches **nothing** rather
than matching everything of its kind on the subject. Refusing acts nobody meant
to forbid is worse than the gap, and it is loud in a test rather than silent in
production.

Closure is segregated a second time, by a rule that lives in the findings
register rather than in this policy: the owner of a finding may not verify its
own closure, and closure evidence is required. Two different questions — *did you
raise it* and *do you own it* — and a person can fail either. See
[Validation and findings](/help/validation).

**This applies to administrators too.** Break-glass exempts you from the
incompatible-roles check, not from segregation. An account that could build and
then approve is exactly the hole an auditor looks for, and a single-account
deployment genuinely cannot complete a segregated path — which is the correct
answer, not a limitation to work around.

## A version is approved by a quorum too

The record is attested by several people. A version — the thing that actually
runs — used to be approved by one. That asymmetry was backwards: the record says
what the model is *for*; the version says what will *happen*.

The depth of control follows the tier, which is the same adjunction (**L-5**)
that decides every other control set here:

| Tier | Who must sign |
|---|---|
| 1 | model risk manager **and** validator |
| 2 | model risk manager **and** validator |
| 3 | one authorised person |
| 4 | one authorised person |

Pretending a scheduling heuristic and a capital model deserve the same ceremony
is how a control becomes something people route around, so tiers 3 and 4 keep a
single signature and the register says plainly that they do.

**A version whose model has no tier cannot be approved at all.**

> **409 `no_tier`** — this model has no risk tier, so how many signatures its
> version needs is undecided. *Assess the model first; approving before assessing
> would be a way of choosing your own control depth.*

That refusal is not about paperwork. The tier decides the number of signatures,
so approving first would let anybody pick their own. It is the obvious way to
game a rule like this one, and it is closed.

Signing is its own permission. A validator holds `version:sign` and never
`version:approve`: they can complete a quorum and can never approve alone. And
the same person may not sign twice under two hats — a quorum is a number of
people, not a number of roles.

One decline closes the approval and returns the version to its author, with the
statement attached. A declined round stays in the history; the next attempt is a
new approval, so *"how many times did this fail second-line review"* is a
question with an answer.

## Who can do what to the record

| Act | Permission | Held by |
|---|---|---|
| `submit` | `model:submit` | model owner |
| `approve` / `return` | `model:approve` | model risk manager |
| `attest` | `model:attest` | model owner **and** model risk manager |
| `amend` | `model:amend` | model owner |
| `retire` | `model:retire` | model owner, model risk manager |
| `delete` | `model:delete` **and** the `admin` role | administrator only |

## Authenticating

The interface uses a signed session cookie. Services and scripts use HTTP Basic
against the same principal register, so there is one identity store rather than
two:

```bash
curl -u a.mehta:… localhost:5006/api/v1/me
```

Passwords are PBKDF2-HMAC-SHA256 with a per-principal salt and 200,000
iterations. A deliberately expensive derivation is right for a login form and
wrong for an API called a thousand times a minute, so a successful verification
is trusted for sixty seconds — keyed by a peppered digest of the presented
secret, never the secret itself. **Suspension is re-read on every request**: the
cache shortens the key derivation, never the authorisation decision.

Every failure returns the same response whether the username is unknown or the
password is wrong, and the unknown-user path still computes a dummy hash so the
timing does not give it away either. The user list of a model risk platform is
an organisational chart, and a login form that confirms who exists hands it over
one guess at a time.

## Seeing your own permissions

```bash
GET /api/v1/me      # your roles, permissions and scope
GET /api/v1/roles   # the catalogue, the incompatible pairs, the SoD rules
```

Open to any authenticated principal. A person should always be able to see what
they are allowed to do without asking an administrator — a permission system
nobody can inspect is one people work around.
