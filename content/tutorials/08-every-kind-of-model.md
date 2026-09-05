---
title: Every kind of model, worked
slug: every-kind-of-model
section: The platform
order: 47
icon: collection
summary: The map to seven end-to-end tutorials — linear regression, GARCH, a closed-form pricer, Hull–White calibration, a Monte Carlo engine, a neural network and an LLM application. One definition, seven shapes, and the differences are entirely in how the parameter object is inhabited. Start here, then follow the one you have to build.
audience: Data scientists, Model developers, Quants
---

# Every kind of model, worked

A reasonable objection to all of this: *a neural network is not an equation, and
an LLM is not a set of coefficients. How do those live in a register built
around* `f : P ⊗ X → D(Y)`?

They live in it comfortably, and this page shows each one. The point of
separating `P` from `f` is that the differences between these artefacts turn out
to be differences in **how the parameter object is inhabited** — not differences
in what a model *is*.

Here is the whole answer on one page:

| Model | `P` is | How `P` is filled | `parameter_kind` | `fit_procedure` | Class |
|---|---|---|---|---|---|
| Black–Scholes | *empty* | it isn't — nothing to fill | `none` | `none` | T0 |
| Linear regression | coefficients | a statistical estimator | `estimated_coefficients` | `estimate` | T3 |
| GARCH(1,1) | ω, α, β | maximum likelihood | `estimated_coefficients` | `estimate` | T3 |
| Hull–White | mean reversion, vol | a solver, against market quotes | `calibration_set` | `calibrate` | T1 |
| Monte Carlo XVA | the model parameters + seed + path count | calibration plus configuration | `calibration_set` | `calibrate` | T1 |
| Neural network | **weights** — millions of them | a training run | `learned_weights` | `train` | T4 |
| LLM application | base model + prompt + corpus + tools | configuration and retrieval | `llm_configuration` | `configure` | T5 |
| Vendor score | exists, unreachable | somebody else's problem | `opaque` | `none` | T6 |

**You never declare the class.** It is derived from the two columns before it.
That is why asking a closed-form pricer for its training set is a type error
rather than an empty field, and why a rule set is not a second-class citizen
that had to be squeezed into a schema designed for gradient descent.

---

## Seven tutorials, one for each

Each of these is a **complete** walkthrough — register, load data, warrant, fit
or configure, review, approve, promote, serve and monitor. They are meant to be
followed rather than skimmed, and each one ends by naming what it taught that
the previous could not.

| Tutorial | Read it for |
|---|---|
| **[A linear regression](/tutorials/linear-regression-end-to-end)** | the whole path at its simplest — every control, nothing exotic. Do this one first. |
| **[A GARCH volatility model](/tutorials/garch-end-to-end)** | an iterative fit that can fail while looking like it succeeded, and a score that needs **state**. ARMA and ARIMA sit in this slot. |
| **[A derivative pricing model](/tutorials/derivative-pricing-end-to-end)** | what governance means when there is **nothing to fit** — and why asking a T0 for its training set is a type error, not an empty field. |
| **[A calibrated term-structure model](/tutorials/hull-white-end-to-end)** | daily recalibration, and approval **by exception** rather than by committee. |
| **[A Monte Carlo engine](/tutorials/monte-carlo-end-to-end)** | the seed as a parameter, and the patch release that passed eleven thousand tests and broke the netting sets. |
| **[A neural network](/tutorials/neural-network-end-to-end)** | where `P` becomes an **artifact** — the content-addressed store, and which formats run code when they load. |
| **[An LLM application](/tutorials/llm-end-to-end)** | where the base model is somebody else's and moves without telling you, and `P` is the assembly you configured. |

If you want the platform mechanics rather than the model shapes, read
[the whole path](/tutorials/the-whole-path) instead: one example, every
subsystem, in order.

---

## Artefacts that remember

Three of the seven above carry **state** across calls: the Monte Carlo engine
(its RNG), the GARCH scorer (last shock and variance), and an agentic LLM
application (its conversation).

This matters more than it looks. **If a thing remembers, you cannot learn what it
does by asking it questions one at a time.** Two systems can answer every single
question identically and still be different systems, because what distinguishes
them is how the answers relate to each other.

The consequence is concrete. A "patch release" claims nothing observable
changed, and for a stateful artefact **a test set of individual cases cannot
support that claim at any size**.

> A counterparty simulation engine seeds its RNG once at start-up. Somebody
> changes it to seed per request — a pure performance fix. Eleven thousand
> single-trade regression tests pass, because a single valuation averages over
> paths either way. What changed is the *correlation between* valuations in one
> batch: two trades in a netting set were simulated against common paths and now
> are not. Exposure moves materially, in the direction of understatement.
>
> No number of tests of that shape could have caught it. Every element of the
> suite had length one.

So: for anything that carries state, your probe set must be **sequences**, and
MAYA records what the state was rather than letting the engine invent it.

---

## Choosing the right shape

If you are registering something and are not sure which row of the table it is,
ask the questions in this order:

1. **Is there anything to fit?** No → `none`, T0. You are done.
2. **Can you see the parameters?** No → `opaque`, T6. Your only evidence is
   behavioural: compare its outputs against your realised outcomes.
3. **Are they solved against market instruments, repeatedly?** →
   `calibration_set`, `calibrate`.
4. **Are they estimated from a historical sample?** → `estimated_coefficients`
   if there are few, `learned_weights` if there are many. The line is whether
   they are a record or an artifact, not whether the method is called machine
   learning.
5. **Are they a configuration around somebody else's model?** →
   `llm_configuration`.
6. **Did people decide them in a room?** → `elicited_weights`, `elicit`. This is
   a real category and it deserves a real answer rather than a spreadsheet.

The classification is derived, so getting steps 3–6 right is what matters; the
class follows.
