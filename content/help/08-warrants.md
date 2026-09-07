---
title: Warrants and execution
slug: warrants
section: Execution
order: 80
icon: key
summary: One signed document for every kind of model, differing by refusal rather than by shape — its four-axis grammar, the fourteen admissibility laws checked before the signature, what resolution refuses in order, and what an engine must do before it touches an artifact.
audience: Engineers, Model risk, Quants
---

# Warrants and execution

A **warrant** is a signed instrument authorising a named principal to perform a
stated operation on a stated model version, within limits, until a stated moment,
revocable at will. It is the entire interface between MAYA and whatever runs your
models.

The claim this page has to make good is a strong one. **One document describes a
Black–Scholes closed form, a Hull–White calibration, a gradient-boosted PD model,
a logistic scorecard, a prompt bundle, an agent with tools, a credit policy
rulebook, a spreadsheet and a vendor black box** — without becoming a union of
special cases, because a union of special cases is a format that breaks the first
time somebody brings a model nobody anticipated.

It does that by differing per kind of model as **refusals over one document**
rather than as different documents. Fourteen admissibility laws, each keyed on a
fact the platform *derives*, decide what is coherent to ask.

## Why the boundary exists

**MAYA does not execute models.** It issues warrants; an execution engine acts on
them. Keeping issuance and execution apart means the control plane can be
unavailable for a minute without the bank stopping, and an execution engine can
be replaced without renegotiating governance. See [What MAYA
is](/help/what-is-maya#what-maya-does-not-do) for why a governance platform that
is also the runtime is the version of this that gets bypassed.

## Grants and warrants are different things

A **grant** is the standing entitlement: this principal, in this environment, for
this declared use.

```bash
POST /api/v1/warrants
{"urn": "maya://model/credit.pd.smallbiz#champion",
 "environment": "prod",
 "principal": "svc/origination",
 "declared_use": "origination_decision"}
```

A **warrant** is the short-lived credential minted against that grant at the
moment of use:

```bash
POST /api/v1/resolve?verb=score
{ …the same four fields… }
```

The `verb` is a query parameter and defaults to `score`. A fit is minted through
its own endpoint, because it needs a featureset and a window that a score does
not:

```bash
POST /api/v1/fit-warrants
{"urn": "…", "environment": "lab", "principal": "svc/model-lab",
 "declared_use": "model_development",
 "featureset": "nj_home_core", "featureset_version": 1,
 "window": {"from": "2019-01-01", "to": "2024-12-31"},
 "as_of": "2025-01-15T00:00:00Z"}
```

Separating grant from warrant is what makes revocation meaningful. Withdrawing
the grant stops future warrants; bumping the revocation epoch invalidates the
ones already out.

## What resolution refuses, in order

Every check is cheaper than the one after it, and each refusal is more specific
than the last.

| | Check | Refusal |
|---|---|---|
| 1 | Does the URN parse? | `validation_failed` 422 |
| 2 | Is the model registered? | `not_found` 404 |
| 3 | May this principal read this model, in this entity? | 401 · `forbidden` 403 · `out_of_scope` 403 |
| 4 | Is the caller the principal, or entitled to act for them? | `principal_not_self` 403 |
| 5 | Is anything blocking? | `blocked` 423 — see [Validation and findings](/help/validation) |
| 6 | Does this principal hold a grant here? | `no_entitlement` 403 |
| 7 | Has the grant been withdrawn? | `revoked` 410 |
| 8 | Is the declared use the approved use? | `use_not_approved` 403 |
| 9 | Is anything bound for this URN in this environment? | `not_found` 404 |
| 10 | Is that version approved? | `restricted` 423 |
| 11 | Does a policy on the `warrant:resolve` gate refuse it? | `policy_refused` 403 |
| 12 | Is there a point of `P` to run at? | `no_approved_parameters` 409 |
| 13 | Does the assembled document satisfy the grammar? | `grammar_violation` 422 |

Two orderings are deliberate. **Revocation is checked before the use
comparison**, because a withdrawn warrant is withdrawn whatever the caller claims
to be doing with it. And **the grammar is checked before the signature**, never
after — a signature over a non-conforming document would assure that the document
is *authentic* and not that it is *usable*, and engines would reasonably read it
as both.

Note what is *not* in that list: the model's lifecycle state. A `baselined` model
resolves normally, which is what *"existing use is not blocked, change is"* means
in the code path rather than in a slogan.

Resolution **fails closed**: there is no path that degrades quietly into
something that looks like it worked.

## The URN is all a consumer holds

A consumer holds a [URN](/help/registering-a-model#the-urn) — bare, pinned with
`@3.2.1`, or aliased with `#challenger` — and nothing else. Artifact location,
schemas, boundaries and policy are resolved at runtime from it. That is exactly
what lets a governed version move happen without a consumer redeploying, and what
makes the alias move the most tightly controlled operation in the platform.

## The ten sections

Ten sections, each answering exactly one question, under three top-level fields
that identify the document itself.

```json
{
  "maya_warrant": "1.0", "warrant_id": "wrt_…", "issued_at": 1767225600.0,
  "subject":     { …which model and version this is about },
  "operation":   { …what is being asked of it },
  "parameters":  { …where the parameter object comes from },
  "realisation": { …how to obtain and invoke the artifact },
  "data":        { …where inputs come from and where outputs go },
  "io_contract": { …the input and output schemas },
  "constraints": { …the operating boundary and resource limits },
  "authority":   { …who may do this, for what, until when },
  "governance":  { …the state of the record at the moment of issue },
  "signature":   { …integrity }
}
```

All ten are required, and a missing one is reported by name — *every warrant
carries all ten sections; an absent one is not an empty one*. `maya_warrant` is
checked separately as a grammar version, and if either fails the validator stops
there: nothing below can be trusted yet.

Three carry more than their one-line description suggests. **Constraints** holds
the operating boundary from the version's contract, which is what lets an engine
refuse *before* touching the artifact, alongside resource limits. **Governance**
holds the tier and the model and version status at the moment of resolution, so
what an engine acted on can be reconstructed later even if the model has moved on
since. **Signature** is HMAC-SHA256 over the canonical form, with the signature
block excluded rather than blanked.

## The four axes

Every model a bank runs differs along exactly four **independent** axes:

| Axis | Field | Vocabulary |
|---|---|---|
| How the parameter object is inhabited | `parameters.kind` | **8**: none, calibration_set, estimated_coefficients, learned_weights, llm_configuration, rule_set, elicited_weights, opaque |
| How the kernel becomes runnable | `realisation.runtime` | **nineteen runtimes** (below) |
| What is being asked of it | `operation.verb` | **10**: score, fit, validate, backtest, explain, simulate, stress, optimise, generate, monitor |
| Where its data comes from | `data.*.binding` | **12**: request, inline, feature_namespace, featureset, dataset_snapshot, delta_table, sql_query, stream, market_data, document_corpus, scenario_set, artifact |

The grammar's nineteen runtimes, grouped by what they are:

| | |
|---|---|
| Code | `python.callable` · `container` · `rest` |
| Portable model formats | `onnx` · `pmml` · `pfa` |
| Quantitative libraries | `quantlib` · `estimator` · `solver` |
| Statistical platforms | `sas` · `r` · `matlab` |
| Declarative | `formula` · `sql` · `spreadsheet` · `rules` |
| Generative | `llm.prompt` · `llm.agent` |
| The honest one | `descriptor_only` |

Three are odd ones. **`formula`** is the one with nothing to locate: its
`entry.expression` is the whole of `f`, written in the language MAYA already
parses for derived features, so there is no artifact, no digest and no engine —
the JSON *is* the model. It exists because a bank runs hundreds of small
closed-form models — a scorecard, a logistic link, an LGD haircut, a Basel risk
weight — and every one of them previously had to be `descriptor_only` (governed
and unrunnable) or wrapped in a container, which turns four lines of arithmetic
into an artifact somebody has to build, sign and store. `P` is inhabited the
ordinary way: an expression naming only its inputs is T0, one naming
coefficients is T2 and they arrive as an approved parameter set.

`estimator` is the only runtime whose job is to **inhabit** a parameter object
rather than to read one. `rules` is the newest, and the only one
whose parameter object is a document MAYA can *read*: for a T8 model the rule set
**is** `P`, so it arrives the way every register-held parameter object does, and
running one at an unapproved point of `P` is refused by the same mechanism that
refuses running a scorecard at unapproved coefficients. See
[Rule sets](/help/rule-sets). `descriptor_only` is one of the nineteen and
matters most in a bank, because much of the estate already runs inside engines
nobody is going to replace.

### The equation and the code, both derived

A `formula` version can be read as mathematics and as Python:

```bash
GET /api/v1/mathematics?urn=maya://model/credit.pd.smallbiz&semver=1.0.0
```

comes back with `latex`, `python`, and the expression both were derived from.
**Neither is stored**, and that is the design rather than an economy. A `latex`
field beside the expression — filled in by whoever wrote it — is a second
description of one model, and two descriptions drift, with the one nobody
executes drifting first. These are rendered from the syntax tree the platform
evaluates, so a disagreement between the equation, the code and the answer is
not possible rather than merely unlikely.

The Python is a whole importable module, not a fragment: a validator's
independent recompute should be `import kernel; kernel.predict(**row)` rather
than an exercise in assembling somebody's snippet. Declare `symbol` on an input
and it typesets as that symbol; a field with none is set upright, because
`debt_service` in italics reads as nine letters multiplied together.

Every other runtime names an artifact MAYA does not read, and asking for its
mathematics answers `not_derivable` — inventing an equation for a model the
platform cannot inspect is exactly the invented description this avoids. For
those the mathematics belongs in an attached document, where a person signs
for it.

Two further closed vocabularies sit alongside the four. Where an output may go —
`response`, `delta_table`, `stream`, `artifact`, `parameter_object`, `evidence`.
And where a parameter object may come from — `artifact`, `parameter_set`
(carrying the set *and* its digest), `declared` (carrying the values),
`to_be_fitted`, `vendor_internal`.

The grammar is the **product** of those four, not their union. A QuantLib pricer
is `(none, quantlib, score, market_data)`. The Hull–White calibration behind it
is `(calibration_set, quantlib, fit, market_data)` — same runtime, three
different coordinates. An XGBoost PD model is `(learned_weights, onnx, score,
feature_namespace)`. An LLM summariser is `(llm_configuration, llm.prompt,
generate, document_corpus)`.

One structure. Different coordinates. And it extends the right way: a new model
technology is a new **value** in one vocabulary — almost always a runtime — not a
new section, not a new document type, and not a change to anything that already
works.

## The fourteen admissibility laws

A warrant can be well-formed and still be nonsense. These are the rules that make
such a document a refusal rather than a runtime failure, and the important ones
are not invented — they fall out of the algebra already in the platform.

Validation runs in two passes. **Shape and vocabulary** violations — an unknown
verb, a missing section, a binding with no key, an unknown sink, a verb whose
required sections are empty — are all reported together as **L-W0**. Only if the
shape is clean does the admissibility pass run, and then it reports *all* its
failures together too. Whoever is writing a warrant by hand wants the whole list;
fixing one error to be told about the next is the worst possible interface for a
document with ten sections.

**L-W1 — you cannot fit what has nothing to fit.** The trainability class is
*derived* from how the parameter object is inhabited, and T0 (parameters from
theory) and T6 (parameters inside a vendor black box) are precisely the classes
for which fitting is a type error. The same law also refuses a
`subject.trainability_class` that is not one of T0–T8 — a value of `"T6 "`, with
one trailing space, would otherwise slip past every class-keyed law below it.

```json
{"law": "L-W1", "path": "operation.verb",
 "detail": "a T0 model cannot be fitted: its parameters come from theory, not
            from data — there is nothing to fit",
 "remediation": "ask for 'score', 'validate' or 'explain'; if this model really
                 is fitted, its parameter_kind and fit_procedure are wrong"}
```

**L-W2 — `generate` needs a generative runtime.** An ONNX graph does not produce
prose. Only `llm.prompt` and `llm.agent` do.

**L-W3 — training data must be readable as-of.** A training set assembled from a
source with no transaction time cannot be shown point-in-time correct, so it
cannot be shown not to have leaked. On a `fit`, **every** input must use one of
the three bitemporal bindings: `dataset_snapshot`, `feature_namespace`,
`featureset`.

**L-W4 — a `fit` must say where its parameters go.** It produces a *new*
parameter object rather than editing the old one, so it needs an output whose
sink is `parameter_object`.

**L-W5 — a determinism claim MAYA cannot check must be pinned.** An LLM at
temperature 0.7 is not reproducible, and neither is a Monte Carlo simulation
without a seed; a warrant asserting either is will be believed by whatever reads
the result. So a claim of determinism from a runtime that executes **arbitrary
code** — `container`, `python.callable`, `r`, `matlab`, `solver`, `rest`,
`llm.prompt`, `llm.agent` — must supply `operation.seed`.

The question is not whether the runtime is random, which no runtime name can
answer. It is whether MAYA can *check* the claim. `pmml`, `onnx`, `sql`,
`spreadsheet` and `descriptor_only` are exempt because their determinism is a
property of the format rather than of whatever somebody wrote inside it.
`quantlib` is exempt as a **named gap**: its determinism is decidable from the
`pricing_engine` its entry declares, and that check is not built. `estimator` and
`rules` are exempt for the opposite reason — MAYA holds what they run, so it can
verify the claim by *executing* it. `L-3` runs the estimator twice and compares
bit for bit; a rule set is a document the platform reads and evaluates itself.
Both are better evidence than a seed.

**L-W6 — a descriptor-only model cannot be fitted.** Descriptor-only is a
legitimate state: the bank holds the licence, the engine holds the artifact, MAYA
holds the governance. What it cannot carry is an instruction to inhabit a
parameter object nothing on this side can reach.

**L-W7 — a backtest needs outcomes.** An input must carry `labels` or an
`outcome_column`. Otherwise it is a re-score wearing a backtest's name.

**L-W8 — a run must name which point in `P` it runs at.** Four distinct
refusals live here: a source that is absent while the kind is not `none`; a
binding outside the closed vocabulary; a `fit` bound to anything but
`to_be_fitted`; a non-fit bound to `to_be_fitted`; and a source missing the keys
its binding requires — a `parameter_set` without a digest, a `declared` without
values. A warrant that names a kernel and leaves its parameters implicit
describes a result nobody can reproduce.

**L-W9 — a read for fitting must be bounded in both clocks.** An `as_of`, and a
window with a start and an end. It applies to `featureset` **and**
`feature_namespace` — the two live sources. A `dataset_snapshot` is bounded by
construction, being a fixed set of rows pinned at a Delta version, so it needs
neither.

**L-W10 — a featureset must provide what the kernel declares it reads.** Checked
by `POST /api/v1/fit-warrants` rather than by the grammar validator, because it
needs the register: the grammar can see that a warrant names a featureset, but
only the register can say whether that set covers the version's declared inputs.
Refused as **409 `schema_not_satisfied`**, naming the missing slots. It is
contravariant, so a *wider* set passes — the extra columns are simply not read,
and refusing them would make a set unshareable, which is what sets exist for.

**L-W11 — a calibration must say what it was calibrated as of.** A calibrated
model *reproduces a market* rather than summarising a history, so the moment it
was solved for is part of what it means. Two warrants naming the same parameter
set on different mornings are not the same run, and without the stamp staleness
is silent: the engine runs yesterday's swaption fit against today's book,
produces an entirely ordinary-looking number, and nothing in the record says
which market it came from.

The law requires the age to be **statable, not small**. How old is too old
depends on the calibration cadence, and that is a policy gate's question — so the
warrant carries `parameters.source.as_of` and something with an opinion decides.

**L-W12 — parameters that live inside an artifact need that artifact digested.**
When the parameter object *is* the file, "which numbers did this run at" and
"which bytes did it load" are the same question, and an artifact binding with no
digest answers neither.

This is the law that bites hardest on a neural network, and it is deliberately
not written in terms of the class: a PMML scorecard is T2 and carries exactly the
same exposure. Keying it on the trainability class would have missed that.

**L-W13 — a generative runtime must pin the build, not just the model name.**
`base_model` names a *family*. The weights behind that name are replaced by
whoever hosts them, on their schedule, and the replacement is not announced in
the answer — so a warrant carrying only the family name describes a model that
can change under it between two runs while every field in the document stays
identical. `realisation.entry.base_model_version` is what closes it.

That is the failure this platform exists to prevent, in its generative disguise:
a stable identifier over moving contents. Pinning does not stop the vendor
retiring a build; it makes the retirement visible as a **mismatch** instead of a
drift.

### Notice what the last three have in common

Each is keyed on a fact the platform **derives** — the parameter kind, the source
binding, the runtime — and none mentions a category anybody attached to a model.
That is the whole answer to *"should warrants be templated per kind of model"*:
they already differ per kind of model, as refusals over one document.

## Profiles: templating the request, never the warrant

The recurring ask is "warrants should be templated by kind of model". It is half
right, and the wrong half is expensive.

**The document must not fork.** If a T4 warrant had a different *shape* from a T3
warrant, every engine, replay path and audit query would have to branch on model
type before reading anything, and the branch would grow a case per model family
forever.

**The content already differs, derivably.** The parameter kind, the admissible
verbs, the artifact block, the determinism, the required bindings — each computed
from a fact rather than declared.

What is genuinely tedious is the **request**: the same verb, the same ceiling and
the same binding shape retyped for every warrant of a given shape. That is what a
profile fills in.

```bash
curl -u j.okafor:… -X POST localhost:5006/api/v1/warrant-profiles \
  -H 'Content-Type: application/json' \
  -d '{"name": "trained_artifact_prod",
       "when": {"trainability_class": ["T3"], "environment": ["prod"]},
       "defaults": {"verb": "score", "max_seconds": 3}}'
```

Three constraints keep it from becoming a taxonomy.

**It selects on facts the platform derives**, never on a category somebody
attached. Nine are selectable: `trainability_class`, `parameter_kind`,
`fit_procedure`, `runtime`, `artifact_format`, `environment`, `tier`, `domain`,
`model_class`. A declared taxonomy sitting beside a derived one is two answers to
one question — `neural_network` on a model whose `parameter_kind` says
`calibration_set`, and no rule for which wins. Selecting by derived facts means a
profile *cannot* disagree with the truth, because the truth is what chose it.

**It cannot widen authority.** Five keys may be defaulted — `verb`,
`max_seconds`, `mode`, `inputs`, `outputs` — and fifteen never can, including the
principal, the declared use, the environment, the URN and semver, the TTL and
grace, the binding kind, the signature and the whole `authority`, `governance`
and `subject` sections. The refusal happens **at creation**, because a check
performed when the profile is written is one nobody can forget to perform at use:

```json
{"error": "authority_not_defaultable",
 "detail": "'principal' decides who may act, for what, or until when, so a
            profile may not supply it",
 "remediation": "authority is granted per principal and per use, never inherited
                 from a template; if this is an obligation rather than a
                 convenience, write it as a policy on the 'warrant:resolve'
                 gate, which refuses instead of suggesting"}
```

**403.** Ask what may be selected on and what may be filled:

```bash
GET /api/v1/warrant-profile-vocabulary
→ {"selectable_facts": {…}, "defaultable": {…}, "never_defaultable": […],
   "detail": "a profile fills holes in a request; it never overrides a caller
              and never widens authority"}
```

**It never overrides a caller.** A profile fills holes. A value the caller
supplied is theirs — including one identical to the default, because "the caller
asked for this" and "nobody said, so we chose" are different facts, and only one
of them is the caller's responsibility.

### Several may match, and they fold

Profiles compose the way featuresets do: **left to right, rightmost wins, `{}` as
the identity**, ordered by how many facts each tests so the most specific speaks
last. That is a monoid, and saying so is what makes `(A ∘ B) ∘ C` and
`A ∘ (B ∘ C)` the same result rather than a question about declaration order.

Rightmost wins **per key**, not per profile — a general profile still supplies the
verb a specific one says nothing about.

```bash
POST /api/v1/warrant-profiles/preview
{"urn": "maya://model/fraud.card.nn", "environment": "prod"}
```

```json
{"request": {"verb": "score", "max_seconds": 3},
 "profiles": [{"name": "everything", "version": 1, "when": {}, "specificity": 0},
              {"name": "trained_artifact_prod", "version": 1,
               "when": {"trainability_class": ["T3"], "environment": ["prod"]},
               "specificity": 2}],
 "applied": {"verb": "everything@1", "max_seconds": "trained_artifact_prod@1"},
 "facts": {"trainability_class": "T3", "runtime": "onnx", "environment": "prod"},
 "detail": "2 value(s) filled from 2 profile(s)"}
```

Every value names the profile it came from. A default whose origin cannot be
named is a value nobody can argue with later.

Profile versions are immutable; publishing again mints a new version.
`POST /api/v1/warrant-profiles/{name}/retire` stops it matching future requests,
and warrants already shaped by it stand — they were never derived from the
profile, only filled by it.

### What a profile must not hold

**Obligations.** "A T3 warrant in prod must carry a digest" is not a default — a
default is something you can drop. It is a law (**L-W12**) or a policy on the
`warrant:resolve` gate, and both **refuse** rather than suggest.

| Want | Put it | Because |
|---|---|---|
| Save typing | a **profile** | it fills holes and is re-validated afterwards |
| Refuse something | a **law** or a **policy gate** | a default can be dropped; a refusal cannot |
| Decide who may act | a **grant** | authority is per principal and per use |

## Checking a warrant

The grammar is published rather than documented, because a contract nobody can
check is a convention:

```bash
GET  /api/v1/grammar          # the four vocabularies, and what each verb means
GET  /api/v1/grammar/schema   # JSON Schema, generated from the vocabulary
POST /api/v1/grammar/validate # check a document
```

The schema is generated rather than hand-written. A schema maintained separately
from the vocabulary it describes will disagree with it, and the disagreement is
discovered by whoever trusted the schema.

## Expiry, grace and the revocation floor

TTL and grace are keyed by risk tier:

```yaml
warrants:
  ttl_seconds:   {1: 60, 2: 300, 3: 3600, 4: 3600}
  grace_seconds: {1: 0,  2: 0,   3: 900,  4: 900}
  jitter_pct: 20
```

A Tier 1 model gets sixty seconds and **zero grace**: it must never run on stale
authorisation. Tiers 3 and 4 get grace so a transient control-plane outage does
not stop the business.

**Jitter** spreads expiry across a band and is capped at 50% however it is
configured. Without it, a fleet issued warrants at deploy time expires in lockstep
and stampedes the resolver at the worst possible moment — synchronised expiry was
adversarial finding **H-1**.

**The revocation floor** is the rule grace never overrides: a warrant on the
local revocation list is refused regardless of grace state. Grace extends how
long an *authorisation* stays current when the platform is unreachable; it never
extends how long a consumer may stay ignorant of a withdrawal it has already been
told about. This was finding **C-1**.

The signing secret comes from `warrants.signing_key`. The `key_id` in the
signature block is *derived* one way from that secret rather than configured, so
a signature names the key without disclosing it, and a well-known development
secret logs a warning on startup.

## Revocation

```bash
POST /api/v1/warrants/revoke
{"urn": "maya://model/credit.pd.smallbiz", "reason": "Suspected leakage"}
→ {"revoked": 4, "urn": "…", "reason": "…", "epoch": 7}
```

The kill switch: every grant on the model is withdrawn and the revocation epoch
is bumped, so warrants already in flight can be recognised as stale by any engine
that checks. Warrants carry the epoch they were minted under, and the section
that carries it says the check is **required**.

## What an engine must check, before it touches the artifact

1. **Verify the signature.** An unsigned or tampered warrant is not a warrant.
2. **Check the local revocation list** — before expiry, because of the revocation
   floor: a revoked warrant is refused regardless of grace state.
3. **Check expiry, including grace.** Past `expires_at + grace_seconds`, refuse.
4. **Check the operating boundary.** Inputs outside the contract's assumptions
   mean the guarantees are void. Refuse rather than produce a number nobody
   should rely on.
5. **If the parameters come from a registered set, read the values and re-derive
   their digest.** Not compare two stored digests — those are two copies of one
   claim, and they agree happily over values somebody edited underneath them.
6. **Only then** load the artifact, verify its digest against the warrant, and
   run.

The ordering is the design. Every check that can be made without touching the
artifact is made first, so a refusal is cheap and an artifact is never loaded on
an authorisation that was never valid.

## The captive engine

MAYA ships one engine — the **captive engine** — but it is a reference consumer
of the public contract, not a privileged component.

```bash
POST /api/v1/execute
{"urn": "maya://model/credit.pd.smallbiz#champion",
 "environment": "prod", "principal": "svc/origination",
 "declared_use": "origination_decision", "inputs": {"dscr": 1.4}}
```

It resolves a warrant through the same public path an external engine uses, then
performs the six checks above. Structurally it holds no direct reference to the
registry or the feature store — there is a test asserting exactly that, because a
boundary is only real if it is enforced by construction rather than by intention.
What it holds is the warrant service, and through it the public contract; the
moment a bundled engine can reach past that contract, the contract stops
describing what actually happens.

Switch it off with one key, and nothing else changes:

```yaml
execution:
  captive:
    enabled: false
```

### What it implements

**Five runtime implementations, answering for six of the grammar's eighteen
runtimes**, and it is precise about which:

| Runtime value | What it does |
|---|---|
| `python.callable` | a callable bound to a version in process, for development |
| `descriptor_only` | answered by the same implementation, and the *correct* case for it — MAYA holds the governance, the engine supplies the model |
| `onnx` | loads and runs an ONNX graph through onnxruntime |
| `pmml` | evaluates the `RegressionModel` and `Scorecard` subset **natively, without a JVM** |
| `quantlib` | prices six instruments, with the valuation date taken from the warrant |
| `estimator` | the only one that *inhabits* `P`: `ols` and `garch11` |

A warrant naming a runtime it does not implement is refused **by name**, not by
failing three layers down inside an artifact loader. The refusal distinguishes two
cases needing different actions: a runtime this engine never implemented
(`no_runtime`, 501 — route the warrant elsewhere) and one it implements whose
dependency is missing (`runtime_unavailable`, 503 — install the package, and the
message names it).

```bash
GET /api/v1/engine
```

serves the engine's account of **its own isolation** — what the sandbox is, what
it protects against, and what it does not. An engine that runs artifacts owes its
callers that statement, and a name like "sandbox" left unexplained implies a
guarantee the process model does not provide. Where the captive engine is
disabled it says so rather than returning nothing:

```json
{"captive_engine": "not enabled",
 "detail": "this instance issues warrants and runs nothing"}
```

### PMML without a JVM

Every mature PMML library embeds one. That is a heavy dependency for a governance
platform, and it puts a second runtime between the digest we verified and the
number we return.

So the two element types covering most of a bank's PMML estate are evaluated
directly: `RegressionModel` — the logistic and linear scorecards credit risk has
run for forty years — and `Scorecard`, the points-based form. Both are arithmetic
over coefficients held in the XML, and the coefficients *are* the deliverable: a
scorecard's whole appeal is that you can read it.

Anything else is refused by name (`pmml_unsupported`, 501), and so is anything
inside those two elements that is not implemented: a normalisation method outside
`none`, `softmax`, `logit` and `exp`, or a predicate operator outside the six
supported. A partial implementation that silently mis-evaluates a tree ensemble
would be far worse than one that says it only does regressions.

### The artifact digest is verified before anything runs

```json
{"error": "artifact_mismatch",
 "detail": "sb.pmml does not match the digest in the warrant
            (expected sha256:9f2c1a…, found sha256:4e8a17…)",
 "remediation": "the artifact has changed since it was approved; do not run it
                 and raise a security incident"}
```

The digests in that message are prefixes — enough to tell two artifacts apart at
a glance; the full values go to the log. A warrant carrying no digest at all is
refused separately as `artifact_unverifiable`, because "there was nothing to
check against" and "we checked and it matched" must never look the same.

This is the point at which the whole chain — registry, warrant, signature —
either does or does not describe the bytes about to run. An engine that skips it
makes every link before it decorative.

Artifacts are read from a configured directory and a path resolving outside it is
refused (`artifact_outside_root`). A warrant is a document from elsewhere, and
treating a path inside it as trustworthy is how a governance system becomes a
file-read primitive.

### Isolation, and exactly how far it goes

Artifact-backed runtimes — ONNX and PMML — do not run in the web process. Each
invocation happens in a spawned child carrying a CPU limit and an address-space
limit, with a wall-clock reclaim behind both. A model that loops forever is killed
(`execution_timeout`, 504); one that allocates without bound gets a `MemoryError`
reported home as a refusal (`execution_limit`, 507) rather than as an outage.

The CPU budget comes from the warrant's `constraints.resources`. The memory
budget is read from there too when present — but MAYA-issued warrants do not
currently emit one, so in practice the default of **2048 MB** applies. Worth
knowing before you conclude that a memory limit you set in a warrant was ignored.

Two further details are deliberate, and both were found by making the tests fail.
The runtime's own dependencies are imported **before** the limit is applied: the
warrant author budgeted for the model, not for the cost of importing a scoring
library, and charging the library's footprint to the model's budget made a
perfectly ordinary artifact fail as though it were greedy. And the memory limit
is **additive to the interpreter's current footprint** rather than absolute, for
the same reason.

The boundary is stated rather than implied. This isolation protects against a
runaway loop, an allocation storm, and a hard crash that would otherwise take the
platform with it. It does not protect against:

> A hostile artifact. A child process shares the filesystem, the network and the
> user. Real isolation for untrusted code is a container or a virtual machine.

Runtimes bound as callables cannot be isolated at all — they are functions the
host registered — and the engine names them as running in process rather than
quietly treating them as protected.

### Valuations, and the date that changes the answer

Most of what a bank runs is not a learned model. It is a valuation: a discount
factor, a zero or forward rate, a fixed bond, a vanilla swap, a swaption. The
captive engine prices those six through QuantLib.

These models are **T0** — the parameter object is terminal, the constants come
from theory, and law **L-W1** refuses to warrant one for fitting. That refusal is
the trainability class working, not a limitation.

They have something the learned models do not: an as-of date that changes the
answer. So this runtime does two things the others do not have to.

**It takes the evaluation date from the warrant, never from the clock.** A
valuation that reads today's date is not reproducible tomorrow, and a backtest of
it is a backtest of nothing. A warrant that does not say when is refused with
`no_evaluation_date` rather than defaulted to now — the default would be the
wrong answer that looks right.

**It builds the curve from what the warrant carries, and nothing else.** Reaching
for a market data service would put an unversioned input into a governed
computation, which is the whole failure the platform exists to make visible.

```json
{"binding": "market_data", "as_of": "2026-01-01", "day_count": "actual/365",
 "curve":    [{"date": "2026-01-01", "rate": 0.030},
              {"date": "2031-01-01", "rate": 0.036}],
 "fixings":  [{"date": "2025-12-31", "rate": 0.031}]}
```

The fixings are there for the same reason. A swap whose first floating period
began before the evaluation date needs that fixing, and it is an input like any
other:

> **`missing_fixing`** — the instrument needs a past fixing the warrant does not
> carry. *Supply fixings alongside the curve; a valuation that invented one would
> put an unversioned number into a governed computation.*

Writing this runtime turned up a hazard worth naming: QuantLib keeps its fixing
history in a **process-global** manager, so a fixing supplied by one warrant would
still be sitting there for the next valuation — the unversioned input arriving
through the back door. Each valuation now starts from an empty history and sees
only what its own warrant carries.

Everything else it will not do, it refuses by name: `instrument_unsupported`,
`pricing_engine_unsupported`, `unknown_day_count`, `no_curve`, `no_volatility`,
`malformed_curve`, `malformed_date`, `malformed_fixing`. Each named rather than
substituted, because a day count silently swapped moves every cash flow and an
engine silently swapped produces a number nobody can reconcile. It knows three
pricing engines and four day counts, and its floating index is Euribor 6M.

It is not sandboxed, and the reason is stated rather than left to be inferred: it
loads no artifact — the instrument and the curve arrive in the warrant — so there
is nothing untrusted to isolate from, and a process spawn per valuation would buy
nothing.

### What it is still not

There is no container runtime, no SAS, R or MATLAB bridge, no rules engine and no
solver. Running a real estate means a real engine — one with the runtimes, the
isolation and the capacity your models actually need. The point of the captive
engine is that a fresh deployment demonstrates the whole governed path end to end
— pricing, scoring, and a fit that produces a real point of `P` — without anyone
building that first.

## Writing your own engine

The contract is the warrant document and the checks above. An engine needs:

- **A signature verifier** sharing the signing key with MAYA.
- **A revocation cache**, refreshed often enough that the floor means something.
  Warrants carry the epoch they were minted under, so a cached epoch behind the
  current one tells the engine its view is stale.
- **A boundary checker** reading `constraints` from the warrant.
- **A digest check** comparing the loaded artifact against `realisation`.
- **Runtimes** for the model families you actually run.

What it does **not** need is any access to MAYA's database, and it should not have
any. If your engine needs to query the registry to do its job, something that
should have been in the warrant is missing — and that is a bug in the warrant, not
a reason to widen the engine's reach.

## Worked examples

Thirteen worked examples in `examples/warrants/`, spanning QuantLib pricing and
calibration, gradient boosting scored and refitted, a PMML regression scorecard,
an LLM summariser, an agent with a tool graph, a vendor black box, a spreadsheet,
a VaR backtest, a vanilla swap the captive engine actually prices, and the two
halves of the New Jersey home-price cycle — fitted from a featureset, then scored
on the parameter set that came back.

Each carries a `_comment` explaining what it demonstrates, and a test asserts that
every one validates and that between them they exercise every axis.

See [warrants by model family](/tutorials/warrants-and-training) for the walkthrough,
and [every kind of model, worked](/tutorials/defining-a-model) for seven
complete paths, one per family.
