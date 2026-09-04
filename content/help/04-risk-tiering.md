---
title: Risk tiering and supervisory regimes
slug: risk-tiering
section: The register
order: 40
icon: bar-chart-steps
summary: How much scrutiny a model gets — a tier computed from materiality and complexity with its derivation stored — and which supervisors require what, each reasoning in its own vocabulary.
audience: Model risk, Compliance, Model owners
---

# Risk tiering and supervisory regimes

Two questions decide how much control a model attracts. *How much is at stake,
and how hard is this thing to challenge?* — which is the tier. And *which
supervisor is asking, and in what terms?* — which is the regime. They are
computed separately because they answer to different authorities, and the same
model can be material under one and out of scope under another.

## What the tier decides

A tier decides validation depth, review frequency, approval route, monitoring
intensity, and how long a warrant lives. Getting it wrong in either direction is
expensive — under-tier and you under-control a material exposure; over-tier and
you spend your scarce validation capacity on a marketing propensity model.

## Two lattices, not one score

Tiering is not a weighted sum. Materiality and complexity are separate ordered
scales, and the tier is a function of both.

**Materiality** comes from the exposure the model touches joined with the
purpose it serves:

```
negligible  <  low  <  moderate  <  material  <  critical
```

Exposure bands and purpose ranks are configuration:

```yaml
risk:
  exposure_bands:
    negligible: 0
    low: 1000000
    moderate: 50000000
    material: 500000000
    critical: 5000000000
  purpose_ranks:
    commercial: 1
    risk_management: 2
    financial_reporting: 3
    regulatory_capital: 4
```

**Complexity** runs `simple < moderate < complex < advanced` and is a meet over
five components — how hard the model is to understand and to challenge:

| Component | Raises complexity when |
|---|---|
| Trainability class | it is T3, T4, T5 or T6 — the classes whose parameters resist inspection |
| Adaptivity and configuration | the class is T4 or T5 |
| Feature count | more than fifty inputs |
| Alternative data | the model reads it |
| Interpretability | the model is not declared interpretable |

Note what is *not* in there. The output kind plays no part, and neither does
opacity or adaptivity as separate facts — they enter through the trainability
class, which is where they were already derived. One derivation, read twice, is
better than two that can disagree.

## Monotonicity is enforced

The tiering function τ is **monotone**: raising materiality or complexity can
never lower the tier. That is law **L-4**, and it is checked by property test
over generated lattice pairs, not by convention.

It matters because the alternative is a scoring formula where a model becomes
*less* risky when you tell the truth about it — and once that is possible,
someone will find it.

## The derivation is stored

An assessment returns more than a number:

```bash
POST /api/v1/models/credit.pd.smallbiz/assess
{"exposure": 2000000000, "purpose_class": "regulatory_capital",
 "feature_count": 64, "uses_alternative_data": false, "interpretable": true}
```

The response carries the facts used, the materiality and complexity levels
reached, the required control set, the next review date, and the ruleset version
that decided.

Why store the derivation rather than the answer:

- **Tiers get challenged.** "Why is this Tier 1?" needs an answer that is not
  "the system said so".
- **Rulesets change.** When the bands are recalibrated, you need to know which
  assessments were made under which version to re-run the right ones.
- **It makes disagreement productive.** An argument about whether exposure is
  $400m or $600m is a resolvable argument. An argument about a score is not.

## Required controls

Each tier maps to a set of required controls, and the mapping is the **Galois
adjoint** of the tiering function — law **L-5**. The control set is the weakest
one adequate for the tier, which means adding a control never weakens the
requirement and the two directions stay consistent.

Practically: `required_controls(tier)` gives what must be in place, and
`supports_tier(controls)` gives the highest tier a given control set can carry.
Both come from one definition, so they cannot drift apart.

## Review cadence

```yaml
risk:
  review_months: {1: 12, 2: 18, 3: 24, 4: 36}
```

Tier 1 models are reviewed annually, Tier 4 every three years, and the
assessment stamps the next review date from that. The cadence is configuration
because supervisory expectation on this differs by jurisdiction and by firm, and
hard-coding it would be a promise MAYA cannot keep.

## Regimes disagree about what words mean

A bank subject to the Federal Reserve, the PRA and the EU AI Act is not subject
to three checklists over one set of fields. It is subject to three **different
vocabularies** describing overlapping realities.

- **SR 26-2** asks whether something applies statistical, economic or financial
  theory to produce a quantitative estimate, and how material it is.
- **The EU AI Act** asks what the system is *for*, whether a natural person is
  affected, and whether it falls in an Annex III category.
