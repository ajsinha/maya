---
title: Authoring a rule set, end to end
slug: rule-sets-end-to-end
section: Worked models
order: 55
icon: list-check
summary: The one place MAYA lets you author a model, and the argument for why that is not a breach of its own boundary. A T8 rule set from an empty editor to an approved parameter set an engine runs — with the four questions a structure makes answerable and a JSON blob does not, including the one no spreadsheet will ever ask you.
audience: Model developers, Model owners, Model risk managers, Validators
---

# Authoring a rule set, end to end

Every other tutorial here takes delivery of a model somebody built elsewhere.
This one is different, and the difference needs justifying before we start.

[MAYA does not train models and does not run them](/help/what-is-maya). An
authoring surface looks like a straight breach of that, and the objection is a
good one: if the platform authors the model, then the developer and the control
plane are the same system, and an examiner asking *"who checked this?"* gets the
answer *"the tool that wrote it."*

So be precise about what is being claimed. **MAYA does not become the authoring
tool. It becomes an editor for a parameter set it already held.**

A T8 rule set was always `P` in the register — `parameter_kind: rule_set`,
`fit_procedure: author`, `provenance: declared`, meaning *"asserted by a person,
and attested rather than fitted"*. It was versioned. It was digested. It was
approved by somebody other than its author. What existed was the **governed
object**. What did not exist was any way to type into it except a raw JSON body,
and any way at all for the platform to say one thing about what the rules meant.

That is the gap this closes, and it closes it without inventing an authority:
publishing here is `POST /parameters` reached through a door that reads the
document first.

> **Why not an ONNX or PMML editor, then?** Because those serialize a *fitted*
> map. Authoring one by hand would let MAYA mint an artifact that has never been
> trained or validated by anything and is indistinguishable in the register from
> one that was. A rule set has no training run to be indistinguishable from —
> **authorship is its provenance**, which is exactly what `declared` means.

---

## 0 · What we are building

A retail mortgage eligibility policy. Three rules, in order, first match wins.
It is deliberately small, because everything interesting here is what the
platform can *say* about it rather than how big it is.

You will need `model_developer` to publish and anybody with `model:read` to
check. Port 5006 throughout.

---

## 1 · Register the model, and let the class derive

```bash
curl -su j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' -d '{
    "urn": "maya://model/credit.eligibility.retail",
    "name": "Retail mortgage eligibility",
    "model_class": "credit", "domain": "retail",
    "owner": "person/j.okafor", "legal_entity": "LE-UK-01",
    "purpose": "origination eligibility screening"}'
```

Then the version. Two fields decide everything that follows:

```bash
curl -su d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/credit.eligibility.retail/versions \
  -H 'Content-Type: application/json' -d '{
    "semver": "1.0.0",
    "kernel": {
      "parameter_kind": "rule_set",
      "fit_procedure": "author",
      "runtime": "rules",
      "entry": {"ruleset": "eligibility", "engine": "maya"},
      "input_schema": [
        {"name": "ltv",      "dtype": "numeric"},
        {"name": "dti",      "dtype": "numeric"},
        {"name": "product",  "dtype": "categorical"},
        {"name": "arrears",  "dtype": "integer"}],
      "output_schema": [{"name": "decision", "dtype": "string"}]}}'
```

```json
{"semver": "1.0.0", "trainability_class": "T8", "status": "draft", ...}
```

**Nobody typed `T8`.** `parameter_kind: rule_set` plus `fit_procedure: author`
derives it, in `core/domain/algebra.py`, and the class then decides which verbs a
warrant may ask for and — since the fibration was closed — what evidence this
model needs and what may be monitored on it. Ask for its fibre:

```bash
curl -su d.raman:dev-pw localhost:5006/api/v1/fibres/T8
```

```json
{"trainability_class": "T8", "label": "Deterministic rule",
 "evidence":  ["model_development_document", "validation_report"],
 "lifecycle": ["draft", "baselined", "submitted", "approved", "attested",
               "amending", "retired"],
 "metrics":   ["input_drift", "score_drift"],
 "templates": ["model_development_document", "validation_report",
               "model_card", "annex_iv"],
 "soundness_rests_on": "the rule read against the policy it implements",
 "outcomes_analysis_is": "above-the-line and below-the-line testing",
 "monitoring_answers": "rule-fire distribution and exception rate"}
```

