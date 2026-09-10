---
title: Approval, attestation and segregation of duties
slug: approval-and-attestation
section: The register
order: 50
icon: patch-check
summary: Three gates in front of every governance act — the record's state, the actor's authority, and what that actor already did — plus how to sign in, and how to tighten a gate without waiting for a release.
audience: Model owners, Model risk, Administrators
---

# Approval, attestation and segregation of duties

Every governance act passes three gates, checked in this order because each is
more expensive than the last:

1. **Is the record in a state that allows it?** — the lifecycle.
2. **May this principal do this, to this model?** — permission, then scope.
3. **May they do it given what they already did?** — segregation of duties, read
   from the evidence chain.

A principal who fails the first gate never learns whether the model exists. An
inventory of model names is itself sensitive, so that is the right disclosure
boundary rather than an accident of ordering.

## The lifecycle

A model record moves through seven states, and the whole design turns on one
distinction: an **attested** record is immutable, and a **mutable** record is one
somebody explicitly opened for change and will have to attest again.

```
draft ──submit──▶ submitted ──approve──▶ approved ──attest──▶ attested
  ▲                   │                                          │
  └──────return───────┘                                          │
                                                                 │
amending ◀──────────────── amend ─────────────────────────────────┘
  │                                                              │
  └──submit──▶ submitted ──▶ approved ──▶ attested        retired ◀── retire
```

| State | Means | Mutable |
|---|---|---|
| `draft` | being written; open to change and **not in force** | yes |
| `baselined` | imported from an existing estate; governed going forward, not asserting historical evidence | yes |
| `submitted` | put forward for approval; **frozen** while it is considered | no |
| `approved` | approved and not yet attested; **not in force until it is** | no |
| `attested` | in force and **immutable** | no |
| `amending` | an amendment is open; the record is changeable again | yes |
| `retired` | withdrawn from use; kept for the record, never deleted | no |

`draft` and `baselined` are both **initial** states — an import does not have to
pretend it was drafted here. `baselined` is deliberately mutable: a baselined
model arrived without a version, a tier or a validation, and freezing it would
mean the only route to closing that debt is an amendment to a record that was
never attested. See [The estate and what needs
doing](/help/estate-and-worklist).

`retire` is reachable from `draft`, `baselined`, `approved` and `attested` — a
model registered in error does not have to be attested before it can be
withdrawn.

### Approving something on terms

SR 26-2 V lets you use a model before it is validated, **with compensating
controls**. Every firm already does this. What varies is whether the controls are
enforced or promised, and a conditional approval written into a committee minute
is a promise — the register cannot tell one that is being honoured from one
everybody has forgotten.

MAYA closes the list of conditions to ones it can actually do something about,
and refuses free text naming them. *The model will only be used for low-value
cases* is not a control; it is a hope with a date on it.

| Condition | MAYA... | How |
|---|---|---|
| `expires` | **enforces** | the approval lapses on the date and the model stops resolving |
| `environments` | **enforces** | resolution outside the listed environments is refused |
| `usage_cap` | **enforces** | becomes a quota on every grant for the model |
| `validated_by` | **enforces** | checked against the validation register |
| `exposure_cap` | **cannot check** | somebody named confirms it periodically |
| `human_review` | **cannot check** | somebody named confirms it periodically |

Read the middle column before anything else. The last two are **attested**: MAYA
does not see the exposure behind a call, and it does not see what happens to an
output after it is returned. The control is that a person confirms the condition
still holds, and an unconfirmed one goes stale and is reported.

That is a real control and it is not the same one. **If you believe your exposure
cap is machine-enforced you are worse off than if you know it is a diary entry**,
because you have stopped checking. MAYA says which is which on every condition
rather than letting you assume.

```
POST /api/v1/approval-conditions
{"urn": "...", "kind": "environments", "rationale": "not yet validated",
 "days": 60, "parameters": {"environments": ["uat"]}}
```

