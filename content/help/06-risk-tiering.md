---
title: Risk tiering
slug: risk-tiering
section: The register
order: 60
icon: bar-chart-steps
summary: How a tier is computed from materiality and complexity, why it is monotone, and why the derivation is stored alongside the answer.
audience: Model risk, Model owners
---

# Risk tiering

A tier decides how much scrutiny a model gets: validation depth, review
frequency, approval route, monitoring intensity. Getting it wrong in either
direction is expensive — under-tier and you under-control a material exposure;
over-tier and you spend your scarce validation capacity on a marketing
propensity model.

## Two lattices, not one score

Tiering here is not a weighted sum. Materiality and complexity are separate
ordered scales, and the tier is a function of both.

**Materiality** comes from the exposure the model touches and the purpose it
serves:

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

**Complexity** comes from the trainability class, the output kind, opacity and
adaptivity — how hard the model is to understand and to challenge.

## Monotonicity is enforced

The tiering function τ is **monotone**: raising materiality or complexity can
never lower the tier. This is checked by property test, not by convention.

It matters because the alternative is a scoring formula where a model becomes
*less* risky when you tell the truth about it — and once that is possible,
someone will find it.

## The derivation is stored

An assessment returns more than a number:

```bash
POST /api/v1/models/credit.pd.smallbiz/assess
{"exposure": 2000000000, "purpose_class": "regulatory_capital"}
```

The response carries the facts used, the materiality and complexity levels
reached, the required control set, and the ruleset version that decided.

Why store the derivation rather than the answer:

- **Tiers get challenged.** "Why is this Tier 1?" needs an answer that is not
  "the system said so".
- **Rulesets change.** When the bands are recalibrated, you need to know which
  assessments were made under which version to re-run the right ones.
- **It makes disagreement productive.** An argument about whether exposure is
  $400m or $600m is a resolvable argument. An argument about a score is not.

## Required controls

Each tier maps to a set of required controls, and the mapping is a **Galois
adjoint** of the tiering function — the control set is the weakest one adequate
for the tier, which means adding a control never weakens the requirement and
the two directions stay consistent.

Practically: `required_controls(tier)` gives what must be in place, and
`supports_tier(controls)` gives the highest tier a given control set can carry.
Both come from one definition, so they cannot drift apart.

## Review cadence

```yaml
risk:
  review_months: {1: 12, 2: 18, 3: 24, 4: 36}
```

Tier 1 models are reviewed annually, Tier 4 every three years. The cadence is
configuration because supervisory expectation on this differs by jurisdiction
and by firm, and hard-coding it would be a promise MAYA cannot keep.