Note what is **absent**: `calibration` is not a monitor kind you can define on
this model. There is nothing fitted to be calibrated, and a calibration monitor
here would run forever producing a number about nothing.

**The `input_schema` is the important half.** Every field a rule reads is checked
against it, using the same `refines` order that decides featureset satisfaction
and typed composition. A rule reading `income` on this model is refused by name
rather than silently never firing.

---

## 2 · The editor, and the shape of a rule

Open `/rules/credit.eligibility.retail/1.0.0`. Or work by API — they are the
same three endpoints, and the screen decides nothing that the server does not.

A rule has four parts and all four are required:

```json
{"id":      "btl_high_ltv",
 "when":    {"all": [{"field": "product", "op": "eq", "value": "BTL"},
                     {"field": "ltv",     "op": "gt", "value": 0.75}]},
 "then":    {"decision": "refer"},
 "because": "BTL above 75% LTV is outside appetite (CP-2024-11)"}
```

### `because` is required, and it is the field you will want to skip

A rule with no stated reason cannot be defended to a supervisor, cannot be
reviewed by whoever owns the policy, and — the one that actually bites —
**cannot be retired by anybody later, because nobody knows what it was for.**
Every bank has rules in production that nobody dares remove. This is the field
that prevents the next one.

It is also, precisely, the difference between a rule set and a stored procedure.

### Conditions are structured, not written

There is no arithmetic and no free text. A condition is a field test, or an
`all` / `any` / `not` of conditions, and nothing else:

```
{"field": "ltv", "op": "gt", "value": 0.8}
{"all": [ ... ]}   {"any": [ ... ]}   {"not": { ... }}
```

Eleven operators, from `GET /api/v1/rulesets/vocabulary`: `eq ne lt le gt ge in
not_in between is_null not_null`.

**This is the design decision the whole tutorial turns on**, so it is worth being
blunt about the alternative. MAYA already has a whitelisted expression language —
[derived features](/tutorials/features-end-to-end) use it — and reusing it here
would have been half a day's work. It is the wrong answer, because *a free
expression is opaque to analysis.*

Whether a rule can ever fire, whether two rules contradict each other, whether
any input falls through: none of those questions can be answered about
`x * 0.3 + y > threshold`, and all of them can be answered about a tree of
`field op value`. The entire argument for holding rule sets in a governance
platform is that they are the one kind of model a non-programmer can review and
the platform can reason about. Give that up for expressiveness and you have
built a worse spreadsheet.

A rule needing arithmetic needs a [derived feature](/help/features-and-two-clocks)
— the same boundary MAYA draws everywhere: the platform transforms what it holds
and does not compute new quantities inside a governed object.

---

## 3 · Check it, and watch four questions get answered

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/rulesets/check \
  -H 'Content-Type: application/json' -d '{
    "urn": "maya://model/credit.eligibility.retail", "semver": "1.0.0",
    "document": {
      "rules": [
        {"id": "btl_high_ltv",
         "when": {"all": [{"field": "product", "op": "eq", "value": "BTL"},
                          {"field": "ltv", "op": "gt", "value": 0.75}]},
         "then": {"decision": "refer"},
         "because": "BTL above 75% LTV is outside appetite (CP-2024-11)"},
        {"id": "recent_arrears",
         "when": {"field": "arrears", "op": "ge", "value": 1},
         "then": {"decision": "decline"},
         "because": "Any arrears in 24 months is a hard decline (CP-2024-03)"},
        {"id": "very_high_ltv",
         "when": {"field": "ltv", "op": "gt", "value": 0.95},
         "then": {"decision": "decline"},
         "because": "Above 95% LTV needs a capital add-on we do not hold"}],
      "otherwise": {"decision": "accept"},
      "note": "Retail mortgage eligibility, Q1 2026"}}'