The window is mandatory and capped at six months. A conditional approval with no
end date is an unconditional approval that has not noticed yet — the same way a
temporary waiver reaches its fourth year. A longer exception is **renewed**,
which is a decision somebody takes again.

The terms are checked **when the model is used**, not when somebody signed.
Approval is a moment and use is continuous. A broken condition refuses resolution
with `approval_condition_broken`, and the refusal quotes the rationale the
condition was imposed under, because that is where the decision to lift it
actually sits.

Lift a condition with `/discharge` and a reason — usually the validation it was
waiting for. See [Lifecycle profiles](/lifecycle-profiles).

### One machine, and what each move costs

Every model in the register is on the state graph above. That is deliberate.
Every law this platform rests on is a statement about that graph — `L-1` is a
reachability proof over exactly two initial states, and the immutability of an
attested record is the reason amendments exist at all. A register whose
vocabulary varies by model is one nobody can read across: a supervisor would
have to ask which machine a model is on before knowing what `submitted` means
on it.

What does vary is **what each move costs**, and that varies by two things the
register already knows.

The **trainability class** says which evidence must be on file before a record
can be attested. `L-15` already makes every class declare that, so the platform
reads the declaration rather than keeping a second catalogue that would disagree
with it the first time either moved. A T3 model owes an independent review; a T0
does not, and asking for one is not rigour — it is a category error that wastes
a review cycle and teaches everybody the checklist is noise.

The **tier** says how many signatures approval and attestation take, and how
long a record may sit mid-move before somebody should ask. Returning a record is
one person's act at every tier: requiring a quorum to send something *back* is
how a review queue seizes up.

Only **attestation** is guarded by evidence, and that is the point — it is the
moment the record becomes immutable and in force. Checking earlier would block a
draft for lacking a validation report nobody could have written yet, and a
control that fires before it can be satisfied teaches people to route around it.

Read the reference lifecycles on **Lifecycle profiles**, or ask what a specific
move would take:

```
GET /api/v1/lifecycle-profiles          every class, side by side
GET /api/v1/lifecycle-profiles/T3?tier=1
GET /api/v1/lifecycle-readiness?urn=...&transition=attest
```

Readiness reports *on file but unreviewed* separately from *missing*. They are
different problems: a document nobody has accepted is already written and
sitting in a queue, and telling somebody to go and write it wastes a week.

### The queue nobody was watching

A record that has been `submitted` for four months is blocked by nothing here.
The submission succeeded, every gate passed, and until now no control anywhere
in the platform looked at the clock. That is how a governance queue becomes a
place things go to wait — the only thing that would show it is a state carrying
an expected duration, and no state had one.

Each transient state now carries one, by tier:

| State | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---|---|---|---|
| `submitted` | 10 days | 20 | 30 | 45 |
| `approved` | 5 days | 10 | 20 | 30 |
| `amending` | 30 days | 45 | 60 | 90 |

`attested` and `retired` carry no clock: they are where a record is supposed to
*rest*, and a duration on them would report every model in force as overdue.

Nothing is refused. A queue is allowed to have a queue — the reviewer may be
right to be taking their time, and blocking would punish the second line for
being careful. The `lifecycle.stalled` batch job raises an **advisory** finding
instead, and the *Lifecycle profiles* screen lists them worst-first. Where the
duration is measured from matters: the **evidence chain**, which already records
every transition with a timestamp, rather than a `status_changed_at` column that
would drift from it the first time anything wrote a status without recording why.

### What "immutable" blocks

An attested record refuses **field changes** (`PATCH /api/v1/models/{name}`) and
**new versions**. The second surprises people and is the important one: a new
version *is* a change to the model, and letting one be added to an attested
record is exactly how the record quietly stops describing what runs.

```json
{"error": "registry_refused",
 "detail": "cannot add a version to maya://model/credit.pd.smallbiz: this model
            is attested and therefore immutable; open an amendment to change it",
 "remediation": "the refusal names the clause that failed; satisfy it and retry"}
```

**409**. The URN is never editable in any state, the status moves only through
the transitions above, and the tier comes from an assessment rather than from a
field.

