---
title: Risk tiering and supervisory regimes
slug: risk-tiering
section: The register
order: 40
icon: bar-chart-steps
summary: The tier, computed from materiality and complexity with its derivation kept; what the tier actually changes and what it does not; and supervisory regimes that reason in their own vocabulary and are checked before they can be turned on.
audience: Model risk, Compliance, Model owners
---

# Risk tiering and supervisory regimes

Two questions decide how much control a model attracts, and they answer to
different authorities.

*How much is at stake, and how hard is this thing to challenge?* — the **tier**.
*Which supervisor is asking, and in what terms?* — the **regime**. They are
computed separately, because the same model can be Tier 1 under one and out of
scope under the other, and merging them would lose exactly that.

## Assessing a model

```bash
curl -u j.okafor:… -X POST \
  localhost:5006/api/v1/models/credit.pd.smallbiz/assess \
  -H 'Content-Type: application/json' -d '{
    "exposure": 2000000000,
    "purpose_class": "regulatory_capital",
    "feature_count": 64,
    "uses_alternative_data": false,
    "interpretable": true}'
```

Five facts, and that is the whole request. `exposure` and `purpose_class` are
required outright — a default of "nothing, commercial" would tier a model at the
bottom of the lattice on nobody's word. The other three have low-risk defaults in
the schema, and MAYA refuses the assessment with `fact_not_supplied` whenever
taking those defaults would land on a **different tier** from reading them at
their worst. An omission that cannot change the answer is allowed through; one
that can is a caller choosing their own tier by staying silent.

A sixth fact — the **trainability class** —
is taken from the model's latest version rather than accepted from the caller,
because it is the single largest driver of complexity and a caller who could set
it could choose their own tier. A model with no versions yet is assessed as
though it were `T0`.

The response is the derivation, not just the number:

```json
{"tier": 1, "materiality": "material", "complexity": "moderate",
 "required_controls": ["independent_validation", "annual_review",
                       "monthly_monitoring", "committee_approval",
                       "full_documentation", "reproducibility_proof"],
 "rationale": "materiality=material (exposure 2,000,000,000 in band 'material',
               purpose 'regulatory_capital'); complexity=moderate (class T2);
               tau(material,moderate)=Tier 1 under ruleset 2026.09.1",
 "ruleset_version": "2026.09.1"}
```

Six fields, and that is all of them. The `rationale` is the sentence somebody
reads out in a committee. Note what is **not** in the response: the facts you
sent, and the next review date.

Why the derivation and not the answer alone:

- **Tiers get challenged.** *"Why is this Tier 1?"* needs a better answer than
  *"the system said so"*.
- **Rulesets change.** When the bands are recalibrated you need to know which
  assessments were made under which version, to re-run the right ones.
- **It makes disagreement productive.** An argument about whether exposure is
  $400m or $600m is resolvable. An argument about a score is not.

The assessment row also stamps a `next_review_due` from the cadence below. Worth
knowing: **no endpoint or page currently reads it back.** It is recorded and not
yet surfaced.

## Materiality is a join. Complexity is not a lattice.

This is worth being exact about, because an earlier version of this page and a
comment still sitting in the source both said "meet", and only one of the two
scales is a lattice operation.

**Materiality** is a genuine **join** — the more severe of two readings, the
exposure the model touches and the purpose it serves:

```
negligible  <  low  <  moderate  <  material  <  critical
```

Both are configuration:

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

**Complexity** runs `simple < moderate < complex < advanced` and is a **score
over declared components, clamped into that chain** — arithmetic, not a meet:

| Component | Adds one when |
|---|---|
| Trainability class | it is T3, T4, T5 or T6 |
| Adaptive or generative | it is T4 or T5 — so these two score **two**, not one |
| Feature count | strictly more than fifty inputs |
| Alternative data | the model reads it |
| Interpretability | the model is not declared interpretable |

Note what that means at the edges. T0, T1 and T2 add nothing — a closed-form
pricer and a logistic scorecard are `simple` unless another component fires. So
do **T7 and T8**: an expert-elicited overlay or a policy rulebook scores zero
here, and if that is wrong for your estate it is the components that are wrong,
not the model.

