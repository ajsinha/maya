---
title: Every kind of model, worked
slug: every-kind-of-model
section: The platform
order: 47
icon: collection
summary: A decision procedure rather than a taxonomy. Two facts about a kernel, asked in one order, and the trainability class falls out — then seven complete tutorials, one per shape, and a note on the three of them that remember what happened last time.
audience: Data scientists, Model developers, Quants
---

# Every kind of model, worked

A reasonable objection to all of this: *a neural network is not an equation, and
an LLM is not a set of coefficients. How do those live in a register built
around* `f : P ⊗ X → D(Y)`?

Comfortably, and this page shows how. Separating `P` from `f` turns the
differences between these artefacts into differences in **how the parameter
object is inhabited** — not into differences in what a model *is*.

The consequence is that classifying a model is not a judgement call. It is a
decision procedure over two fields, and neither of them is a category anybody
attached.

---

## The procedure

You answer two questions on the version's kernel. `core/domain/algebra.py`
computes the rest, and nothing anywhere may declare the result.

```
1.  Can the governing party see the parameters at all?
        no  ─────────────────────────────────────────────────→  T6
2.  Is P the terminal object — is there anything to fit?
        no, nothing ─────────────────────────────────────────→  T0
3.  Otherwise, how is P filled?  (fit_procedure)
        calibrate ──────────────────────────────────────────→  T1
        estimate  ──────────────────────────────────────────→  T2
        train     ── and adaptive: false ───────────────────→  T3
                  └─ and adaptive: true  ───────────────────→  T4
        configure ──────────────────────────────────────────→  T5
        elicit    ──────────────────────────────────────────→  T7
        author    ──────────────────────────────────────────→  T8
```

Three things about that procedure are worth stating plainly.

**`opaque` wins first.** A vendor black box is T6 whatever `fit_procedure` says,
because the class describes what *you* can do with `P`, and the answer is
nothing.

**`none` wins second.** `parameter_kind: none` means `P` is the terminal object,
so there is no point of `P` to move to, whatever anybody wrote in
`fit_procedure`.

**T4 is `train` plus one more bit.** `adaptive: true` on the kernel says the
model updates in flight. It is not a separate parameter kind and not a
judgement about how clever the model is; it is a fact about whether `P` moves
without a fit warrant, which is why it earns its own class.

`elicited_weights` × `elicit` is **T7** and `rule_set` × `author` is **T8**.
Both are real categories that deserve a real answer rather than a spreadsheet
with a policy document beside it.

---

## The estate on one page

| Model | `P` is | How `P` is filled | `parameter_kind` | `fit_procedure` | Class |
|---|---|---|---|---|---|
| Black–Scholes | *empty* | it isn't — nothing to fill | `none` | `none` | **T0** |
| Hull–White | mean reversion, vol | a solver, against market quotes | `calibration_set` | `calibrate` | **T1** |
| Monte Carlo XVA | model parameters, seed, path count | calibration plus configuration | `calibration_set` | `calibrate` | **T1** |
| Linear regression | coefficients | a statistical estimator | `estimated_coefficients` | `estimate` | **T2** |
| GARCH(1,1) | ω, α, β | maximum likelihood | `estimated_coefficients` | `estimate` | **T2** |
| Neural network | **weights** — millions | a training run | `learned_weights` | `train` | **T3** |
| …one that updates in flight | the same weights, moving | an online update | `learned_weights` | `train` + `adaptive` | **T4** |
| LLM application | base model, prompt, corpus, tools | configuration and retrieval | `llm_configuration` | `configure` | **T5** |
| Vendor score | exists, unreachable | somebody else's problem | `opaque` | *anything* | **T6** |
| Expert overlay | weights from a committee | a room full of people | `elicited_weights` | `elicit` | **T7** |
| Credit policy rulebook | the rules | somebody wrote them | `rule_set` | `author` | **T8** |

**You never declare the class.** It is derived from the two columns before it,
which is why asking a closed-form pricer for its training set is a *type error*
rather than an empty field, and why a rule set is not a second-class citizen
squeezed into a schema designed for gradient descent.

It is also why the platform's refusals can be laws rather than a policy
document. **L-W1** refuses `fit` on T0 and T6 because that is what those classes
*mean*; **L-W11** applies to a calibration because `parameters.kind` says so;
**L-W12** applies wherever the parameters live inside an artifact, which is
independent of the class and catches a PMML scorecard as readily as a network.