```

```json
{"rules": 3,
 "fields": ["arrears", "ltv", "product"],
 "shadowed": [], "contradictions": [],
 "reads": ["arrears", "ltv", "product"],
 "explanation": [
   "1. when product is equal to BTL and ltv is greater than 0.75, then decision = refer  — BTL above 75% LTV is outside appetite (CP-2024-11)",
   "2. when arrears is at least 1, then decision = decline  — Any arrears in 24 months is a hard decline (CP-2024-03)",
   "3. when ltv is greater than 0.95, then decision = decline  — Above 95% LTV needs a capital add-on we do not hold",
   "otherwise, decision = accept"]}
```

`check` **records nothing**. It needs `model:read`, not `parameter:record` —
requiring the recording permission to *look* at whether a draft is valid would
push authors to skip the step, and a control people route around is worse than
one they never had, because it also reports success.

The `explanation` is the point of the response. It is generated from the parsed
form, so the sentences on the screen, in the model card, in the committee paper
and in the export pack are **one rendering** rather than four — and the
differences between four renderings are exactly where a misreading survives.

### The four questions

| | The question | How it is answered |
|---|---|---|
| **Totality** | does every input have an outcome? | `otherwise` is required. By construction, not by analysis |
| **Reachability** | can each rule ever fire? | domain analysis over the conditions |
| **Contradiction** | do two rules disagree? | identical condition, different outcome |
| **Conformance** | does every field exist, at a usable type? | `refines`, against the version's `input_schema` |

---

## 4 · The refusals, which are the reason to be here

Six worth meeting. Each is a real thing that happens in real rule sets.

### The rule that can never fire

Put a broad rule first and a narrow one after it:

```json
{"rules": [
  {"id": "any_high_ltv", "when": {"field": "ltv", "op": "gt", "value": 0.5},
   "then": {"decision": "refer"}, "because": "..."},
  {"id": "btl_high_ltv", "when": {"all": [{"field": "product", "op": "eq", "value": "BTL"},
                                          {"field": "ltv", "op": "gt", "value": 0.75}]},
   "then": {"decision": "decline"}, "because": "..."}],
 "otherwise": {"decision": "accept"}}
```

```
422 rule_unreachable — rule 'btl_high_ltv' can never fire: rule 'any_high_ltv'
comes first and matches everything it matches
   → reorder them, narrow the earlier rule, or delete this one. A rule that never
     fires still appears in the model card and in every committee paper, and
     nobody reading either can tell
```

**This is the one no spreadsheet will ever tell you**, and it is the single best
argument for holding rule sets in a governance platform at all.

Think about what an unreachable rule does. It never fires, so it never produces a
wrong answer, so it never causes an incident, so nothing ever draws attention to
it. It survives every review. It appears in the documentation. Somebody in the
business believes that policy is in force — and it is not. A rule set with one of
these is *lying about the bank's own policy*, quietly, for years.

Readers of [the adversarial review](/help/evidence-and-provenance) will recognise
the shape: a control that reports success while doing nothing. It turns out that
pattern is not peculiar to platforms. It is what happens to any control nobody
can check, and a rule set is a control.

### Two rules that disagree

```
409 rules_contradict — rules 'a' and 'b' have the same condition and different
outcomes
   → first match wins, so the second can never fire — but the ordering is not the
     problem. Decide which outcome the policy actually means
```

Worth reading that remediation twice. Identical conditions are *also* a
shadowing, so the obvious implementation reports `rule_unreachable` and sends the
author off to fix the ordering. The ordering is not the mistake. Two rules saying
opposite things about identical inputs is a disagreement about the policy, and
somebody has to decide which one is meant.

(The first version of this checker had exactly that bug: the contradiction branch
was unreachable, because shadowing was reported first. In the checker written to
find unreachable rules.)

### The rule that contradicts itself

```json
{"id": "typo", "when": {"all": [{"field": "ltv", "op": "gt", "value": 0.9},
                                {"field": "ltv", "op": "lt", "value": 0.5}]}, ...}
```

```
422 rule_never_fires — rule 'typo' has a condition no input can satisfy:
ltv is greater than 0.9 and ltv is less than 0.5
   → almost always a typo in a bound; fix it, or remove the rule
```

### The field that does not exist

```
422 unknown_field — rule 'income_test' reads 'income', which this model's input
schema does not declare
   → declare it on the version, or read one of: arrears, dti, ltv, product