## Approval and attestation are different acts

**Approval** is one authorised person in the second line saying the work is
sound. **Attestation** is the set of people who will be asked about this model in
a supervisory meeting each putting their name to it — the owner that the controls
are operating, the second line that challenge was effective.

A button one person presses is not that, so attestation is a **quorum**:

```yaml
lifecycle:
  attestation:
    required_roles: [model_owner, model_risk_manager]
    validity_days: 365
```

```bash
POST /api/v1/models/{name}/attest
{"role": "model_owner", "decision": "attest",
 "statement": "Controls are operating and the model is used only for its
               approved purpose."}
```

Every named role signs, and the model becomes attested only when all of them
have. Two rules make it a quorum rather than a formality:

- **A principal may only sign for a role they actually hold** — `role_not_held`,
  403. An attestation signed under a borrowed hat is not a quorum.
- **Each required role signs once** — `already_signed`, 409.

**One decline ends it**, before the count is even looked at, and sends the record
back to be worked on: to `amending` if the attestation was for an amendment,
otherwise to `draft`.

### Expiry, and what is not built

An attestation carries an expiry, a year by default. Once it lapses the model
page says so and the scheduler raises a finding rather than waiting for somebody
to notice.

**There is no renewal endpoint.** `periodic` exists in the vocabulary of
attestation kinds and nothing constructs one. Renewal today is an ordinary
attestation round against the unchanged record; the lapse is detected and
reported, and the re-signing is not yet its own act.

## A version is approved by a quorum too

The record is attested by several people. A version — the thing that actually
runs — used to be approved by one, and that asymmetry was backwards: the record
says what the model is *for*, the version says what will *happen*.

The depth of control follows the tier, by the same adjunction (**L-5**) that
decides every other control set:

| Tier | Who must sign |
|---|---|
| 1 | model risk manager **and** validator |
| 2 | model risk manager **and** validator |
| 3 | one authorised person |
| 4 | one authorised person |

Ask rather than reading configuration:

```bash
GET /api/v1/version-approval-quorum
→ {"quorum": [{"tier": 1, "required_roles": ["model_risk_manager", "validator"],
               "signatures": 2},
              {"tier": 3, "required_roles": [], "signatures": 1}, …]}
```

Pretending a scheduling heuristic and a capital model deserve the same ceremony
is how a control becomes something people route around, so tiers 3 and 4 keep a
single signature and the register says plainly that they do. Approving a tier 1
or 2 version directly is refused as `quorum_required`; opening a quorum for a
tier 3 or 4 version is refused as `no_quorum_required`.

**A version whose model has no tier cannot be approved at all.**

> **409 `no_tier`** — this model has no risk tier, so how many signatures its
> version needs is undecided. *Assess the model first; approving before assessing
> would be a way of choosing your own control depth.*

That is the obvious way to game a rule of this kind, and it is closed.

**Signing is its own permission.** A validator holds `version:sign` and never
`version:approve`: they can complete a quorum and can never approve alone. And
the same person may not sign twice under two hats — `already_signed_personally`;
a quorum is a number of people, not a number of roles.

One decline closes the approval with the statement attached. A declined round
stays in the history and the next attempt is a new approval, so *"how many times
did this fail second-line review"* has an answer.

## Amendments, retirement and deletion

An **amendment** is a declared act. It says what is changing and why, returns the
record to `amending`, and creates an obligation: the amendment must itself be
submitted, approved and attested before the model is back in force.

```bash
POST /api/v1/models/{name}/amend
{"reason": "Recalibrate for the 2026 cycle", "scope": ["kernel", "thresholds"]}
```

A reason is required (`reason_required`, 422). Amendments get a reference —
`AMD-001` — because they get quoted in committee minutes. One is in flight at a
time per model, counting both `open` and `submitted`: two concurrent amendments
to one record produce a document nobody can reconstruct. Nothing is edited in
place and nothing is lost; a withdrawn amendment stays in the history as one.

