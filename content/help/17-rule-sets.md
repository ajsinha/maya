---
title: Rule sets
slug: rule-sets
section: Features and data
order: 75
icon: list-ol
summary: The parameter object of a T8 model is a rule set somebody wrote, and it used to be an opaque blob. It now has a structure, four checks that are impossible over a free expression, an English rendering, an editor that mints no authority — and a runtime that finally runs it.
audience: Model owners, Policy owners, Model risk, Engineers
---

# Rule sets

A **T8** model is one whose parameter object is a rule set somebody authored:
eligibility criteria, exclusion lists, limit checks, override policy, the band
assignment on the end of a scorecard. In a real bank this is the largest
population by count and the least well governed by anything, because a rule set
is usually a spreadsheet, a stored procedure, or a paragraph in a policy document
that somebody transcribed into code once.

MAYA always held these. A version declaring `parameter_kind: rule_set` and
`fit_procedure: author` derives the class **T8**, its parameter sets carry
`provenance: declared`, and each one is versioned, digested and approved by
somebody other than whoever recorded it. What it held them *as* was an arbitrary
JSON document in `values` — so the platform could tell you the rule set had
changed and not one thing about what it said.

Two things changed that. A rule set has a **structure** the platform can reason
about, and the `rules` runtime — named by the warrant grammar since the first
milestone and implemented by nothing — now runs one.

## What a rule set is

Ordered rules, **first match wins**, and a stated `otherwise`:

```json
{"rules": [
   {"id": "btl_high_ltv",
    "when": {"all": [{"field": "product", "op": "eq", "value": "btl"},
                     {"field": "ltv",     "op": "gt", "value": 0.8}]},
    "then": {"decision": "refer"},
    "because": "BTL above 80% LTV is outside appetite (CP-2024-11)"},
   {"id": "thin_file",
    "when": {"field": "bureau_score", "op": "is_null"},
    "then": {"decision": "refer"},
    "because": "No bureau record: manual assessment (POL-CR-07 §4)"}],
 "otherwise": {"decision": "accept"},
 "note": "Origination eligibility, retail mortgages"}
```

A **condition** is one of exactly four things:

```
{"field": "ltv", "op": "gt", "value": 0.8}     a field test
{"all": [ … ]}                                 every one of them holds
{"any": [ … ]}                                 at least one holds
{"not":   … }                                  it does not hold
```

and nothing else. Nesting is refused past six levels, and a set is refused past
512 rules — past that nobody is checking the first-match ordering by reading it,
and the honest answer is that this wants to be a model rather than a rule set.

### The operators

Eleven, deliberately few.

| | Means |
|---|---|
| `eq` · `ne` | equal to · not equal to |
| `lt` · `le` · `gt` · `ge` | less than · at most · greater than · at least |
| `between` | within the closed range `[low, high]` |
| `in` · `not_in` | one of · none of |
| `is_null` · `not_null` | not supplied · supplied |

The six ordered operators need a field with an order — `numeric`, `integer`,
`date`, `datetime` and their spellings. `product_code > "MTG"` has a defined
answer in every programming language and no meaning in any bank, so it is
refused as `unordered_comparison` rather than evaluated.

**There is no arithmetic**, and that is the design rather than a gap. A rule that
needs arithmetic needs a [derived
feature](/help/features-and-two-clocks) — the same boundary drawn everywhere
else: the platform transforms what it holds and does not compute new quantities
inside a governed object.

### Two fields you cannot skip

**`otherwise` is required.** No input falls through, and there is no implicit
default anywhere in the platform. A rule set whose author has not written down
what happens to the cases they did not think of is a rule set whose behaviour on
those cases is an accident.

**`because` is required, per rule.** The policy, the limit, the regulation. A
rule with no stated reason cannot be defended to a supervisor, cannot be reviewed
by whoever owns the policy it implements, and cannot be retired by anybody later
because nobody knows what it was for. It is the field an author will most want to
skip, and it is the one that makes the difference between a rule set and a stored
procedure.

## Why a structure and not an expression language

MAYA already parses a small whitelisted arithmetic expression for derived
features, and reusing it here was the obvious move. It is the wrong one, for a
reason worth stating: **a free expression is opaque to analysis.**

