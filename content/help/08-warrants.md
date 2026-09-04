---
title: Warrants and execution
slug: warrants
section: Execution
order: 80
icon: key
summary: The signed, expiring, entitlement-bound document an execution engine acts on — its four-axis grammar and admissibility laws, what resolution refuses and why, and what an engine must check before it touches an artifact.
audience: Engineers, Model risk, Quants
---

# Warrants and execution

A **warrant** is a signed instrument authorising a named principal to perform a
stated operation on a stated model version, within limits, until a stated
moment, revocable at will. It is the entire interface between MAYA and whatever
runs your models.

It used to be called a hook. That name suggested a callback, which is the wrong
mental model: nothing calls back, and the document is not a piece of plumbing. It
is an authorisation, and calling it one makes the semantics obvious.

This page covers the three things you need in order: what a warrant is and what
issuing one refuses, how the document is structured and which combinations of
its parts mean anything, and what an engine must do with one.

## Why the boundary exists

**MAYA does not execute models.** It issues warrants; an execution engine acts on
them. Keeping issuance and execution apart means the control plane can be
unavailable for a minute without the bank stopping, and it means an execution
engine can be replaced without renegotiating governance — see
[What MAYA is](/help/what-is-maya#what-maya-does-not-do) for why a governance
platform that is also the runtime is the version of this that gets bypassed.

## Grants and warrants are different things

A **grant** is the standing entitlement: this principal, in this environment, for
this declared use.

```bash
POST /api/v1/warrants
{
  "urn": "maya://model/credit.pd.smallbiz#champion",
  "environment": "prod",
  "principal": "svc/origination",
  "declared_use": "origination_decision"
}
```

A **warrant** is the short-lived credential minted against a grant, at the moment
of use:

```bash
POST /api/v1/resolve
{ ...the same four fields... }
```

Separating them is what makes revocation meaningful. Withdrawing the grant stops
future warrants; bumping the revocation epoch invalidates the ones already out.

## What resolution checks, in order

1. **Is the model registered?** → `404 not_found`
2. **Is anything blocking?** → `423 blocked` — see [Findings](/help/validation#findings)
3. **Does this principal hold a grant here?** → `403 no_entitlement`
4. **Has the grant been withdrawn?** → `410 revoked`
5. **Is the declared use the approved use?** → `403 use_not_approved`
6. **Is anything bound for this URN in this environment?** → `404 not_found`
7. **Is that version approved?** → `423 restricted`

The order matters. Revocation is checked before the use comparison, because a
withdrawn warrant is withdrawn whatever the caller claims to be doing with it.

Note what is *not* in that list: the model's lifecycle state. A `baselined` model
resolves normally, which is what *"existing use is not blocked, change is"*
means in the code path rather than in a slogan.

Every refusal carries a reason and a remediation. Resolution **fails closed**:
there is no path that degrades quietly into something that looks like it worked.

## The URN is all a consumer holds

A consumer holds a [URN](/help/registering-a-model#the-urn) — bare, pinned with
`@3.2.1`, or aliased with `#challenger` — and nothing else. Artifact location,
schemas, boundaries and policy are resolved at runtime from it. That is exactly
what lets a governed version move happen without a consumer redeploying, and what
makes the alias move the most tightly controlled operation in the platform.

## The ten sections

A warrant has to describe a Black–Scholes closed form, a Hull–White calibration,
a gradient-boosted PD model, a logistic scorecard, a prompt bundle, an agent with
tools, a credit policy rulebook, a spreadsheet and a vendor black box — and it
has to do it without becoming a union of special cases, because a union of
special cases is a format that breaks the first time somebody brings a model
nobody anticipated.

So it is ten sections, each answering exactly one question, under three
top-level fields that identify the document itself.

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

An absent section is not an empty one: all ten are required, and a missing one is
reported by name — *every warrant carries all ten sections; an absent one is not
an empty one*. `maya_warrant` is checked separately, as a grammar version.

Three of them carry more than their one-line description suggests.
**Constraints** holds the operating boundary from the version's contract, which
is what lets an engine refuse *before* touching the artifact, alongside resource
limits. **Governance** holds the tier and the model and version status at the
moment of resolution, so what an engine acted on can be reconstructed later even
if the model has moved on since. **Signature** is HMAC-SHA256 over the canonical
form, with the signature block excluded rather than blanked.

## The four axes

Every model a bank runs differs along exactly four **independent** axes:

| Axis | Field | Vocabulary |
|---|---|---|
| How the parameter object is inhabited | `parameters.kind` | eight values: none, calibration_set, estimated_coefficients, learned_weights, llm_configuration, rule_set, elicited_weights, opaque |
| How the kernel becomes runnable | `realisation.runtime` | seventeen: quantlib, onnx, pmml, python.callable, container, sql, spreadsheet, rules, solver, llm.prompt, llm.agent, sas, r, matlab, rest, pfa, descriptor_only |
| What is being asked of it | `operation.verb` | ten: score, fit, validate, backtest, explain, simulate, stress, optimise, generate, monitor |
| Where its data comes from | `data.*.binding` | twelve: request, inline, feature_namespace, featureset, dataset_snapshot, delta_table, sql_query, stream, market_data, document_corpus, scenario_set, artifact |

Two further closed vocabularies sit alongside them: where an output may go
(`sink`) and where a parameter object may come from (`parameters.source`).

The grammar is the **product** of those four, not their union. A QuantLib pricer
is `(none, quantlib, score, market_data)`. The Hull–White calibration behind it
is `(calibration_set, quantlib, fit, market_data)` — same runtime, three
different coordinates. An XGBoost PD model is
`(learned_weights, onnx, score, feature_namespace)`. An LLM summariser is
`(llm_configuration, llm.prompt, generate, document_corpus)`.

One structure. Different coordinates.

And it extends the right way: a new model technology is a new **value** in one
vocabulary — almost always a runtime — not a new section, not a new document
type, and not a change to anything that already works.

## The admissibility laws

A warrant can be well-formed and still be nonsense. These are the rules that make
such a document a refusal rather than a runtime failure — and the important ones
are not invented, they fall out of the algebra already in the platform.

Shape and vocabulary violations — an unknown verb, a missing section, a binding
with no key — are reported as **L-W0**. The rest are admissibility:

**L-W1 — you cannot fit what has nothing to fit.** The trainability class is
*derived* from how the parameter object is inhabited, and T0 (parameters from
theory) and T6 (parameters inside a vendor black box) are precisely the classes
for which fitting is a type error.

```json
{"law": "L-W1", "path": "operation.verb",
 "detail": "a T0 model cannot be fitted: its parameters come from theory, not
            from data — there is nothing to fit",
 "remediation": "ask for 'score', 'validate' or 'explain'; if this model really
                 is fitted, its parameter_kind and fit_procedure are wrong"}
```

**L-W2 — `generate` needs a generative runtime.** An ONNX graph does not produce
prose.

**L-W3 — training data must be readable as-of.** A training set assembled from a
source with no transaction time cannot be shown point-in-time correct, so it
cannot be shown not to have leaked. Three bindings qualify: `dataset_snapshot`,
`feature_namespace` and `featureset`.

**L-W4 — a `fit` must say where its parameters go.** It produces a *new*
parameter object rather than editing the old one, so it needs an output whose
sink is `parameter_object`.

**L-W5 — claimed determinism must be pinned.** An LLM at temperature 0.7 is not
reproducible, and a warrant asserting that it is will be believed by whatever
reads the result. Claim determinism from a stochastic runtime and you must
supply a seed.

**L-W6 — a descriptor-only model cannot be fitted.** Descriptor-only is a
legitimate state: the bank holds the licence, the engine holds the artifact, MAYA
holds the governance. What it cannot carry is an instruction to inhabit a
parameter object nothing on this side can reach.

**L-W7 — a backtest needs outcomes.** Otherwise it is a re-score wearing a
backtest's name.

**L-W8 — a run must name which point in P it runs at.** A warrant that names a
kernel and leaves its parameters implicit describes a result nobody can
reproduce.

**L-W9 — a featureset read for fitting must be bounded in both clocks.** An
`as_of`, and a window with a start and an end. This is L-W3 made specific for the
binding that carries a whole training set.

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

Validation reports every problem it can see **at the stage it got to**: all the
shape errors together, and then, only if the shape is clean, all the
admissibility failures together. Whoever is writing a warrant by hand wants the
whole list, and fixing one error to be told about the next is the worst possible
interface for a document with ten sections. What it will not do is guess at
admissibility for a document whose sections are missing.

MAYA validates every warrant **before signing it**, never after. A signature over
a non-conforming document would be an assurance that the document is authentic
and not that it is usable, and engines would reasonably read it as both. So an
engine that trusts the signature can also trust the shape.

## Expiry, grace and the revocation floor

TTL and grace are keyed by risk tier:

```yaml
warrants:
  ttl_seconds:   {1: 60, 2: 300, 3: 3600, 4: 3600}
  grace_seconds: {1: 0,  2: 0,   3: 900,  4: 900}
  jitter_pct: 20
```

A Tier 1 model gets sixty seconds and **zero grace**: it must never run on stale
authorisation. Tier 3 and 4 get grace so a transient control-plane outage does
not stop the business.

**Jitter** spreads expiry across a band, and is capped at 50% however it is
configured. Without it, a fleet issued warrants at deploy time expires in
lockstep and stampedes the resolver at the worst possible moment — synchronised
expiry was part of adversarial finding **H-1**.

**The revocation floor** is the rule that grace never overrides: a warrant on the
local revocation list is refused regardless of grace state. Grace extends how
long an *authorisation* stays current when the platform is unreachable; it never
extends how long a consumer may stay ignorant of a withdrawal it has already been
told about. This was **finding C-1**.

## Revocation

```bash
POST /api/v1/warrants/revoke
{"urn": "maya://model/credit.pd.smallbiz", "reason": "Suspected leakage"}
```

The kill switch: every grant on the model is withdrawn and the revocation epoch
is bumped, so warrants already in flight can be recognised as stale by any engine
that checks. Warrants carry the epoch they were minted under, and the section
that carries it says the check is required.

## What an engine must check, in order

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

MAYA ships one engine — the **captive engine** — but it is a reference consumer
of the public contract, not a privileged component.

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

It resolves a warrant through the same public path an external engine uses, then
performs the five checks above.

Structurally, it holds no direct reference to the registry or the feature store —
there is a test asserting exactly that, because the boundary is only real if it
is enforced by construction rather than by intention. What it holds is the
warrant service, and through it the public contract; the moment a bundled engine
can reach past that contract, the contract stops describing what actually
happens.

Switch it off with one key:

```yaml
execution:
  captive:
    enabled: false
```

Nothing else changes, and the endpoint reports that no captive engine is
configured. External engines are unaffected, because they were never using it.

### What it implements

**Three runtime implementations, answering for four of the grammar's seventeen
runtime values**, and it is precise about which:

| Runtime value | What it does |
|---|---|
| `python.callable` | a callable bound to a version in process, for development |
| `descriptor_only` | answered by the same implementation, and the *correct* case for it — MAYA holds the governance, the engine supplies the model |
| `onnx` | loads and runs an ONNX graph through onnxruntime |
| `pmml` | evaluates the `RegressionModel` and `Scorecard` subset **natively, without a JVM** |

A warrant naming a runtime it does not implement is refused **by name** — not by
failing three layers down inside an artifact loader. The refusal distinguishes
two cases that need different actions: a runtime this engine never implemented
(`no_runtime` — route the warrant elsewhere) and one it implements whose
dependency is missing (`runtime_unavailable` — install the package, and the
message names it).

`GET /api/v1/engine` serves the engine's own description of itself — which
runtimes it implements, and exactly what its isolation does and does not cover.
An engine that runs artifacts owes its callers that statement, and a name like
"sandbox" left unexplained implies a guarantee the process model does not
provide. Where the captive engine is disabled the endpoint says so rather than
returning nothing:

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

Anything else is refused by name, and so is anything inside those two elements
that is not implemented: a normalisation method outside `none`, `softmax`,
`logit` and `exp`, or a predicate operator outside the six supported. A partial
implementation that silently mis-evaluates a tree ensemble would be far worse
than one that says it only does regressions.

### The artifact digest is verified before anything runs

```json
{"error": "artifact_mismatch",
 "detail": "sb.pmml does not match the digest in the warrant
            (expected sha256:9f2c1a…, found sha256:4e8a17…)",
 "remediation": "the artifact has changed since it was approved; do not run it
                 and raise a security incident"}
```

The digests in that message are prefixes — enough to tell two artifacts apart at
a glance; the full values go to the log. A warrant that carries no digest at all
is refused separately as `artifact_unverifiable`, because "there was nothing to
check against" and "we checked and it matched" must never look the same.

This is the point at which the whole chain — registry, warrant, signature —
either does or does not describe the bytes about to run. An engine that skips it
makes every link before it decorative.

A version therefore records **both** an `artifact_digest` and an `artifact_uri`.
The digest says *what* should be there; the URI says where to look. A digest with
no location cannot be fetched; a location with no digest cannot be checked.

Artifacts are read from a configured directory and a path resolving outside it is
refused. A warrant is a document from elsewhere, and treating a path inside it as
trustworthy is how a governance system becomes a file-read primitive.

### Isolation, and exactly how far it goes

Artifact-backed runtimes — ONNX and PMML — do not run in the web process. Each
invocation happens in a spawned child process carrying two limits: a CPU limit
and an address-space limit, with a wall-clock reclaim behind both. A model that
loops forever is killed; one that allocates without bound gets a `MemoryError`
reported home as a refusal rather than an outage.

The CPU budget comes from the warrant's `constraints.resources`. The memory
budget is read from there too when present — but MAYA-issued warrants do not
currently emit one, so in practice the default of 2048 MB applies. Worth knowing
before you conclude that a memory limit you set in a warrant was ignored.

Two further details are deliberate, and both were found by making the tests fail.

The runtime's own dependencies are imported **before** the limit is applied. The
warrant author budgeted for the model, not for the cost of importing a scoring
library, and charging the library's footprint to the model's budget made a
perfectly ordinary artifact fail as though it were greedy.

The memory limit is **additive to the interpreter's current footprint** rather
than absolute, for the same reason.

The boundary is stated rather than implied. This isolation protects against a
runaway loop, an allocation storm, and a hard crash that would otherwise take the
platform with it. It does not protect against:

> A hostile artifact. A child process shares the filesystem, the network and the
> user. Real isolation for untrusted code is a container or a virtual machine.

Saying that plainly is better than a name like "sandbox" implying a guarantee the
process model does not provide. Runtimes bound as callables cannot be isolated at
all — they are functions the host registered — and the engine names them as
running in process rather than quietly treating them as protected.

### What it is still not

There is no container runtime and no quantitative library. Running a real estate
means a real engine — one with the runtimes, the isolation and the capacity your
models actually need. The point of the captive engine is that a fresh deployment
demonstrates the whole governed path end to end, against real ONNX and PMML
artifacts, without anyone building that first.

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

## Worked examples

Twelve of them ship in `examples/warrants/`, spanning QuantLib pricing and
calibration, gradient boosting scored and refitted, a regression scorecard, an
LLM summariser, an agent, a vendor black box, a spreadsheet, a VaR backtest, and
the two halves of the New Jersey home-price cycle — fitted from a featureset,
then scored on the parameter set that came back. Each carries a `_comment`
explaining what it demonstrates, and a test asserts that every one of them
validates and that between them they exercise every axis.

See [warrants by model family](/tutorials/warrants-by-family) for the
walkthrough.