---

## Seven tutorials, one for each

Each is a **complete** walkthrough — register, load data, warrant, fit or
configure, review, approve, promote, serve and monitor. Each ends by naming what
it taught that the previous one could not.

| Tutorial | Read it for |
|---|---|
| **[A linear regression](/tutorials/linear-regression-end-to-end)** | the whole path at its simplest — every control, nothing exotic. Do this one first |
| **[A GARCH volatility model](/tutorials/garch-end-to-end)** | an iterative fit that can fail while looking as though it succeeded, and a score that needs **state**. ARMA and ARIMA sit in this slot |
| **[A derivative pricing model](/tutorials/derivative-pricing-end-to-end)** | what governance means when there is **nothing to fit** — and why asking a T0 for its training set is a type error rather than an empty field |
| **[A calibrated term-structure model](/tutorials/hull-white-end-to-end)** | daily recalibration, approval **by exception** rather than by committee, and the `as_of` that L-W11 refuses to let you leave out |
| **[A Monte Carlo engine](/tutorials/monte-carlo-end-to-end)** | the seed as a parameter, and the patch release that passed eleven thousand tests and broke the netting sets |
| **[A neural network](/tutorials/neural-network-end-to-end)** | where `P` becomes an **artifact** — the content-addressed store, which formats run code when they load, and L-W12 |
| **[An LLM application](/tutorials/llm-end-to-end)** | where the base model is somebody else's and moves without telling you, and `P` is the assembly you configured |

Want the platform mechanics rather than the model shapes? Read [the whole
path](/tutorials/the-whole-path) instead: one example, every subsystem, in
order.

---

## What the class does *not* decide

Worth being clear, because the table above invites the opposite reading.

The trainability class does not select a document shape. There is **one** warrant
document across all of them — see [warrants by model
family](/tutorials/warrants-by-family) — and what differs is which laws refuse.
It does not select a validation checklist either; it changes which evidence is
coherent to ask for.

And it does not set the tier. Complexity is one input alongside materiality,
and neither dominates: a T0 pricer on a two-billion-dollar regulatory-capital
book and a T3 network on a twenty-million-dollar commercial one both come back
**Tier 2**, by different routes. The tier is derived as well, and from different
facts — see [risk tiering](/help/risk-tiering) for the two lattices and why
there is no single score.

---

## Artefacts that remember

Three of the seven carry **state** across calls: the Monte Carlo engine (its
RNG), the GARCH scorer (last shock and last variance), and an agentic LLM
application (its conversation).

This matters more than it looks. **If a thing remembers, you cannot learn what
it does by asking it questions one at a time.** Two systems can answer every
individual question identically and still be different systems, because what
distinguishes them is how the answers relate to each other.

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

So for anything that carries state, the probe set must be **sequences**, and
MAYA records what the state was rather than letting the engine invent it — a run
that will not say what state it started from is a run nobody can repeat.
`state_required` is the refusal, and it is a 422.

---

## If you are still not sure which row you are on

Ask in this order. Steps 3 to 6 are the ones that matter; the class follows.

1. **Is there anything to fit?** No → `none`, T0. You are done.
2. **Can you see the parameters?** No → `opaque`, T6. Your only evidence is
   behavioural: compare its outputs against your realised outcomes.
3. **Are they solved against market instruments, repeatedly?** →
   `calibration_set`, `calibrate`.
4. **Are they estimated from a historical sample?** → `estimated_coefficients`
   if there are few, `learned_weights` if there are many. The line is whether
   they are a record or a file — `MAX_INLINE_VALUES` is 4,096 — not whether the
   method is called machine learning.
5. **Are they a configuration around somebody else's model?** →
   `llm_configuration`, `configure`.
6. **Did people decide them in a room?** → `elicited_weights`, `elicit`. Did one
   person write them down as rules? → `rule_set`, `author`.

And if `P` is non-terminal but `fit_procedure` is `none`, the class comes back
**T0** — because nothing in the kernel says how those parameters got there, and
a class asserting they were fitted would be asserting something no field
supports. That is not a bug to work around; it is the register telling you the
version is under-specified.