- **SS1/23** asks about materiality and proportionality, and about post-model
  adjustments.

Flattening those into one flat set of compliance fields is how a scope
determination becomes indefensible. So each regime carries its own **signature** —
the terms it may use — and its own obligations expressed in those terms. The
three shipped are activated from configuration:

```yaml
regimes:
  active: [sr-26-2, ss1-23, eu-ai-act]
```

## The check that makes translation trustworthy

Each regime also carries a **translation** into MAYA's core vocabulary: SS1/23's
"materiality" onto `tier`, the AI Act's "high-risk use" onto a combination of
tier and domain. Writing one is easy. Writing one that is *right* is not, and a
wrong translation produces exactly the class of bug that cannot be defended to an
examiner.

Institution theory gives a check for this, and it is the reason for the whole
construction:

```
M ⊨_Σ′ σ(φ)   ⟺   Mod(σ)(M) ⊨_Σ φ
```

**Truth is invariant under change of notation.** Evaluating a translated
obligation against the core state must give the same answer as translating the
state into the regime's vocabulary and evaluating the original obligation there.
If those disagree, the translation is wrong.

MAYA checks this rather than assuming it, against inventory states spanning the
corners — nothing recorded, everything recorded, and the awkward middles:

```bash
GET /api/v1/regimes/sr-26-2/satisfaction
# → {"holds": true, "checked": 42,
#    "detail": "truth is invariant under translation across 42 sentence-state pairs"}
```

**A regime that fails cannot be activated.** Activation is refused with
`satisfaction_condition_failed`, and a regime with an untranslated term is
refused with `incomplete_translation`. An encoding whose truth does not survive
translation would produce determinations nobody can defend, and those are worse
than no determinations at all.

### It caught a real error

The SR 26-2 encoding shipped here failed this check on first run. Its scope
sentence *read* the term `in_scope` while declaring only
`applies_quantitative_theory` and `produces_estimate` — so when evaluated against
its declared terms alone it saw nothing, and concluded that every model was out
of scope.

That is precisely the confidently-incorrect determination the condition exists to
prevent, and it was found by a property test rather than by an examiner. The
encoding now declares the term it reads, the comment in the source records why,
and a regression test holds the fix in place.

The report distinguishes the two failure modes, because they need looking at in
different places:

| Reason | Means |
|---|---|
| *the sentence reads a term it did not declare* | an encoding error with a one-line fix |
| *truth changed under translation* | the translation assigns a meaning that does not survive |

## Determinations are derivations

```bash
GET /api/v1/regimes/determinations?urn=maya://model/credit.pd.smallbiz
```

Every verdict carries the terms it read, the regime-eye view of the model, and
the citation each obligation rests on:

```json
{"regime": "eu-ai-act",
 "read_as": {"high_risk_use": true, "affects_natural_persons": true,
             "human_oversight": true, "technical_documentation": false},
 "obligations": [
   {"sentence": "documentation", "satisfied": false,
    "text": "high-risk systems keep technical documentation",
    "citation": "EU AI Act Art. 11, Annex IV",
    "read": {"high_risk_use": true, "technical_documentation": false}}]}
```

*"Why is this model in scope for the AI Act"* is the question that gets asked,
and *"the system said so"* has never been an answer.

## Disagreement is an output, not a bug

A model can be in scope for one regime and out of scope for another. That is a
fact somebody needs to know, so it is reported as one:

```json
{"compliant_under": ["ss1-23"], "not_compliant_under": ["sr-26-2", "eu-ai-act"],
 "disagreement": true,
 "detail": "compliant under 1 of 3 activated regime(s); the regimes disagree,
            which is a fact about the estate rather than a defect"}
```

Notice how the encodings differ in practice. A Tier 1 treasury model is material
under SR 26-2 and **not** high-risk under the AI Act, because the Act reasons
about whether natural persons are affected rather than about exposure. Merging
them into one score would lose exactly that distinction — which is the same
reason materiality and complexity are two lattices rather than one number.

## Adding a supervisor

MAS, APRA, OSFI E-23, a future GenAI rule — each is a **signature, some sentences
and a translation**. The schema does not change, the API does not change, and the
interface does not change.

That is the payoff for the construction, and it is why the regimes are
institutions rather than a table of rules.

## What these encodings are not

The three shipped here are **illustrative, not complete, and not legal advice**. A
supervisory statement is forty pages of open-textured prose, and turning it into
obligations is expert work a firm must do for itself, with its own counsel,
against its own estate.

What the platform provides is the structure to hold the result in a form that can
be evaluated, translated, and checked for consistency.