Note also what is *not* a component. Output kind plays no part, and opacity and
adaptivity are not separate facts — they enter through the trainability class,
where they were already derived. One derivation read twice beats two that can
disagree.

Both scales are **monotone**, which is what the law needs; only one of them is a
lattice operation, and saying so is cheaper than defending the stronger claim.

### The function, stated

```
score = materiality × 2 + complexity        (each as its rank, from zero)

materiality is critical                     →  Tier 1, whatever the complexity
score ≥ 7  →  Tier 1      score ≥ 5  →  Tier 2
score ≥ 2  →  Tier 3      otherwise  →  Tier 4
```

The concrete case that shows it is proportionate: a **material** model that is
**simple** is Tier 2, not Tier 1. A materially exposed regression that everybody
can read does not deserve the ceremony a capital model does, and a tiering
function that could not say so would be routed around within a quarter.

## Monotonicity is enforced

The tiering function τ is **monotone**: raising materiality or complexity can
never lower the tier. That is law **L-4**, asserted by property test over three
hundred generated lattice pairs in
`tests/test_risk.py::TestTauMonotonicity` — the one place Hypothesis is used.

It matters because the alternative is a scoring formula in which a model becomes
*less* risky when you tell the truth about it. Once that is possible, somebody
finds it.

## Required controls

Each tier maps to a control set, and the mapping is the **Galois adjoint** of the
tiering function — law **L-5**, in `tests/test_risk.py::TestControlAdjunction`:

```
required_controls(tier) ⊆ applied   ⟺   tier ≥ supports_tier(applied)
```

`required_controls(tier)` gives what must be in place. `supports_tier(applied)`
gives the **strictest** tier that control set can defend, and defaults to 4 —
controls that defend nothing defend Tier 4. Both come from one definition, so
adding a control never weakens the requirement and the two directions cannot
drift apart.

## What the tier actually changes — and what it does not

Two things follow the tier by the L-5 adjunction, and they are the two that
refuse:

| | |
|---|---|
| **The version approval quorum** | Tiers 1 and 2 need a model risk manager *and* a validator; tiers 3 and 4 need one signature. See [Approval and attestation](/help/approval-and-attestation#a-version-is-approved-by-a-quorum-too) |
| **Warrant lifetime and grace** | A Tier 1 warrant lives sixty seconds with zero grace; tiers 3 and 4 get grace so a control-plane blip does not stop the business. See [Warrants](/help/warrants#expiry-grace-and-the-revocation-floor) |

And a review cadence is stamped from configuration:

```yaml
risk:
  review_months: {1: 12, 2: 18, 3: 24, 4: 36}
```

**Validation depth, monitoring frequency and the documentation set do not follow
the tier.** They are named in `required_controls` and nothing enforces them from
there. That is a gap, it is recorded as one, and a page claiming otherwise would
be the kind of assertion this platform exists to replace.

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

Flattening those into one set of compliance fields is how a scope determination
becomes indefensible. So each regime carries its own **signature** — the terms it
may use — its own obligations expressed in those terms, and a **translation**
into MAYA's core vocabulary. Three ship, activated from configuration:

```yaml
regimes:
  active: [sr-26-2, ss1-23, eu-ai-act]
```

## A regime is checked before it can be turned on

Writing a translation is easy. Writing one that is *right* is not, and a wrong
one produces exactly the class of bug that cannot be defended to an examiner.
Institution theory gives the check, and it is the reason for the whole
construction:

```
M ⊨_Σ′ σ(φ)   ⟺   Mod(σ)(M) ⊨_Σ φ
```

**Truth is invariant under change of notation.** Evaluating a translated
obligation against the core state must give the same answer as translating the
state into the regime's vocabulary and evaluating the original there. That is law
**L-8**, and it is checked against **six probe states** spanning the corners —
nothing recorded, everything recorded, and the awkward middles — rather than over
generated ones. The weaker quantifier is stated because it is the true one.

```bash
GET /api/v1/regimes/sr-26-2/satisfaction
```

```json
{"regime": "sr-26-2", "holds": true, "checked": 42, "states": 6,
 "untranslated_terms": [], "failures": [],
 "detail": "truth is invariant under translation across 42 sentence-state pairs"}
```

Forty-two is six probe states against seven sentences. Activation runs four
checks, in this order, and each has its own refusal:

| Refusal | Status | Means |
|---|---|---|
| `no_regime` | 404 | No such key |
| `incomplete_translation` | 422 | A term the regime uses has no translation into the core |
| `obligation_contradiction` | 422 | **L-16** — the regime obliges and forbids the same term, so it cannot be coherently satisfied |
| `satisfaction_condition_failed` | 422 | **L-8** — truth did not survive translation |

A regime that fails any of them **cannot be activated**. Determinations nobody
can defend are worse than no determinations at all.

### It caught a real error

The SR 26-2 encoding shipped here failed this check on its first run. Its scope
sentence *read* the term `in_scope` while declaring only
`applies_quantitative_theory` and `produces_estimate` — so evaluated against its
declared terms alone it saw nothing and concluded every model was out of scope.

That is precisely the confidently-incorrect determination the condition exists to
prevent, found by a property test rather than by an examiner. The encoding now
declares the term it reads, the comment in the source records why, and a
regression test holds the fix.

The report separates the two failure modes, because they are fixed in different
places:

| `reason` | Means |
|---|---|
| *the sentence reads a term it did not declare* | an encoding error with a one-line fix |
| *truth changed under translation* | the translation assigns a meaning that does not survive |

## Determinations are derivations

```bash
GET /api/v1/regimes/determinations?urn=maya://model/credit.pd.smallbiz
```

The body carries the model, the **core state** every regime was translated
against, one entry per activated regime, and the disagreement summary:

```json
{"model": "maya://model/credit.pd.smallbiz",
 "core_state": {"tier": 1, "trainability_class": "T2", "has_validation": true, "…": "…"},
 "regimes": [
   {"regime": "eu-ai-act", "title": "EU AI Act — high-risk and generative obligations",
    "authority": "European Union",
    "read_as": {"high_risk_use": true, "affects_natural_persons": true,
                "human_oversight": true, "technical_documentation": false},
    "obligations": [
      {"sentence": "documentation", "satisfied": false,
       "text": "high-risk systems keep technical documentation",
       "citation": "EU AI Act Art. 11, Annex IV",
       "read": {"high_risk_use": true, "technical_documentation": false}}],
    "compliant": false, "unmet": ["documentation"]}],
 "compliant_under": ["ss1-23"],
 "not_compliant_under": ["sr-26-2", "eu-ai-act"],
 "disagreement": true,
 "detail": "compliant under 1 of 3 activated regime(s); the regimes disagree,
            which is a fact about the estate rather than a defect"}
```

*"Why is this model in scope for the AI Act"* is the question that gets asked,
and *"the system said so"* has never been an answer. Every verdict carries the
terms it read, the regime-eye view of the model, and the citation each obligation
rests on.

**Disagreement is an output.** A Tier 1 treasury model is material under SR 26-2
and **not** high-risk under the AI Act, because the Act reasons about whether
natural persons are affected rather than about exposure. Merging them into one
score would lose exactly that — the same reason materiality and complexity stay
two scales.

## Adding a supervisor

MAS, APRA, OSFI E-23, a future GenAI rule — each is a **signature, some sentences
and a translation**. The schema does not change, the API does not change, and the
interface does not change. That is the payoff for building regimes as
institutions rather than as a table of rules.

## What these encodings are not

The three shipped here are **illustrative, not complete, and not legal advice**. A
supervisory statement is forty pages of open-textured prose, and turning it into
obligations is expert work a firm does for itself, with its own counsel, against
its own estate.

What the platform supplies is the structure to hold the result in a form that can
be evaluated, translated, and checked for consistency before anybody relies on
it.

## Related

Tiering and the estate's **risk appetite** meet at two points: `models_untiered`
is a reportable metric, and `tier` is one of the three scopes a limit may be
declared over. See [Risk appetite and the board
pack](/help/portfolio-reporting).