The whole argument for putting rule sets in a governance platform is that a rule
set is the one kind of model a non-programmer can actually review — and that the
platform can therefore say things about it that it cannot say about a neural
network. Whether a rule can ever fire. Whether two rules contradict each other.
Whether any input falls through. None of those can be answered about
`x * 0.3 + y > threshold`; all of them can be answered about a tree of
`field op value`.

## The four checks

They run before a rule set can be recorded, and on every keystroke in the editor.

| Check | What it decides |
|---|---|
| **Totality** | no input falls through — by construction, because `otherwise` is required, rather than by analysis |
| **Reachability** | a rule an earlier rule already covers can never fire |
| **Contradiction** | the same condition reaching two different outcomes |
| **Conformance** | every field a rule reads is declared in the version's input schema, no ordered operator is asked of a field with no order, no field is compared against a value of the wrong kind, and every outcome field is declared in its output schema |

**Reachability is the one worth having.** A rule an earlier rule already covers
never fires — and nothing about reading the document tells you so. Somebody
believes that rule is in force. It appears in the model card, gets cited in a
committee paper, and survives every review, *because a rule that never fires also
never produces a wrong answer.* No spreadsheet tells you this.

### What the reachability analysis promises, exactly

**Sound and incomplete, and the distinction matters.**

*Sound* — when it reports a rule unreachable, the rule is unreachable. It never
cries wolf, because a check that produces false alarms is a check somebody turns
off, and then the real ones go with it.

*Incomplete* — it reports a rule unreachable when a **single** earlier rule
covers it. Two earlier rules that between them cover a third — `ltv > 0.8` and
`ltv <= 0.8` covering everything — are **not** detected.

So the promise is exactly this, and it is worth reading twice:

> **No rule is shadowed by any single earlier rule.**

Not *no rule is unreachable*. Full coverage checking is satisfiability over the
whole set: decidable here, and a solver — and a solver inside a governance
platform is a dependency whose failure modes nobody in the bank can debug. A
check that claims more than it delivers is the thing this analysis exists to
find, so the narrow promise is the one that is stated, on the rule-set page as
well as here.

Two smaller honesty points. Where a condition expands past 256 disjunctions the
analysis reports that it **did not run**, rather than running partially and
saying no problems were found. And the negation of `between` has no single-atom
form, so it is treated as opaque rather than approximated — an approximation
there would make the analysis unsound, and unsound is the one thing it must not
be.

## What it says, in English

Every rule set renders as sentences:

```
1. when product is equal to btl and ltv is greater than 0.8, then decision = refer
   — BTL above 80% LTV is outside appetite (CP-2024-11)
2. when bureau_score is not supplied, then decision = refer
   — No bureau record: manual assessment (POL-CR-07 §4)
otherwise, decision = accept
```

That is not a convenience. A rule set exists to be reviewed by whoever owns the
policy it implements, and if the reviewable form lived only in a screen then the
export pack, the committee paper and the model card would each get a different
rendering of one rule — and the differences between three renderings are exactly
where a misreading hides.

## The editor, and the boundary it does not cross

MAYA does not train models and does not run them. An authoring surface looks like
a straight breach of that, and the distinction is worth being precise about
because it is what keeps the rest of the boundary intact.

**MAYA does not become the authoring tool. It becomes an editor for a parameter
set it already held.** The governed object always existed; what did not exist was
any way to type into it except a raw JSON body, and any way for the platform to
say what the rules meant. Everything that made a parameter set trustworthy still
applies unchanged — the set lands `proposed`, the digest is over the content, and
whoever wrote the rules may not approve them.

**This is not an ONNX or PMML editor, and will not become one.** Those formats
serialize a *fitted* map. Authoring one by hand would let MAYA mint an artifact
that has never been trained or validated and is indistinguishable in the register
from one that was. A rule set has no training run to be indistinguishable from —
**authorship is its provenance**, which is exactly what `declared` means.

Three things follow:

- **Checking and trialling are free.** They carry no authority, record nothing,
  and can be called on every keystroke. An author iterates without touching the
  register, and the moment a draft becomes a governed object is one act they had
  to choose.