```

Without this the rule is accepted and **silently never fires** — the worst of the
three available outcomes, and indistinguishable from the unreachable-rule case
from the outside.

### The comparison with no meaning

```
422 unordered_comparison — rule 'x' asks whether 'product' is greater than
something, but it is declared 'categorical', which has no order
   → compare with eq/ne/in/not_in, or declare the field with an ordered type if
     it really is one
```

`product_code > "MTG"` has a defined answer in every programming language and no
meaning in any bank.

### The missing `otherwise`

```
422 otherwise_required — the rule set has no 'otherwise', so it does not say what
happens when no rule matches
   → add 'otherwise'; a rule set without one behaves by accident on exactly the
     cases its author did not think of
```

---

## 5 · What the analysis does *not* do

Here is a rule set the platform accepts and that has an unreachable rule in it:

```json
{"rules": [
  {"id": "high", "when": {"field": "ltv", "op": "gt", "value": 0.8},  ...},
  {"id": "low",  "when": {"field": "ltv", "op": "le", "value": 0.8},  ...},
  {"id": "never", "when": {"field": "ltv", "op": "ge", "value": 0.0}, ...}],
 "otherwise": {"decision": "accept"}}
```

`high` and `low` between them cover every value of `ltv`, so `never` cannot fire.
Neither one covers it *alone*, and the analysis compares one earlier rule at a
time. **It is not detected.**

That is a deliberate limit, not an oversight, and the shape of the trade is worth
seeing:

- The analysis is **sound**: when it reports a rule unreachable, the rule *is*
  unreachable. It never cries wolf — because a check that produces false alarms
  is a check somebody turns off, and the real ones go with it.
- The analysis is **incomplete**: it catches shadowing by any *single* earlier
  rule. Full coverage is satisfiability over the whole set, which is decidable
  here but is a **solver** — and a solver inside a governance platform is a
  dependency whose failure modes nobody in the bank can debug at four in the
  afternoon before a submission.

So the platform promises exactly *"no rule is shadowed by any single earlier
rule"*, and the screen says that rather than "no rule is unreachable". A control
that claims more than it delivers is the thing this whole analysis exists to
find; it would be a poor joke to build one here.

---

## 6 · Try it before anybody approves it

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/rulesets/trial \
  -H 'Content-Type: application/json' -d '{
    "urn": "maya://model/credit.eligibility.retail", "semver": "1.0.0",
    "document": { ... as above ... },
    "rows": [{"product":"BTL","ltv":0.80,"arrears":0},
             {"product":"RESI","ltv":0.97,"arrears":0},
             {"product":"RESI","ltv":0.60,"arrears":2},
             {"product":"RESI","ltv":0.55,"arrears":0}]}'
```

```json
{"outcomes": [
   {"row": 0, "decision": "refer",   "matched_rule": "btl_high_ltv",   "because": "BTL above 75% ..."},
   {"row": 1, "decision": "decline", "matched_rule": "very_high_ltv",  "because": "Above 95% LTV ..."},
   {"row": 2, "decision": "decline", "matched_rule": "recent_arrears", "because": "Any arrears ..."},
   {"row": 3, "decision": "accept",  "matched_rule": null,             "because": "no rule matched; the stated otherwise applies"}],
 "fired": {"btl_high_ltv": 1, "recent_arrears": 1, "very_high_ltv": 1},
 "never_fired": [],
 "fell_through": 1}
```

Two things to notice.

**`trial` is not `/execute`.** There is no warrant, no entitlement and no
decision — an author is reading their own draft back. Routing it through the
execution path would have meant inventing an authority for a convenience, and an
authority invented for a convenience is the kind that turns up later attached to
something else.

**`never_fired` is the report worth reading.** A rule that fires on none of your
sample rows is not necessarily wrong; your sample may just be thin. But a rule
set where most rules fire on nothing is one somebody should look at before it is
approved, and this is the only moment anybody will.

A row that cannot be decided is reported against that row rather than raised:

```json
{"row": 0, "refused": "value_not_comparable",
 "detail": "'ltv' arrived as str ('high') and the rule compares it with 0.75"}
```