**Retirement is a state.** It withdraws a model from use and keeps everything —
the record, the versions, the evidence, the findings. This is what almost every
situation calls for, and model owners and risk managers can do it.

**Deletion is the one act with no workflow, no reversal and no second
signature**, and it is checked against the **role** as well as the permission:

```json
{"error": "deletion_refused",
 "detail": "only an administrator may delete a model; everyone else retires it",
 "remediation": "POST /api/v1/models/{name}/retire, which withdraws the model
                 from use and keeps the record"}
```

**403.** A permission can be granted to a role by mistake; requiring `admin`
explicitly means the mistake has to be made twice.

Even then the evidence survives. A `model_deleted` entry is appended **before**
the rows go, so the chain records the intent even if the removal fails halfway,
and afterwards the model's whole history is still there ending with who deleted
it and why.

## Roles

Eight of them, over 72 permissions. Deliberately few: a permission system with
forty roles is one nobody can reason about, and the question that matters at an
audit — *who could have approved this?* — becomes unanswerable.

| Role | Line | Holds | Never holds |
|---|---|---|---|
| `model_developer` | 1st | `version:create`, define and materialise features, assemble training sets, `parameter:record`, attach documents, acknowledge and plan findings | `model:register`, any approve, sign, seal or attest |
| `model_owner` | 1st | everything a developer holds, plus `model:register`, `model:submit`, `model:amend`, `model:attest`, `model:retire`, `risk:assess`, issue and resolve warrants, raise findings, define monitors, propose overlays, `document:compile` | `model:approve`, `alias:move`, `version:approve`, conclude a validation, approve an overlay |
| `validator` | 2nd | all sixteen reads, open/record/conclude validations, raise/close/extend findings, `document:review`, `parameter:approve`, `feature:seal`, `featureset:seal`, `policy:author`, **`version:sign`** | `version:approve`, `alias:move`, `model:approve` — and builds nothing |
| `model_risk_manager` | 2nd | everything a validator holds, plus `version:approve`, `alias:move`, `model:approve`, `model:attest`, `model:retire`, tiering, `feature:certify`, warrant revocation, overlay approval, `regime:activate`, `policy:publish`, `report:cut`, baseline import | `version:create`, `model:submit`, `model:amend` |
| `auditor` | 3rd | the sixteen reads, plus `finding:raise` | everything else — closes nothing, approves nothing, builds nothing |
| `operator` | — | `model:read`, `warrant:read`, `evidence:read`, `monitor:read`, `monitor:evaluate`, `scheduler:read`, `scheduler:run` | any other governance act |
| `service` | — | `model:read`, `warrant:read`, `warrant:resolve`, `warrant:execute`, `monitor:observe`, `scheduler:read`, `scheduler:run` | evaluating a monitor — it delivers telemetry, it does not judge it |
| `admin` | — | all 72, and sole holder of `model:delete` and `principal:manage` | — |

Roles **compose**: a principal holds a set and gets the union. That is how a
small firm gives one person two hats visibly, rather than inventing a hybrid role
that hides the fact.

Six pairs are refused, because holding both defeats the control they exist to
enforce:

```
model_developer + model_risk_manager   a first line approving its own work
model_owner     + model_risk_manager   an owner approving and tiering their own models
model_developer + validator            the builder running their own effective challenge
model_owner     + validator            an owner signing off their own challenge
model_developer + auditor              the third line must not build what it audits
model_owner     + auditor              the third line must not own what it audits
```

The two `validator` pairs were added after a review pointed out that this page
described the role as "second line, never builds" while nothing stopped a
developer from holding it — and a developer who does can open the validation of
the version they wrote, record its results and conclude it.

Granting one anyway needs `allow_conflicts: true` on the create or role change,
so the exception is deliberate rather than accidental — **409
`incompatible_roles`** otherwise. A principal holding `admin` is not checked
against these pairs at all: break-glass is a conscious exception. Worth knowing
that the override flag itself is not written into the evidence payload; the
resulting role set is.

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

