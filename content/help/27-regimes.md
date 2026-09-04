---
title: Supervisory regimes
slug: regimes
section: Assurance
order: 152
icon: bank
summary: Several supervisors at once, each reasoning in its own vocabulary — and the mathematical check that stops a regime encoding producing determinations nobody can defend.
audience: Model risk, Compliance
---

# Supervisory regimes

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
the terms it may use — and its own obligations expressed in those terms.

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

**A regime that fails cannot be activated.** An encoding whose truth does not
survive translation would produce determinations nobody can defend, and those are
worse than no determinations at all.

### It caught a real error

The SR 26-2 encoding shipped here failed this check on first run. Its scope
sentence *read* the term `in_scope` while declaring only
`applies_quantitative_theory` and `produces_estimate` — so when evaluated against
its declared terms alone it saw nothing, and concluded that every model was out
of scope.

That is precisely the confidently-incorrect determination the condition exists to
prevent, and it was found by a property test rather than by an examiner. The
report distinguishes the two failure modes, because they need looking at in
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
them into one score would lose exactly that distinction.

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