One bad sample must not hide what the other nineteen would have shown. And note
that a type mismatch **refuses** rather than guessing — Python would compare two
strings lexically and return something entirely plausible, which is a defect, not
a rule outcome.

---

## 7 · Publish, and meet the part that has not changed

```bash
curl -su d.raman:dev-pw -X POST localhost:5006/api/v1/rulesets \
  -H 'Content-Type: application/json' -d '{
    "urn": "maya://model/credit.eligibility.retail", "semver": "1.0.0",
    "name": "eligibility-2026q1",
    "document": { ... },
    "note": "Q1 2026 policy refresh: arrears rule tightened to any-in-24-months"}'
```

```json
{"id": "01a0...", "name": "eligibility-2026q1", "kind": "rule_set",
 "provenance": "declared", "state": "proposed",
 "diagnostics": {"rules": 3, "reads": ["arrears","ltv","product"],
                 "shadowed": [], "contradictions": []}}
```

**`state: proposed`.** Now try approving your own work:

```bash
curl -su d.raman:dev-pw -X POST \
  localhost:5006/api/v1/parameter-sets/01a0.../review \
  -H 'Content-Type: application/json' -d '{"accept": true}'
```

```
403 forbidden — 'parameter:approve' is not granted by your roles
(model_developer)
   → ask an administrator for a role that carries this permission
```

Not the refusal you might have expected, and the reason is worth a minute.

**The separation is enforced twice, and by two different things.** Look at who
holds what:

| Role | `parameter:record` | `parameter:approve` |
|---|---|---|
| `model_developer` | yes | — |
| `model_owner` | yes | — |
| `validator` | — | yes |
| `model_risk_manager` | — | yes |
| `admin` | **yes** | **yes** |

**No ordinary role holds both.** So for every real persona the *role* separation
bites first, and `self_approval` never gets a chance to fire — which raises the
obvious question of why it exists at all.

It exists for the row at the bottom. An administrator holds both, and without a
person-level check an administrator could author a lending policy and approve it
alone:

```bash
curl -su admin:admin123 -X POST \
  localhost:5006/api/v1/parameter-sets/01a0.../review \
  -H 'Content-Type: application/json' -d '{"accept": true}'
```

```
403 self_approval — admin recorded these parameters and cannot also approve them
   → a parameter set changes what the model does; approval is by somebody other
     than whoever produced it
```

Two controls, one behind the other, and the second is not redundant: it is what
covers the exception the first one has. A design with only the role check would
look complete right up until somebody used the account that exists to do
everything.

Neither refusal is in `core/rules/` anywhere. Both are the parameter register's,
untouched, because publishing a rule set **is** recording a parameter set. Every
property that made a fitted coefficient set trustworthy applies here unchanged:
the digest over the content, the second reviewer, the immutability, the evidence
node. This is the whole argument of §0, made concrete — the editor edits a
governed object; it never mints one.

So it takes a validator:

```bash
curl -su a.mehta:val-pw -X POST \
  localhost:5006/api/v1/parameter-sets/01a0.../review \
  -H 'Content-Type: application/json' -d '{"accept": true, "note": "Q1 policy read against CP-2024-11"}'
```

```json
{"state": "approved", "approved_by": "a.mehta", ...}
```

One endpoint for accept and reject, taking `accept` rather than two verbs: a
review is one act with two outcomes, and splitting it into two endpoints makes
"reviewed" something you have to reconstruct from which door somebody used.

The canonical form is worth one paragraph. The digest is taken over the
**parsed** document, so reformatting your JSON does not produce a new parameter
set — but **reordering the rules does**, because with first-match evaluation the
order *is* the meaning.

---

## 8 · Run it

The `rules` runtime has been named by the grammar since the first milestone and
implemented by nothing. So until now a rule set could be registered, versioned,
approved and attested — and still be *scored* by whatever stored procedure the
bank was already using. The governed artefact and the executing artefact were two
documents nobody compared, which is the arrangement this platform exists to end.

Four steps first, in this order, and the order matters:

```bash
# 1. Assess — AFTER the version exists. Complexity is read off the latest
#    version's derived class, so assessing an empty model tiers it as T0.
curl -su s.iqbal:mrm-pw -X POST \
  localhost:5006/api/v1/models/credit.eligibility.retail/assess \
  -H 'Content-Type: application/json' -d '{}'

# 2. Approve the version. How many signatures depends on the tier the
#    assessment produced — the refusal names what is still needed.
curl -su s.iqbal:mrm-pw -X POST \
  localhost:5006/api/v1/models/credit.eligibility.retail/versions/1.0.0/approve \
  -H 'Content-Type: application/json' -d '{}'

# 3. Point the environment's alias at it.
curl -su s.iqbal:mrm-pw -X PUT \
  localhost:5006/api/v1/models/credit.eligibility.retail/aliases \
  -H 'Content-Type: application/json' \
  -d '{"environment":"prod","alias":"champion","semver":"1.0.0"}'

# 4. A standing grant. Without one, /execute is refused `no_entitlement` —
#    an approved model is not thereby an entitled one.
curl -su s.iqbal:mrm-pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' -d '{
    "urn": "maya://model/credit.eligibility.retail", "environment": "prod",
    "principal": "svc/origination", "declared_use": "origination_decision"}'
```

Then score:

```bash
curl -su svc/origination:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' -d '{
    "urn": "maya://model/credit.eligibility.retail#champion",
    "environment": "prod", "principal": "svc/origination",
    "declared_use": "origination_decision",
    "inputs": {"product": "BTL", "ltv": 0.80, "arrears": 0, "dti": 0.35}}'
```

```json
{"descriptor_id": "01a0729a657e7201f109f5f2ca15",
 "model_urn": "maya://model/credit.eligibility.retail",
 "version": "1.0.0",
 "prediction": {"decision": "refer",
                "matched_rule": "btl_high_ltv",
                "because": "BTL above 75% LTV is outside appetite (CP-2024-11)"},
 "boundary_ok": true, "boundary_violations": [], "latency_ms": 1.56}
```

### `matched_rule` is not diagnostics

It travels even when the output schema does not declare it, and that is
deliberate. **A decision a bank cannot attribute to a rule is a decision it
cannot explain to the person it refused** — and under most consumer-credit
regimes the explanation is the obligation, not the outcome. A system that can
tell you *what* it decided but not *why* has met none of it.

### Where the rules came from

The runtime does not read a file. `CaptiveEngine._parameters` resolves the
**approved** parameter set, re-derives its digest, and hands the values over — so
running a rule set at an unapproved point of `P` is refused by the same mechanism
that refuses running a scorecard at unapproved coefficients. Edit the values
underneath an approval and:

```
409 parameter_mismatch — the parameter set does not match the digest in the
warrant, so the numbers about to run are not the numbers that were approved
```

One consequence worth stating: `rules` is deliberately **absent** from
`UNVERIFIABLE_DETERMINISM`, so [L-W5](/help/warrants) does not demand a seed.
MAYA holds the rule set, reads it, and can verify a determinism claim by
executing it — which is stronger evidence than a seed, and the same reason the
captive estimator is exempt.

---

## 9 · What this changed, and what it did not

**Changed.** T8 was the least-served class in the register and is now the
best-served: the only one whose parameter object the platform can read, explain,
check for internal contradiction, and run. That is not because rule sets matter
more than neural networks. It is because a rule set is *small enough to be
reviewed*, and everything above follows from taking that seriously.

**Not changed.** The register still holds it as a parameter set. Approval still
needs two people. The warrant still binds a digest. Nothing about the governance
of a rule set is special, and the moment it became special would be the moment to
stop.

**Not built.** No `entry_points` discovery, so a bank's own operators ship inside
this repository. No rendering to PMML — a T2 scorecard is the case where that
would earn its keep, and it is not here. And the coverage analysis is
single-rule, which §5 says plainly rather than leaving you to discover.

---

## Where next

- [Every kind of model](/tutorials/every-kind-of-model) — the decision procedure
  that made this model T8 without anybody typing it
- [Warrants by family](/tutorials/warrants-by-family) — why one document covers
  a rule set and a transformer
- [Featuresets and parameters](/help/featuresets-and-parameters) — the register
  this editor writes into
- [The whole path](/tutorials/the-whole-path) — every subsystem, one example

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE.
*Not legal, regulatory or financial advice — see NOTICE §4.*