- **Rendering is separate from authoring.** The English form and the canonical
  bytes can be produced over an approved set without authoring anything.
- **A trial is not an execution.** It is deliberately not routed through
  `/execute`: there is no warrant and no entitlement, because nothing is being
  scored — an author is reading their own draft back. Giving it an authority
  would have meant inventing one, and an authority invented for a convenience is
  the kind that turns up later attached to something else.

The editor is at `/rules/{model}/{semver}` — **one page per version, not per
model**, because a rule set is checked against a particular version's input
schema, and picking one silently is how a rule set comes to be validated against
something other than what it runs on. A recorded set reads back at
`/rulesets/{parameter_set_id}`.

## Running one

For a T8 model the rule set **is** `P`. It reaches the engine the way every
register-held parameter object does: the approved set is resolved, its digest
re-derived, and the values put in the invocation's parameters. Running a rule set
at an unapproved point of `P` is therefore refused by the same mechanism that
refuses running a scorecard at unapproved coefficients.

The warrant's verb must be `score`. A change to the rules is a new parameter set
somebody approves, not a fit, and `fit` is refused as `wrong_verb`.

**Every decision names the rule that made it.** `matched_rule` and `because`
travel back with the outcome even when the output schema does not declare them:

```json
{"decision": "refer",
 "matched_rule": "btl_high_ltv",
 "because": "BTL above 80% LTV is outside appetite (CP-2024-11)"}
```

That is not diagnostics. A decision a bank cannot attribute to a rule is a
decision it cannot explain to the customer who was refused, and under most
consumer-credit regimes **the explanation is the obligation**, not the outcome.

When no rule matches, `matched_rule` is `null` and the reason says so — *"no rule
matched; the stated otherwise applies"*.

### Missing is not false

A field absent from the input makes `is_null` true and every comparison false.
So a rule reading a field nobody supplied does **not** fire, rather than firing
on a coerced default; `otherwise` catches it, and `otherwise` is where somebody
has written down what to do when the data is not there.

A value that arrives at the wrong type — a string where a number was declared —
is a **refusal**, not a rule outcome. Python would happily compare two strings
lexically and return something plausible; a rule set that guessed there would
return an outcome nobody authored.

## The API

| Method | Path | Permission | What it does |
|---|---|---|---|
| `GET` | `/rulesets/vocabulary` | auth | The operators, what each means, which need an ordered field, and which dtypes have an order — from the code rather than from a copy of it |
| `POST` | `/rulesets/check` | `model:read` | Validate a draft against the version's schemas. Returns the whole report, the fields read, the English form and the canonical document. **Records nothing** |
| `POST` | `/rulesets/trial` | `model:read` | Run a draft against sample rows. Reports each outcome, how many times each rule fired, which fired on nothing, and how many rows fell through to `otherwise`. **Records nothing, decides nothing** |
| `POST` | `/rulesets` | `parameter:record` | Publish. Validates, then records a parameter set that lands `proposed` |
| `GET` | `/rulesets/{parameter_set_id}` | `model:read` | An approved rule set in English |

`check` needs only `model:read` on purpose: checking a draft changes nothing, and
requiring the recording permission to *look* at whether a document is valid would
push authors to skip the step.

A trial also earns its keep as a **coverage report**. A rule that fires on none
of the sample rows is not necessarily wrong — but a rule set where most rules
never fire on any realistic input is one somebody should look at before it is
approved.

## Refusals you will meet

All of these are **422** unless marked otherwise: the document is well-formed
JSON and wrong as a *policy*, which is a problem with what was written rather
than with the state of the register.