Scope filters **listings**, not just detail pages, and it filters *before* the
page is cut — page two of a filtered list must not be page two of the unfiltered
one with holes in it. A model outside your scope is not merely unopenable; its
existence is not disclosed by a count that does not add up.

## Segregation of duties

This is the part role separation alone cannot do.

The usual way to build it is a separate table of who-did-what, consulted when
somebody attempts a conflicting act. That table is a second source of truth about
history, and the moment it disagrees with the record, the control is worthless.

MAYA already has an append-only, hash-chained record of every governance act with
its actor and its subject. So segregation is checked **against the evidence chain
itself**: the artifact that proves what happened decides who may act next. There
is nothing to keep in step, and tampering to clear a conflict breaks the chain.

Five rules:

| Act | Refused if the same person previously recorded | Narrowed by |
|---|---|---|
| `version:approve` | `version_created` on that version | — |
| `alias:move` | `version_created` on that version | — |
| `validation:conclude` | `version_created` on that version | — |
| `finding:close` | `finding_raised` | `finding_id` |
| `finding:extend` | `finding_acknowledged` | `finding_id` |

```json
{"error": "segregation_of_duties",
 "detail": "the person who created a version may not approve it — solo recorded
            'version_created' against this subject at evidence #12",
 "remediation": "route the approval to someone in the second line who did not build it"}
```

**403.** Identity is compared after stripping the `person/` prefix and folding
case, because the platform writes an owner as `person/j.okafor` and
authenticates the same human as `j.okafor` — an `==` there was a duties check
anybody could step around by spelling their own name differently.

### When the subject is not where the evidence lives

The last two rows need a word, because this is where the design nearly failed
silently. A finding is raised against the **model** — that is where a reader
looks for it and what a compiled document cites — while the act being checked is
about one finding. Searching the chain under the finding's own id therefore found
nothing and permitted everything.

So a rule may name the payload field carrying the identity it is about, and the
check narrows the model's evidence to nodes whose `finding_id` matches. Raising
one finding on a model does not disqualify you from closing another; that would
be a different and much broader rule, and not the one anybody wrote down.

A rule that needs that discriminator and is given none matches **nothing** rather
than everything of its kind on the subject. Refusing acts nobody meant to forbid
is worse than the gap, and it is loud in a test rather than silent in production.

### What this does not cover

Two limits, stated because a control described more broadly than it runs is worse
than a smaller one described accurately.

**The check runs where a route names the subject.** It is wired on the direct
version approval, the alias move, concluding a validation, and closing or
extending a finding. **The quorum path does not run it** — opening and signing a
version approval do not name the version as a subject. Independence there rests
on the quorum being two different people in two second-line roles, which is a
real control and a different one.

**Administrators are not exempt.** Break-glass exempts you from the
incompatible-roles check, not from segregation. A single-account deployment
genuinely cannot complete a segregated path, and that is the correct answer
rather than a limitation to work around.

Closure is segregated a second time by a rule living in the findings register
rather than in this policy: the owner of a finding may not verify its own
closure, and closure evidence is required. *Did you raise it* and *do you own it*
are two questions and a person can fail either. See [Validation and
findings](/help/validation).

## Signing in

The interface uses a signed session cookie. Services and scripts use HTTP Basic
against the same principal register, so there is one identity store rather than
two:

```bash
curl -u a.mehta:… localhost:5006/api/v1/me      # your roles, permissions and scope
curl -u a.mehta:… localhost:5006/api/v1/roles   # the catalogue, the pairs, the SoD rules
```

Both are open to any authenticated principal. A person should always be able to
see what they are allowed to do without asking an administrator — a permission
system nobody can inspect is one people work around.

Passwords are PBKDF2-HMAC-SHA256, per-principal salt, 200,000 iterations. A
deliberately expensive derivation is right for a login form and wrong for an API
called a thousand times a minute, so a successful verification is trusted for
sixty seconds, keyed by a peppered digest of the presented secret and never the
secret itself. **Suspension is re-read on every request**: the cache shortens the
key derivation, never the authorisation decision.

