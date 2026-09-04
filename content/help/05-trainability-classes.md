---
title: Trainability classes
slug: trainability-classes
section: The register
order: 50
icon: diagram-3
summary: T0 to T8 — one definition of "model" that stretches from Black–Scholes to an agent, without becoming vacuous. And why the class is derived rather than declared.
audience: Everyone
---

# Trainability classes

Most model inventories were designed around one implicit assumption: a model is
something that was **trained on data**. Ask that inventory to hold a Black–Scholes
pricer, a credit policy rulebook or a prompt bundle, and it either rejects them
or forces them into fields that make no sense — a "training dataset" for an
analytic formula, a "model performance" metric for a rulebook.

MAYA takes the opposite route. The definition is about **how the parameter object
is inhabited**, and training is just one of the ways.

## The classes

| Class | P is inhabited by | Bank examples |
|---|---|---|
| **T0** | Nothing — P is the unit. Parameters come from theory. | Black–Scholes closed form, SA-CCR, standardised RWA, accrual mechanics |
| **T1** | Calibration to market observables, re-solved each period | Hull–White to swaption vols, SABR surfaces, bootstrapped yield curves |
| **T2** | Statistical estimation from a sample | Logistic PD scorecards, OLS/GLM, ARIMA, Cox survival models |
| **T3** | Numerical optimisation over a loss | Gradient boosting, random forests, neural networks |
| **T4** | Training that continues after deployment | Online learners, bandits, adaptive fraud models |
| **T5** | Configuration of a pre-trained foundation model | Prompt bundles, RAG pipelines, fine-tune-free LLM applications |
| **T6** | Opaque — P exists, you cannot see it | Vendor black boxes, licensed scoring services |
| **T7** | Expert elicitation | Judgemental overlays, expert-weighted scorecards, scenario narratives |
| **T8** | Authorship — a human wrote the parameters | Credit policy rulebooks, deterministic eligibility logic |

## Why it is derived, never declared

The class is computed from `parameter_kind` and `fit_procedure`, plus whether
the model is adaptive and whether the parameters are accessible. You cannot
send `"trainability_class": "T0"`.

The reason is behavioural. A declared class is a field somebody fills in, and
the value they fill in is the one that asks least of them. "It's T0, so there is
no training data to produce" is an appealing sentence, and it is not one an
owner should be able to write for a gradient boosting model.

Derivation moves the lie one step back, to `parameter_kind` and
`fit_procedure` — which are checkable against the artifact, and which the
version's schema and contract have to be consistent with.

## What the class actually changes

**What evidence is appropriate.** Asking a T0 analytic pricer for a training set
is a *type error*, not a missing document. MAYA will not ask for one, and will
not record its absence as a gap. Conversely a T3 model with no training data
lineage is a genuine gap and is recorded as one.

**What operations are admissible.** You cannot `fit` a T0 model — there is
nothing to fit. A warrant requesting it is refused at the grammar level.

**What monitoring makes sense.** A T1 calibrated model is re-solved daily, so
"parameter drift" is normal operation rather than an alert; what matters is
calibration error against the instruments. A T3 model's parameters should not
move at all between retrains, so any movement is an incident.

**Where the risk sits.** T6 opacity is a control problem: you compensate with
outcomes analysis and benchmarking, because you cannot inspect. T4 adaptivity is
a change-control problem: the model in production is not the model that was
validated, by design.

## The uncomfortable one

**Most of a bank's model estate is not T3.** Counting by artifact, the T0/T1
population — pricing, capital, accrual, curve construction — usually dwarfs the
machine-learned population, and it is systematically under-governed because the
inventory was built for models that have training sets.

That inversion is the argument for classifying this way rather than asking
"is it AI?".