| Code | Means |
|---|---|
| `no_rules` | a rule set with no rules is its `otherwise`, written at length |
| `otherwise_required` | it does not say what happens when no rule matches |
| `too_many_rules` | past 512, nobody is checking the ordering by reading it |
| `rule_id_required` · `rule_id_malformed` | ids travel into logs, exports and audit reports; `a-z`, `0-9` and underscore |
| `duplicate_rule_id` (**409**) | two rules answering to one name in every decision that quotes it |
| `outcome_required` | the rule does not say what it decides |
| `reason_required` | the rule does not say why it exists |
| `condition_malformed` · `condition_ambiguous` · `condition_too_deep` | the condition is not one of the four shapes, combines two combinators in one object, or nests past six levels |
| `unknown_operator` | not one of the eleven |
| `value_required` · `value_not_expected` | an operator that compares carries nothing to compare against, or `is_null`/`not_null` carries a value. A value the platform silently ignored would make the rule mean something other than it reads |
| `value_malformed` | `in`/`not_in` without a non-empty list, or `between` without exactly `[low, high]` |
| `empty_range` | `between` with the bounds the wrong way round: the rule can never fire |
| `unknown_field` | the rule reads a field the version's input schema does not declare — which is a rule that will silently never fire, the worst of the three outcomes available |
| `unordered_comparison` | an ordered operator on a categorical field |
| `unknown_outcome_field` | a rule or the `otherwise` sets a field the output schema does not declare |
| `value_not_comparable` | at evaluation: the value arrived at a type the rule cannot compare |
| `rule_never_fires` | a condition no input can satisfy — `ltv > 0.9 and ltv < 0.5`. Almost always a typo in a bound |
| `rule_unreachable` | an earlier rule matches everything this one matches. Reorder them, narrow the earlier one, or delete this one |
| `rules_contradict` (**409**) | two rules with the same condition and different outcomes. First match wins, so the second can never fire — but **the ordering is not the problem**: somebody has to decide which outcome the policy means |
| `not_a_ruleset_model` (**409**) | the version's `parameter_kind` is not `rule_set`, so its parameter object is not a rule set |
| `not_a_ruleset` (**409**) | that parameter set is a fitted one; read it on the model page |
| `ruleset_malformed` | the document is not an object, or a rule inside it is not. At *execution* this one means something worse: the register holds a stored rule set that no longer parses, which is a platform defect rather than a bad request, and the run is refused rather than answered with the part of the policy that could be read |
| `not_found` (**404**) | the version is not registered; register it before authoring its rules |
| `no_ruleset` (**409**) | at execution: the warrant binds no parameter set, so there are no rules to run and nothing that was approved |
| `wrong_verb` (**409**) | at execution: the warrant asks for something other than `score`. A change to the rules is a new parameter set somebody approves, not a fit |

`rules_contradict` is checked **before** `rule_unreachable`, and the order is not
cosmetic. Two rules with the same condition are also a shadowing — the first
covers the second exactly — so reporting shadowing first made `rules_contradict`
unreachable, in the checker written to find unreachable rules. The messages point
somewhere different: *"this rule can never fire, reorder it"* sends an author to
the ordering, and the ordering is not the mistake.

## What this does not do

**It does not find your rule sets.** MAYA holds them; there is no EUC scanner and
no discovery sweep, so the population arrives by whatever route a bank already
uses.

**It does not import them either.** A decision table in a spreadsheet, a DMN
file, a stored procedure — each would be a parser, and each a parser that can be
subtly wrong. The rules are typed in, or posted as a document.

**The coverage analysis is single-rule.** Stated above, and stated again here
because it is the limit a reader is most likely to over-read.

**Conformance checks values it can be certain about, and no others.** A numeric
field compared with text, or a textual field compared with a number, is refused
`value_wrong_type`: `{"field": "ltv", "op": "eq", "value": "high"}` on a numeric
`ltv` can never be true, and a rule that can never fire is exactly what these
checks exist to prevent.

Two cases are deliberately not judged. A **date** is an epoch in some registers
and an ISO string in others, so neither spelling is refused. An **unrecognised
dtype** is somebody's own extension. In both, refusing would mean refusing
correct rules — and a check that produces false alarms is one people switch off,
taking the real alarms with it.

**It computes no above-the-line or below-the-line testing.** The T8 fibre says
that is what outcomes analysis for a rule set *is*; MAYA holds such results where
they were computed and does not produce them. The per-rule fire counts a trial
reports are an author's sanity check before approval, not a monitoring result.

**It does not read the policy.** Whether the rules say what the policy says is a
human judgment, and `because` is where the author writes down which policy each
rule is claiming to implement. The platform checks that the claim was made, never
that it is true.

---

Worked end to end, from an empty editor to an approved set an engine runs:
[Authoring a rule set](/tutorials/defining-a-model).