Every failure returns the same response whether the username is unknown or the
password is wrong, and the unknown-user path still computes a dummy hash so the
timing does not give it away either. The user list of a model risk platform is an
organisational chart, and a login form that confirms who exists hands it over one
guess at a time.

### CSRF, on exactly one surface

A token defends **ambient authority**, and only ambient authority needs
defending. A session cookie is sent by the browser whether or not the page that
triggered the request came from us. An `Authorization: Basic` header is not; a
caller who can set it already holds the credential, and asking them for a token
as well would protect nothing while breaking every service client.

So the check applies to exactly one case — a state-changing method whose
authority came from the session cookie — and to nothing else:

| | |
|---|---|
| Header | `x-maya-csrf`, or the form field `csrf_token` where a page posts without JavaScript |
| Where the page gets it | a `csrf-token` meta tag; the bundled script attaches it to every `fetch`, XHR and form |
| Exempt methods | `GET`, `HEAD`, `OPTIONS` |
| Exempt paths | `/login`, `/auth/login`, `/auth/callback` — exactly, never as prefixes, because a prefix exemption grows silently as routes are added beneath it |
| Refusal | **403 `csrf_token_invalid`** |

It runs as middleware rather than as a check in each route, because there are 107
mutating endpoints and a control that many places have to remember is a control
that will be missing from the next one. The token is **per session, not per
form**: a single-use token breaks the back button, breaks two tabs, and breaks
every page that issues several posts from one render — and a control people route
around is worse than one they never had, because it also reports success.

This exists even though the cookie is `SameSite=Strict`, because that is one
defence, implemented by somebody else's software, and its removal would be
invisible from here.

### Request ids

Every request carries one. Send `x-request-id` and it is honoured; send something
that is not `[A-Za-z0-9._:-]{1,64}` and it is **replaced** rather than escaped,
because a caller-supplied string on a log line is log injection. It comes back on
the response, and it is stamped on every log line the call produced — including
the ones from libraries, because the filter is installed on the handler rather
than on one logger.

One access line per request carries the method, path, status and duration. The
Python SDK sends an id per call, exposes `client.last_request_id`, and puts it on
every `Refused` exception, so *"it failed"* and *"which of the four thousand log
lines was mine"* stop being separate investigations.

### Through a directory

MAYA speaks OIDC: authorisation code with PKCE (S256, always), a `state` and a
`nonce`, all checked. `GET /api/v1/sso` says whether it is configured and exactly
what it will do.

**The token's signature is verified against the provider's published key**, with
an RS256 verifier in the standard library — no dependency, so the platform still
deploys air-gapped. It *constructs* the padded block the signature should have
produced and compares the whole of it rather than parsing what it recovers; it
decides the algorithm itself rather than reading `alg` from the token, because an
algorithm the sender chooses and the verifier obeys is how a token gets accepted
with no signature at all; a key under 2048 bits is refused; and several published
keys with no `kid` is `ambiguous_key` rather than trying each in turn, which
would make a token valid if *any* key signed it.

**SSO being down does not lock anybody out.** An unreachable provider refuses the
login with the reason (`provider_unreachable`, 503) and points at local
credentials. A directory outage should not take the model register with it.

#### What happens to roles

An identity provider that grants MAYA roles is an identity provider that decides
segregation of duties — and the person administering it is very often the person
whose duties are being segregated. So **group claims are mapped, never obeyed**:

```yaml
auth:
  oidc:
    group_claim: groups
    provision: false
    roles:
      maya-developers: model_developer
      maya-validators: validator
      maya-risk: model_risk_manager
```

The group name is the key because that is what the directory controls; the role
is the value because that is what MAYA controls, and the direction of that arrow
is the whole point. **A group with no entry grants nothing.** It does not grant
itself.

The incompatible-roles check applies here exactly as it does to a locally created
principal, and it is checked **before** whether the person is known here, so a
"you are not provisioned" message cannot hide the more serious problem behind the
lesser one:

> the directory places solo in groups that map to incompatible roles: a
> developer who can also approve versions is a first line approving its own work.
> *Fix the group membership, or the mapping; accepting both would let a directory
> decide segregation of duties, and refusing quietly would hide that it had.*

`auth.oidc.provision` is **off by default**. Auto-provisioning gives everybody in
the directory a foothold in the model register, and that should be a decision
somebody makes rather than inherits. With it off, somebody who authenticates
perfectly well and has no principal here is told so (`not_provisioned`, 403).

What is recorded is the issuer, the subject, the groups, and which groups mapped
to which roles — not the whole token, which carries more about a person than a
governance record needs. Without it, *"why did this person have that role in
March"* becomes unanswerable the moment the directory moves on.

```bash
POST /api/v1/sso/preview      # which roles would these claims get? (principal:manage)
```

Answers that without signing anybody in — for wiring up a mapping before somebody
finds out the hard way.

## Tightening a gate without a release

Several refusals on this page are written in the registry: an attested record
does not accept changes, an alias points only at an approved version, a warrant
does not resolve over a blocking finding. Those are invariants and they stay
where they are.

What was missing was a way to *add* a condition — *tier 1 versions also need a
validation episode*, *this environment also needs an accepted MDD* — without
waiting for a release. Four gates publish facts a rule may read:

```bash
GET /api/v1/policies              # what is in force on each gate
GET /api/v1/policies/facts/{gate} # version:approve · alias:move · model:mutate · warrant:resolve
```

### A rule is a predicate, not a program

```
blocking_findings == 0 and (tier > 2 or validated)
```

Comparison, membership, `and`/`or`/`not`, a conditional, arithmetic, and
`any` · `all` · `len` · `min` · `max` · `abs` · `sorted` · `sum` over a
collection. **No loops, no assignment, no function definitions, no attribute
access.** That is what makes a rule something a reviewer can reason about rather
than something they have to run.

A name that is not one of the gate's published facts is refused **when the rule
is written**:

> **422 `unknown_fact`** — the rule reads `phase_of_the_moon`, which this gate
> does not publish. *A rule that failed at the moment of a governance decision
> would have failed at the worst possible time, so it is refused now.*

### A policy carries its own cases

A policy is drafted with at least two cases — facts, and the verdict the author
says those facts deserve — and **cannot be published until they pass**. At least
one must be a case the policy *refuses*:

> **422 `no_refusing_case`** — none of the cases expects this policy to refuse
> anything. *A policy nobody has shown to refuse is a policy nobody has shown to
> be a gate; add a case it must turn down.*

### Loosening is allowed, and is never quiet

Publishing a version that permits something its predecessor refused is a
legitimate act; rules do change. So the register replays the outgoing version's
cases against the incoming rule and reports every verdict that flipped, in both
directions:

```json
{"loosened": [{"name": "an attested record is not", "was": "refuse", "now": "allow"}],
 "tightened": [],
 "detail": "1 case(s) the previous policy refused are now permitted"}
```

The drift is written into the `policy_published` evidence too, so it can be read
back later. A change that loosens a gate should be something somebody decided,
not something somebody discovered.

Authoring and publishing are separate duties: a validator or a risk manager
drafts (`policy:author`), only a risk manager publishes (`policy:publish`). A
rule authored and enacted by one person is a rule nobody reviewed.

### The boundary, stated plainly

**A policy can tighten a gate. It cannot loosen one.** Every check written in the
registry stays exactly where it is, and a policy runs *in addition* to it,
refusing with `policy_refused` (403).

That is a smaller promise than "the gates are the policy", and it is the honest
one. Replacing an invariant with a line of configuration means a mistyped rule
can weaken the platform, and the failure would look like a successful deployment.
Tightening without a release is the half of the problem worth solving; loosening
a gate should cost a release, and does.

An instance that publishes nothing runs exactly what it ran before — the built-in
rules are the default for every gate, written in the same language so they can be
read alongside anything that replaces them.
