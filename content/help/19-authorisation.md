---
title: Roles and segregation of duties
slug: authorisation
section: Assurance
order: 145
icon: person-badge
summary: Three lines of defence made executable — what each role may do, which models it reaches, and the rule that the person who built a version may never approve it.
audience: Model risk, Administrators
---

# Roles and segregation of duties

Authorisation asks three questions, in this order:

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
| `model_developer` | 1st | Create versions, define and materialise features, assemble training sets | Approve, tier, promote, validate |
| `model_owner` | 1st | Everything a developer can, plus register models, request a tier, issue warrants, raise findings | Approve, promote, conclude a validation |
| `validator` | 2nd | Open, record and conclude validations; raise and close findings | Build anything |
| `model_risk_manager` | 2nd | Everything a validator can, plus approve versions, move aliases, set tiers, certify features, revoke warrants | Create versions |
| `auditor` | 3rd | Read everything, raise findings | Close a finding, approve, build |
| `operator` | — | Read models, warrants and evidence | Any governance act |
| `service` | — | Resolve and execute warrants | Sign in to the interface |
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
| `finding:close` | raised that finding | closure must be attested by someone else |

The refusal cites the record:

```json
{
  "error": "segregation_of_duties",
  "detail": "the person who created a version may not approve it — solo recorded
             'version_created' against this subject at evidence #12",
  "remediation": "route the approval to someone in the second line who did not build it"
}
```

**This applies to administrators too.** Break-glass exempts you from the
incompatible-roles check, not from segregation. An account that could build and
then approve is exactly the hole an auditor looks for, and a single-account
deployment genuinely cannot complete a segregated path — which is the correct
answer, not a limitation to work around.

## Authenticating

The interface uses a signed session cookie. Services and scripts use HTTP Basic
against the same principal register, so there is one identity store rather than
two:

```bash
curl -u a.mehta:… localhost:5006/api/v1/me
```

Passwords are PBKDF2-HMAC-SHA256 with a per-principal salt. A deliberately
expensive derivation is right for a login form and wrong for an API called a
thousand times a minute, so a successful verification is trusted for a short
window — keyed by a peppered digest of the presented secret, never the secret
itself. **Suspension is re-read on every request**: the cache shortens the key
derivation, never the authorisation decision.

Every failure says the same thing whether the username is unknown or the
password is wrong. The user list of a model risk platform is an organisational
chart, and a login form that confirms who exists hands it over one guess at a
time.

## Seeing your own permissions

```bash
GET /api/v1/me      # your roles, permissions and scope
GET /api/v1/roles   # the catalogue, the incompatible pairs, the SoD rules
```

Open to any authenticated principal. A person should always be able to see what
they are allowed to do without asking an administrator — a permission system
nobody can inspect is one people work around.
