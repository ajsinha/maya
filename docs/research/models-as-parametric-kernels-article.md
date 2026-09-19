# Models as Parametric Kernels

### An order, an operator and a polynomial — deriving the facts a model governance system otherwise makes somebody type in

> **About this revision (September 2026).** The earlier version of this article described a build of MAYA
> that has since been deleted: the platform was rebuilt from nothing against a new specification, and at
> version 0.3.0 it is a register of features, feature sets, models and the *warrants* that license a model
> to be trained or run. The argument below is unchanged where it stands as mathematics. What changed is
> every claim about the system. Where a section describes what a register *should* do, it now says what
> MAYA 0.3.0 actually does — often less, sometimes differently. [Laws, or it didn't
> happen](#laws-or-it-didnt-happen) gives the register of what runs, and [The system this came out
> of](#the-system-this-came-out-of) describes the system. Three defects were found by writing this revision,
> and all are in it: a check that reads a missing parameter set as "non-trainable", six algebra operators
> that drop the clock the point-in-time argument depends on, and one source type that is read through
> rather than copied.

---

There is a question that sounds trivial and turns out to be the hardest one in the room:

**What is a model?**

Not *which* model. Not *whose*. What *is* one — formally, generally, in a way that covers everything an
organisation actually has to govern?

I spent a while on this and came away convinced that a whole category of expensive software failure traces
back to nobody having a good answer. This is that answer.

But the thing I actually want to argue is narrower and, I think, more useful. Every governance system I have
looked at runs on **facts that somebody typed in**. What kind of model this is. That this version may replace
that one. That this training set is point-in-time correct. That this conclusion rests on that evidence.

Typed-in facts are true at the moment they are typed and never again checked. And it turns out that four of
the most consequential ones don't have to be typed in at all — they fall out of structure you already have,
if you write the structure down.

> **One caveat before we start, because a reviewer caught me on it.** I cite two supervisory texts: the UK's
> SS1/23, in force since 2024, and a 2026 US revision of the model risk guidance. Treat the second more
> carefully than I originally did — it's recent, its status may not be settled wherever and whenever you're
> reading, and an earlier draft narrated it as the settled successor to SR 11-7 without saying so.
>
> It matters less than it looks. Everything below is readable off SR 11-7 and SS1/23 alone: SR 11-7 has
> carried the aggregate-risk expectation, the independent-challenge requirement and the inventory obligation
> since 2011. And the definitional narrowness I use to motivate "one estate, several scopes" is a *recurring*
> feature of model-risk definitions, not a property of one revision — SR 11-7's own "quantitative method
> applying statistical, economic, financial, or mathematical theories" already sits awkwardly against a
> deterministic rule set you nonetheless have to govern, and against a language model that governs nothing
> and drafts everything. Where your jurisdiction's text differs, the substitution is mechanical, and the
> section on regimes exists precisely because it should be.

That's the paper. A definition, an order, an operator and a polynomial. And then, at the end, something I
didn't go looking for: the line between *derived* and *declared* turns out to be exactly the line between
where you can safely let a machine do the work and where you can't.

---

## The population problem

Picture the quantitative assets inside a large bank.

There is a Black–Scholes implementation. Its parameters come from financial theory. It has never been trained
on anything and never will be.

There is a volatility surface, re-solved against market quotes every morning before the desk opens. Its
parameters change daily; its *methodology* changes maybe once every three years.

There is a credit scorecard refitted annually. A gradient-boosted fraud model retrained weekly. An adaptive
threshold that updates itself continuously in production with no human in the loop.

There is a language model drafting suspicious-activity narratives, whose "parameters" are a base model, a
prompt, a document corpus and a set of tools.

There is a third-party credit score whose internals are contractually unavailable and always will be.

There is a country-risk rating scheme whose weights were set by a committee of nine people in a room.

And there are several thousand spreadsheets.

Every one has to appear in one inventory, be classified by how much damage it could do, be reviewed by
someone independent, be monitored, documented and change-controlled. In most jurisdictions that is
supervisory expectation; in some it is law.

Now go and look at the tools built to do this. They split with unusual cleanliness. **Governance platforms**
have beautiful workflow and no access to the artefacts — they record assertions *about* things they cannot
see. **ML platforms** manage artefacts beautifully and have no representation of materiality, approved use,
independent challenge or remediation. Each solves half.

I don't think that split is a product-strategy accident. I think it's what happens when a field has no
definition to organise around.

---

## The real problem: declared facts rot

The usual way to describe what goes wrong is a list of four pathologies. Let me give you a sharper version,
because the sharper version points at the fix.

In each case, **a fact that could have been derived from structure was instead declared by a person.**

**Kind is declared.** A field says this is "an ML model" or "a pricer" or "other". Downstream, evidence
requirements switch on that field, so the closed-form pricer gets asked for its training dataset. That's not
a missing value — it's a category error, like asking what colour the number seven is. The system has no way
to say so, so someone types "N/A", and within two years the inventory is full of records that mean nothing.
And nothing checks that the artefact declared "rule set" doesn't have forty-two fitted coefficients in it.

**Fit is declared.** "This version can replace that one." "This featureset provides what that model reads."
"This model's output feeds that one." Each is the same claim — *can this thing stand where that thing
stood?* — and in every system I've looked at, each gets its own code path. Four implementations of one
relation. They disagree eventually, and the direction is predictable: **toward permitting more**, because
that's the direction in which nobody files a bug.

**Currency is declared.** The condition under which a training row is admissible lives inside whatever SQL
somebody wrote. Nothing checks that the SQL implements the condition. And the failure mode — using a fact
before it was knowable — is invisible to every performance metric, because it *improves* them.

**Support is declared.** The evidence log records, in prose, that a version was validated. Nothing in the
record says what the conclusion rests on. So nothing can compute whether a cited set actually suffices, or
what the cheapest route to closing a gap is, or whether a document has gone stale. The claim is
unfalsifiable, which is the opposite of what assurance means.

Four declarations. Four things that stop being true quietly.

---

## The definition

Here it is, and the payoff is worth the two lines of notation.

> A **model** is a parameter object `P`, an input object `X`, an output object `Y`, and a map
>
> ```
> f : P ⊗ X → D(Y)
> ```
>
> that consumes parameters and input and produces output — possibly stochastically.

In the jargon: a morphism in `Para(Stoch)` — a parametric map in a *Markov category*, where morphisms behave
like probability kernels rather than plain functions.

The whole trick is separating `P` from `f`.

Because now you stop asking *what kind of model is this?* — a question with no principled answer — and start
asking the one that actually distinguishes your artefacts:

**How does the parameter object get filled in?**

| The artefact | Its `P` | How `P` gets filled | Class |
|---|---|---|---|
| Black–Scholes | *empty* — the terminal object | it doesn't; there's nothing to fill | T0 |
| Volatility surface | a calibration set | a solver, against market quotes, daily | T1 |
| Credit scorecard | coefficients | a statistical estimator, annually | T2 |
| Fraud classifier | weights | a training run, weekly | T3 |
| Adaptive threshold | weights that move in production | a training run, then the model itself | T4 |
| LLM application | base model + prompt + corpus + tools | configuration and retrieval | T5 |
| Vendor score | *exists, but you cannot see it* | someone else's problem, unavailable | T6 |
| Committee scorecard | weights a panel agreed | elicitation from people | T7 |
| Rule set | the rules | somebody wrote them down | T8 |

Look at what happened. The taxonomy people argue about endlessly — is this an ML model, is a pricer a model,
does a rule set count — isn't a taxonomy of *things*. It's a taxonomy of *how one slot gets filled*.

And the two extremes are the interesting ones:

- **Black–Scholes is the case where `P` is the terminal object.** Not a degenerate model. Not a special case.
  `P ⊗ X ≅ X`, so the model is just a kernel, and the fitting question is *vacuous*. The system can now say,
  precisely: asking this artefact for a training set is a **type error**.
- **The vendor score is the case where `P` exists but is inaccessible.** All you can observe is the
  composite. Which is *exactly why* the only evidence you will ever get about a vendor model is behavioural —
  you compare its outputs against your own realised outcomes. That isn't a workaround. It's what the
  mathematics leaves available.

Here is the part that matters for the argument, though: **this class should be computed, never stored.** No
field. Nobody types T3. You give the register two facts about how the parameters came to be, and it works out
the rest — and derives from that what evidence it is entitled to ask you for.

*MAYA 0.3.0 does much less than this.* It records a model's **kind** — `formula`, `black_box`, `composite`
or `vendor` — and that kind is declared by whoever registers it. It derives exactly one row of the table: a
model whose formula declares no parameter input can be licensed to run without a training warrant, and one
that declares any cannot. T6 survives as the declared kind `vendor`, whose bundle says plainly that it
cannot be re-executed. The rest of the classification is argument, not software.

### The honest bit

The class derives from three things: is `P` empty, is `P` reachable, and what procedure filled it. The first
two are properties of the artefact. The third is still something a person records.

So the derivation *shrinks* the declared surface — from a nine-valued taxonomy with nine ways to be wrong,
down to one fact about what act produced the numbers — rather than eliminating it. And it shrinks it in a
place where being wrong is harder to hide, because the shape of `P` and the procedure that filled it are
recorded separately and can be compared.

Two limits of that are worth stating plainly. Nothing cross-checks the two declarations against each other,
so "learned weights" filled by "elicitation from a committee" is accepted. And where the fit procedure is not
recorded at all, the fallback is **T0** — so an artefact whose parameters exist but whose provenance nobody
wrote down is treated like a closed-form pricer, and exempted from fitting evidence. Both are the failure
direction this whole article is about, one level in: where a derivation still reads a declaration, the
declaration can still be missing, and the safe default is the strict one rather than the permissive one.

MAYA 0.3.0 has exactly this defect, in the one row it derives. Its "no parameters, no training warrant"
check reads the parameters only of a model whose formula has a closed-form body. A black box, a vendor
model or a composite passes as "non-trainable" whatever parameters it declares — and so does an execution
warrant drawn from a training warrant without naming a parameter set. I found it writing this revision,
with a probe that created and approved both. The training warrant is stricter (it won't seal without an
approved parameter set), so the gap is at the second licence, not the first. It is reported, not yet fixed.

---

## The filing cabinet, and why the labels have to be computed

Here is the second thing the derived class buys, and I think it's the sharpest small result in the whole
account.

Almost everything in a governance system is a family indexed by kind. What evidence this needs. What
lifecycle it follows. What can usefully be monitored on it. What documents come out of it. Picture a filing
cabinet where each drawer holds one kind of artefact and comes with its own set of forms.

The bad design writes the list of drawers into the cabinet's frame — "kind" as a column with fixed values —
so adding a drawer means rebuilding the cabinet. The good design makes drawers independent, so adding one is
just adding one. That's a **fibration**, and it comes with a small theorem: adding a drawer cannot disturb
what's in any existing drawer. Which is what lets you promise to support kinds of artefact nobody has
invented yet.

But there's a second requirement, and it's the one usually missing: **every drawer has to actually contain
its forms.** A drawer with no forms is worse than an absent drawer, because the cabinet looks complete. So
you want a check — no empty drawers — and you want it to run before the cabinet is opened rather than when
somebody reaches into one.

Now the interesting part. **What are the drawers labelled?**

Say the label is a free-text field someone types — "credit", "rates", "c". You now have two options and both
of them fail:

- **Close the vocabulary.** Only these labels are allowed. But then adding a new kind means editing the
  allowed list, which is a release — and "adding a kind is just supplying a drawer" has stopped being true.
- **Leave it open.** Anyone can type anything. But then the completeness check can only look at the labels
  it knows about, and somebody types a label nobody registered. The check passes. The cabinet is not
  complete. **That's a check that reports success.**

There's no third option, as long as the label is *typed in*.

Unless the label is **computed**. An index derived from the artefact itself can't be typed wrong, can't be
extended by accident, and can't disagree with the thing it indexes. The set of possible labels is fixed, so
"no empty drawers" quantifies over all of them — and adding a kind is still just supplying a drawer.

Which is exactly what T0–T8 is. The trainability class isn't only a nicer way to talk about the taxonomy;
it's the only kind of label that lets the filing cabinet make both of its promises at once. The
organisational label — what desk owns this, what business it serves — keeps its real job, which is grouping
and reporting, and indexes nothing.

I find this satisfying because it's the article's own thesis turned on the article's own machinery.
*Derived, not declared* isn't just better hygiene for the facts in the register. It's a structural
requirement on the thing that organises them.

(MAYA 0.3.0 has no such cabinet. Its evidence requirements vary by *object type* — feature, feature set,
model, warrant — through the workflow policy's named checks, and nothing is indexed by model kind. Its
declared four-valued kind is the "closed vocabulary" horn above, harmless only because no drawer hangs off
it.)

### The monitor that ran for two years and meant nothing

A discount-curve pricer is registered, and somebody attaches a **performance** monitor — discrimination
against realised outcomes, evaluated monthly. It runs. It never fires. On the estate screen the model is
green and monitored.

But the pricer has no parameters and no fitted relationship to outcomes. Discrimination is not a question
about it. The monitor wasn't failing to detect anything; there was nothing of that kind to detect.

And that is *worse* than having no monitor at all, because an absent monitor shows up in the coverage
worklist and a meaningless one doesn't. It reads as coverage.

With a drawer per class, the monitor kind gets checked against what that class can actually answer, and the
attachment is refused — naming what *is* answerable for a T0 artefact instead: whether the inputs are still
inside the range it was benchmarked over. That's not a restriction on what validators may do. It's the
drawer being read rather than merely held.

---

## When you can read the parameters

For most classes, `P` is a pile of numbers and the interesting questions about it are statistical. For **T8**
— the rule sets, the deterministic policies — `P` is something a person wrote down. And that changes what you
can ask, because a rule set has *logical* structure. Questions about it can be **decided** rather than
estimated.

The condition for that is a restriction, and the restriction is the whole point. Write rules in a general
expression language and questions about them become questions about programs, which is to say unanswerable.
Restrict a condition to comparisons on declared fields combined with and/or/not — no arithmetic, no function
calls, no free text — and each rule reduces to a set of intervals and permitted values per field. Emptiness
and containment become arithmetic.

Then this becomes decidable, and it matters more than it sounds:

> Rule sets are evaluated **first match wins**. So a rule that an earlier rule already covers **can never
> fire** — and nothing about reading the document tells you that.

Somebody believes that rule is in force. It appears in the model card. It gets cited in a committee paper. It
survives every review — because a rule that never fires also never produces a wrong answer. That is the same
pattern as the monitor above and the false-positive verifier earlier: **a control reporting success while
doing nothing.** Arrived at from the model's side rather than the platform's. No spreadsheet will ever tell
you this.

**And here is the exact promise, which is narrower than you might want.** The analysis is *sound*: when it
says a rule is unreachable, the rule is unreachable — it never cries wolf, because a check that produces
false alarms is a check somebody switches off, and then the real ones go with it. It is *incomplete*: it
catches a rule shadowed by a **single** earlier rule, not one shadowed by two earlier rules working together
(`ltv > 0.8` and `ltv <= 0.8` between them cover everything, and neither covers anything on its own).

Full coverage checking is satisfiability over the theory — decidable here, but it needs a solver, and a
solver inside a governance platform is a dependency whose failure modes nobody in the bank can debug.

So the claim made is *"no rule is shadowed by any single earlier rule"*, not *"no rule is unreachable"*.
Stating which is the difference between a check people trust and a check people turn off — and a check that
claims more than it delivers is precisely the failure this analysis exists to find.

(Rule sets are not a model kind in MAYA 0.3.0, and this analysis is not in it. The nearest thing is the
workflow policy editor, which refuses an unreachable *state* at edit time — reachability over a state
machine, not over rules.)

---

## One order, for four questions

Remember the four places that ask *can this stand where that stood?* Here they are again:

| Where | What it asks |
|---|---|
| An alias move | may this replacement version stand where the incumbent stood? |
| A fit warrant | does this featureset provide what the kernel says it reads? |
| A contract | does this operating contract refine the one it replaces? |
| A dependency edge | does what the source produces arrive where the target reads it? |

Four questions, and the tempting thing is to answer each where it is asked. The fourth is the one that
shows why that is expensive: an unchecked dependency edge is not a weak check, it is a **drawing**, and every
blast radius computed over it is computed over a graph nobody validated.

So: write the relation once.

> **`A ⊑ B`** iff `A` has every field `B` has, each accepting **at least** what `B`'s did.

Read it as *A can stand in for B*. `A` may have extra fields — nobody has to look at them. Each shared field
must accept at least what `B`'s accepted, because a replacement that rejects an input its predecessor took is
a replacement that breaks a caller.

**This direction is counterintuitive, and reliably so — which is the reason to write it down as an order.**
The word "refinement" suggests narrowing, and a subtype *is* narrower in the set of values it denotes. But a
schema here is a set of *inputs a slot will accept*, and standing in for something means accepting at least
what it accepted. So wider is fine and narrower regresses — the reverse of what the word invites you to
think.

Both readings of "narrower" are easy to hold at once and impossible to hold consistently. And the failure the
wrong one produces is silent: state the rule in the intuitive direction and you admit exactly the
replacements that break callers.

### It's a lattice, and the lattice does work

Schemas ordered this way have meets and joins:

| | | |
|---|---|---|
| **meet** `A ⊓ B` | the **union** of the fields, each widened to accept both | the schema that can stand in for either — what a featureset must provide to serve two models at once |
| **join** `A ⊔ B` | the **intersection**, narrowed to what both accepted | what two schemas *agree* on — what a consumer of either may rely on |
| **top** | the empty schema | it demands nothing, so everything can stand in for it |

There's no bottom, and saying so matters: a least element would have to carry every field name that could
ever exist. It's a lattice on each finite fragment, which is the only fragment anything ever inhabits.

The meet is the one that earns its keep. *"Can one featureset serve both these models?"* was previously not
even askable; now it's `S(F) ⊑ in(k₁) ⊓ in(k₂)`, one line.

**And the meet is partial — informatively so.** Two schemas whose shared slot carries two different types
have *no* meet, because no schema accepts both a number and a string in one slot. So the honest answer to
"can one featureset serve both?" is **no, and here is the slot**. The implementation raises a named error
carrying the conflicting field and both types, rather than returning nothing — because the caller who asks
has a decision to make, and a `None` threaded through three layers becomes a silent empty schema somewhere
downstream.

One thing to be precise about, since this article is about claims that go unchecked — and here the rebuild
reversed the old build. The old build had the meet implemented and law-tested and **no production path
called it**. MAYA 0.3.0 has the meet deployed and *not* law-tested: a composite model's input contract is the
union of its members' contracts, and two members wanting one attribute at two different types is refused
with the attribute, both types and both members named. That is "can one featureset serve both?" in daily
use, on names and types.

What 0.3.0 does not have is the order as one function. Three routines answer fragments of it — a version
classifier (*breaking*, *behavioral*, *additive*), a warrant's contract check, and that composite union —
and, exactly as this section predicts, they already disagree in one small place: the warrant check lets any
numeric attribute stand in for a `float64` input, while the other two demand the identical type. Defensible
for a number. Not a decision anyone made in one place. Bounds and nullability are compared nowhere, and there
is no join.

### A refusal that names the remedy

When `A ⊑ B` fails, it fails in exactly two ways, and they're kept apart:

- **missing** — names `B` has that `A` doesn't. Somebody bound the wrong featureset.
- **narrowed** — names `A` has that accept less than `B`'s did. Somebody tightened a constraint without
  noticing it was a promise.

Different mistakes, different fixes. A refusal that says "incompatible" is a message. A refusal that says
*"does not provide `turnover`; accepts less than before at `dscr`"* is an instruction.

That's a small thing that changes what a control feels like to be on the receiving end of.

---

## Wiring is a type-check, not a drawing

An edge saying *A's output is read by B* is a claim about types. Recorded and never checked, it's a picture:
the blast radius follows edges nobody validated, a composite has no derived schema, and there's nothing to
quantify the interaction premium over.

Checked, it's composition — and the check is the same order as everything else:

```
refines( output_schema(source), input_schema(target) )
```

| | |
|---|---|
| extra outputs | fine — simply unread |
| a missing output | refused: a wire to nowhere, with the field named |
| a narrowed output | refused, the same regression an alias move names, one level out |
| either end has no version yet | recorded **without** a type check, and the log says so |
| `challenger_of`, `benchmark_for` | not typed: they record how somebody *thinks* about a model. There's no wire |
| `calibrated_by` | propagates but doesn't compose — solving parameters isn't handing an output to an input |

And the composite's schema is **derived**: the source's inputs, the target's outputs. Not declared — because a
composite whose signature somebody wrote down is a composite that can disagree with its parts.

**What MAYA 0.3.0 actually does here is different, and instructive.** It checks no model-to-model edge at
all — it doesn't record one model feeding another outside a composite. Instead it makes the composition
*itself* the governed object. A composite model (ensemble, pipeline, router, residual or hierarchical) is a
model version with its own specification document, its own approval, **one** parameter set namespaced by
member (`base.sigma`, `skew.beta`) and **one** warrant over one feature set.

The old build took the other defensible position: it authorised a *chain* of separately approved models in
one call, signed nothing for the whole, and argued that three people had approved three models and nobody had
approved the composition. The rebuild meets that objection rather than avoiding it — there *is* an approval
for the composition, because the composition is what was submitted. The cost is that a composite is a new
thing to approve even when every member already is.

Two details carry the theory across. **A composite's maturity is capped at its lowest member's** — a meet on
a finite chain, which composes, and which is exactly what the impossibility result below permits and no
more. And **every member below the target maturity is named, not the first**: a refusal that reveals one
obstacle at a time is a refusal whose author hasn't computed the obstruction set.

What composes is the order, not the number. MAYA can say *this composite is no more mature than its least
mature member*. It cannot say *this composite is 0.83 risky*, and the reason is a theorem, not a backlog
item.

**A concrete one.** An ECL stack records that a PD model feeds a provisioning engine. Both entries have
existed for two years; the edge is on the diagram in every committee pack. The PD model produces `pd_12m`.
The provisioning engine reads `pd_lifetime`. Nobody ever wired them — an adapter in between computes one from
the other using a term structure that belongs to a third model, which isn't in the register at all.

Unchecked, the register reports a two-node dependency that is wrong in both directions: it claims a change to
the PD model reaches provisioning directly, and it omits the term structure entirely. Checked, the edge is
refused at the moment somebody records it, with `pd_lifetime` named — and the conversation that follows is
the one that discovers the third model.

### On the name

In the old build the model-to-model relation was first called `feeds`, and that is wrong in a bank
specifically. A *feed* there means market data, a reference file, a nightly drop. So "A feeds B" read as
though the platform consumed or produced one, and it did neither: the edge was a statement about two entries
in a register, describing a wire that somebody else's engine carries. It was renamed `input_to`. The rebuild
chose its central word — **warrant** — with the same care: a permission with a holder, a scope and an expiry,
not a record of what happened.

Worth a paragraph because naming is part of the formalism, not decoration around it. A formal account whose
terms are read wrongly by its audience has a defect, and the defect is in the account.

---

## What doesn't compose: aggregate risk

Supervisory guidance has said, for fifteen years and in almost identical words across jurisdictions, that you
must assess model risk *individually and in aggregate*, and that aggregate risk "reflects interactions and
dependencies among models; reliance on common assumptions, data, or methodologies."

Everyone nods at this. Almost nobody implements it. In practice, aggregate risk gets computed as the maximum
— or the join — of the component ratings.

That practice is provably wrong, and the proof is three lines.

Take a curve model `A` and two pricers `B` and `C`.

- **Network 1:** `A`'s output is copied and read by both `B` and `C`.
- **Network 2:** `A` into `B`, and a *separate, independently built* curve `A′` into `C`.

The component ratings are identical between the two. Same three values. So any scheme computing the aggregate
as a function of the component ratings alone gives both networks **the same answer**.

But they are obviously not equally risky. In Network 1, one failure takes down both outputs. In Network 2,
one failure takes down one. That is the entire concept of concentration risk, and the standard method is
structurally blind to it.

So: *no aggregate risk measure can be both sensitive to shared dependency and computed compositionally from
its parts.* Pick one. The regulators explicitly want the first, so the second has to go.

Now the bit that made me sit up. **What is the difference between the two networks?** Exactly one thing.
Network 1 *copies* `A`'s output. Network 2 doesn't.

Shared dependency **is** the copy operation.

Which is why the choice of setting matters in a way that's usually invisible. In an ordinary Cartesian
setting — normal functions, normal composition — copying is free and implicit and structurally invisible. You
literally cannot see the difference between the two networks in the algebra. In a Markov category, copying is
an explicit piece of structure you have to draw. Choosing the setting where probability lives naturally
*also* gives you the setting where concentration risk becomes visible.

**Two things I have to be straight with you about here.**

The first is what's new and what isn't. That aggregate model risk isn't additive, that shared data and shared
assumptions create concentration, and that model interdependency needs its own analysis — all of that is
established practice and established supervisory language, and dependency-aware risk aggregation has a long
quantitative history. What I'm claiming is the **diagnosis**: that the obstruction isn't a modelling
difficulty you approximate away with a better correlation assumption, it's the copy map, so it's structural —
and that this gives you a sharp statement of what a correct aggregate *cannot be*. That's a constraint on
candidate measures, not a measure. Whether it earns its formalism against the concentration analyses that
already exist is an open question and I haven't settled it.

The second is what's built. The theorem is proved and the interaction premium itself is **not computed**.
MAYA 0.3.0 has no risk tier and no aggregate at all. The one assessment it composes is a composite's maturity,
capped at its least mature member — compositional, and making no claim to see concentration. That's what the
theorem permits and no more.

---

## One operator, and the `min` that everything rests on

Everything above is about `P` and about the *shape* of `X`. This section is about `X`'s contents, and it's
where the expensive mistakes actually happen.

### Two clocks, never one

Every fact about the world has two timestamps:

- **`event_ts`** — when the fact was *true*. The borrower's Q1 debt-service ratio has an event time of 31
  March, because that's the period it describes.
- **`ingest_ts`** — when the fact became *known to you*. That figure landed in your warehouse on 20 May,
  because that's when they filed.

A single-timestamp store cannot tell them apart, so it cannot answer the only question that matters when
assembling a training set: *what did we know at the moment the decision was made?*

Watch what happens with a restatement — which is not an edge case, it's a Tuesday. In August the borrower
revises the Q1 figure downward, 1.20 to 0.40. Both rows are true. Both belong in the store. Same event time,
different ingest times. You're building a training set for a decision made in June.

- Read with one clock and you get 0.40, because it's the current value for Q1.
- Read with two and you get 1.20, because 0.40 was not knowable in June.

Train on 0.40 and your model learns to predict defaults using a number that only exists *because* the default
already happened. It scores beautifully in backtest and fails in production, and the failure looks like drift
rather than what it is.

So far, so folklore. Here's the part I think isn't folklore.

### The read is an operator

```
AsOf(R, ℓ, a) = argmax over (event_ts, ingest_ts) of
                { r ∈ R : r.event ≤ ℓ  ∧  r.ingest ≤ min(ℓ, a) }
```

`ℓ` is the label time — the moment of the decision. `a` is the `as_of` — the moment the assembly was built.

Four properties, each a line of proof:

| | |
|---|---|
| **Idempotent** | read the result again and you get it back |
| **Commutes with projection** | which row is admissible is decided on the clocks alone, so reading fewer columns cannot change the choice |
| **Monotone in `a`** | a later read can only *widen* what's admissible; nothing knowable stops being knowable |
| **Saturating at `ℓ`** | **this is the one** |

Because the ingest bound is `min(ℓ, a)` and not `a`, **every `a ≥ ℓ` gives the same answer**. A training row
assembled the day its label matured, and the same row re-assembled a year later, are identical — however many
restatements arrived in between.

That *is* reproducibility. Not a discipline you impose on whoever re-runs the job, not a convention in a
runbook: a property of the operator.

Without the `min`, a re-run quietly *improves* on the original — which is the least useful kind of
reproducibility, because the numbers then agree with nothing, including themselves.

Both bounds are there because they refuse different things. `ℓ` is what the model could have known when the
decision was made. `a` is what the platform could have known when the set was built. Taking the earlier of
the two is what makes the read stable.

### What MAYA actually does: a cut, and a certificate

MAYA 0.3.0 does **not** implement that operator — and working out exactly what it does instead turned out to
be one of the more useful parts of this revision.

It does two simpler things. Every feature row carries an event time and a knowledge time, and a restatement is
a new row, never an overwrite. A resolution names **one** `as_of_known` instant for the whole read and, for
each key, takes the latest row known by then — a plain scalar cut, the thing most bitemporal systems do. Then,
when a training warrant is drawn, MAYA **checks** every row: was its knowledge time on or before its own event
date plus a declared lag (a day, by default)? The answer is written up as a signed **leakage certificate** on
the warrant — *certified*, *certified with exceptions* (every late row justified in writing), or *refused* —
and a warrant whose certificate is refused cannot even be submitted for review.

Two small results relate that to the operator, and I think they're the honest version of the saturation
claim:

- **A clean certificate certifies the operator.** Where the certificate finds no violation, the row the cut
  chose is exactly the row `AsOf` would have chosen. (The cut took the latest row known by `a`; the
  certificate says it was also known by `ℓ`; so it's the latest row known by `min(ℓ, a)`.)
- **Reproducible or refused.** Rebuild that training set later, after more restatements have landed, and for
  every row whose decision date had already passed you get either the *same* row or a *violation* on the
  certificate. Never a silently different number.

That's saturation turned from a property of the read into a property of a signed document. It buys something
the operator can't express — a late fact *accepted*, with a written reason, which a validator sometimes
genuinely needs. And it costs something: the certificate can only see rows that carry a clock. In 0.3.0 two
kinds don't. A row produced by a fill has no knowledge time of its own, although its value was learned when
the row it was copied from was. And six of the feature algebra's operators — projection, composition,
coalescing, aggregation, resampling and case selection — return frames with no knowledge-time column at all,
so a feature derived through any of them is invisible to the certificate. I found both writing this, and
they're reported rather than fixed.

Where MAYA gets its reproducibility guarantee, then, is not the operator but the **pin**: a pin records its
`as_of_known`, and is sealed by a hash of a canonical encoding of its rows, so the same data pinned twice
hashes the same and changed data never does.

### The leak that hides inside a helpful feature

Once you have two clocks, the interesting failures move somewhere subtler.

Suppose you have monthly observations with a gap and you fill it forward from the *next* observation — a
perfectly ordinary thing to do when presenting a history to a person. The value you carried backwards into
March was first observed in April. It's now sitting in a March training row.

The honest fix isn't to forbid it. It's to record *when each filled value actually became available*, so a
value carried backwards keeps April's ingest stamp — and then the ordinary point-in-time rule excludes it
without anybody having to remember a flag.

And here is the trap in that fix: recording the stamp is **necessary and not sufficient**. The rule that
reads it has to bound the ingest clock by the moment of the *decision*. It is very natural to bound it
instead by the moment you built the training set — which is usually "now" — and then the April value walks
into the March row on the grounds that April came before Tuesday. The stamp is telling the truth. Nothing is
reading it against the right bound.

That shape is characteristic of this whole area, and it is why the bound belongs in the operator rather than
in whoever writes the query. The mechanism is right, the mechanism is sound, and the thing consulting the
mechanism asks it a slightly different question than the one it answers.

MAYA 0.3.0 takes the blunter route for the backwards case: `backward_fill` and interpolation are marked
**non-causal**, non-causality propagates through every derivation, and a training warrant over a non-causal
feature set gets a *refused* certificate — and cannot be submitted — unless the developer has explicitly
allowed it *and* written a justification, which then appears on the certificate. The forward case is where it is weaker, as above: a forward-filled row
carries no clock of its own.

### Where the data is allowed to live

That guarantee is usually read as a rule about how to *query* a store. It is also a rule about which
stores may be queried at all, and the second reading is the one that decides an architecture.

The reproducibility holds because the bound is `min(ℓ, a)` over rows that carry both clocks and are
never amended in place. A restatement is a new row with a later ingest time, so the earlier read stays
derivable — that is the entire mechanism. A source that *overwrites* has neither property. An ordinary
warehouse table, a view rebuilt nightly, a file replaced on a schedule: once August's restatement lands,
May's row is gone, and no operator applied at read time can recover what the June decision saw.

The read doesn't fail. It returns 0.40 and says nothing. Which is the exact failure this section exists
to remove, arriving through the back door.

So a platform that binds a featureset slot straight to an external table hasn't implemented the operator.
It has implemented a query that usually agrees with it — indistinguishable until the first restatement,
and indistinguishable again afterwards, because nothing records that they diverged.

The consequence for a build is one line: **copy, don't connect.** An external source is *pulled* — read
once, bitemporalised, written into storage the platform controls as an immutable versioned snapshot — and
models read the snapshot. Connecting is cheaper and gives up the guarantee.

This isn't a preference about storage technology. It's the observation that the operator constrains its
*argument* as much as its definition. An operator defined over rows that can be overwritten is defined
over the wrong object, and the guarantee it appears to give is a guarantee about a table that no longer
exists.

MAYA 0.3.0 follows this for its SQL and Python sources: a pull snapshots the result into the feature's
bitemporal ingest log, and a changed result is a restatement. One source type doesn't: a `delta` source —
another team's Delta table — is read at resolution time and every row is stamped with the moment of the
read. That failure is loud rather than silent (a read as of any earlier instant sees none of those rows,
and the certificate flags them), but it is the connection this section warns against, and nothing tests it.

### The operator has to hold in two other places

The definition above is a statement about one function. But a governance platform doesn't run the training
assembly — some engine elsewhere does — and it checks the assembly with a second computation of its own. So
the operator has to hold in two more places than the one it's defined in, and each is worth stating as its
own requirement.

**The published rule must be the applied rule.** The point-in-time predicate is published as a string, in
every featureset plan and every warrant, because the engines that implement it aren't the ones this system
runs. That string is a **contract**. What's required of it is agreement: for any set of records, the rows the
published predicate admits are the rows the operator admits.

The way to check that is to **execute** the published string against the same rows and compare. Checking the
*text* instead — asserting the published rule contains some expected
phrase — is weaker in exactly the way that matters: it passes on a rule that reads plausibly and admits
different rows. And an engine faithfully implementing a published contract that disagrees with your own read
gives you an unreproducible training set, two correct-looking implementations, and no way to tell which one
is wrong. (MAYA's certificate publishes its rule in words, and the same function that writes the words applies
the rule — agreement by construction rather than by test.)

**The independent recomputation must bound the clock identically.** Assembly is verified by a second
computation that deliberately doesn't reuse the assembly path, so that agreement between them carries
information. That whole arrangement is worth its cost only if the two routes implement the *same* operator. A
verifier that bounds ingest by `as_of` while the assembly bounds it by `min(ℓ, a)` disagrees on every set
assembled *after* its labels matured — the ordinary case — and reports a mismatch on a **correct** assembly.

That failure is worse than it looks. A control that reports a violation where there is none isn't a
conservative control; it's one that teaches whoever reads the report to discount it, and it does so precisely
for the population it was built to examine. Stating the operator once, and requiring both routes to be it, is
what removes the possibility.

**A change of storage isn't licence for a second implementation.** The operator is defined over records and
says nothing about the medium holding them. But a platform that later gains a second storage backend acquires,
at that moment, the opportunity to write the predicate a second time — and the local pressure is toward doing
exactly that, because the new backend arrives with its own idioms while the existing function is written
against the old one. MAYA has two Delta Lake backends — the native `deltalake` bindings and its own
pure-Python implementation of the protocol — and the cut is written once, above both. What is written twice is
the storage, and that answers to one conformance suite run on each backend, with each backend reading the
other's tables. The general form is the moral of the section above: the number of implementations of a
relation is a design variable, and every value above one is a standing decision to permit disagreement. Where
MAYA wanted a second implementation for speed — a column-at-a-time canonical encoder, vectorised fill rules —
the original is named the authority and the fast one is tested equal to it on randomised inputs.

### Featuresets: schema and filling

The operator reads records; something has to say which records.

A **featureset** declares a *schema* — named slots with types, which by the order above is exactly what a
kernel is defined over. A **version** of that featureset *fills* the schema, binding each slot to a specific
feature and to the pinned version of the view supplying its values.

That separation does three things:

- Swapping which feature fills a slot doesn't change the model's input space. It changes what the model was
  *fitted on*, which is a different event with a different control.
- A version that cannot fill the schema is refused. Adding a slot is a change to `X`, and a change to `X` is
  a model change, not a data change. The register says so instead of letting it happen quietly.
- Because every binding pins a version, one featureset version resolves to the same bytes forever. A stable
  identifier over moving contents is the failure this design exists to prevent, and it is a failure with many
  disguises — the pin has to be at every level, because pinning the set and not the view underneath it looks
  identical from the outside and is not.

MAYA's version/pin split is this separation with the words moved: a feature-set **version** freezes *how* it is
assembled, a **pin** freezes *what* it assembled, and a feature-set pin refuses to exist until every member is
pinned — with a cascade that pins all of them in one transaction, or none. One difference from the ideal: a
version may name its members by version rather than by pin, and then it resolves to whatever they resolve to
today. Only the pin is stable.

---

## One polynomial, for everything that rests on something else

### Evidence is a derivation, not a log

Assurance evidence is a DAG: fitting evidence supports a fitting run, which with code and environment
supports a version, which supports test outcomes, which support a validation conclusion, which supports an
authorisation, which supports a deployment. Claims are built from base evidence by AND (joint dependence) and
OR (alternative routes).

Annotate each base item with an element of a **semiring** — something playing the role of plus, something
playing the role of times — and propagate with times for AND and plus for OR.

Now the trick. Evaluate the derivation once in **`ℕ[X]`**, the free commutative semiring over evidence
identifiers, and every other answer is a *substitution* into that result: a homomorphism sending each
variable to its value in whatever arithmetic you care about.

| Arithmetic | What the same traversal then tells you |
|---|---|
| true/false | is the claim supported at all? |
| counting | how many independent derivations corroborate it? |
| minimal support sets | which evidence sets suffice — what you'd put in front of an examiner |
| `ℕ[X]` itself | exactly how it was derived, keeping multiplicity |
| `(max, ×)` on `[0,1]` | with what confidence? |
| `(min, +)` | at what least cost can a gap be closed? |
| sets of regimes | for which regimes is this evidence admissible? |

Nobody has to write seven features. You write one traversal and seven valuations of about twenty lines each.

And this is a **theorem**, not a coincidence: where evaluating directly in an arithmetic and pushing the
polynomial forward disagree, one of the two routes is not a homomorphism — which is a fact about the
structure, not about the traversal. The old build checked it over 200 randomly generated derivation DAGs
against five arithmetics. **MAYA 0.3.0 has no evidence derivation at all** — its evidence is typed lineage
edges, a hash-chained audit log, custody events and signed certificates — so none of this section runs in it,
except three computations I come back to below.

The polynomial is worth keeping rather than just evaluating in each arithmetic separately, because it retains
what the others throw away. Coefficients count *distinct derivations*; exponents count *how many times one
fact is used*. Boolean provenance loses both — it cannot tell a claim supported by one document from a claim
supported by four.

### The same idea, one layer across

A derived feature is a **term**: `Z = f(X, Y)`. So annotate each base feature with its own variable and
evaluate the term in `ℕ[X]`. Now every question about the feature is a homomorphism out of it:

| Question | The homomorphism |
|---|---|
| what does this rest on? | the free variables of the polynomial |
| when did it become knowable? | pushforward into `max` — with an adjoined zero, see below |
| does it touch the label? | membership of the label's variable |

The ingest clock is the interesting one. *"A derived feature's ingest time is the maximum over its inputs"*
was documented as a rule — as *arithmetic, so it can't be forgotten*. It's stronger than that. It's a
**homomorphism**, and a homomorphism has no exceptions to forget.

In MAYA 0.3.0 that holds for feature sets — a row's knowledge time is the latest of its members' — and not
for the feature algebra, where six operators drop the clock entirely. A homomorphism has no exceptions to
forget; an implementation of one can still have six.

Two other things fell out that I hadn't separated properly before:

- **`lineage`** is every ancestor including derived ones — the right answer to *what breaks if this changes*.
- **`rests_on`** is the free variables of the polynomial: base features and nothing else — the right answer to
  *what data does this ultimately read*.

The second is the first minus its derived members. And leakage detection becomes a **membership test** rather than a graph walk with a depth limit: a derivation of a
derivation of the label is still the label, and the polynomial knows it without anyone traversing anything.

### The one that isn't a semiring

The design I started from named six arithmetics. One of them was **freshness** — `(max, max)` — answering
"as of when is this current?"

It isn't a semiring. `max(0, 5)` is 5, not 0, so its zero does not annihilate. And it's worse than that: for
`max` to have an identity at all, that identity has to be the bottom of the order — on *both* sides. So zero
equals one. And in any semiring, `0 = 1` forces the whole thing to collapse to a single element. There is no
choice of constants that repairs it. `(max, max)` is a commutative idempotent monoid used twice, and the
universal property does not reach it.

The practical consequence is worth knowing rather than hiding: **a claim resting on a *missing* fact reports
the freshness of the facts that are present, rather than reporting that it has none.** A structure that tells
you "as of when" for a claim it cannot in fact support is exactly the sort of instrument that reads as
reassurance.

**And I got the repair wrong last time.** I wrote that no different pair of operations could fix it. One
can, and it's elementary: add a brand-new element `⊥` meaning *no derivation at all* — not the smallest date,
a new thing — make it the identity for "or" and absorbing for "and", and keep `max` everywhere else. That
*is* a semiring (it's the same move that makes lineage a semiring in the provenance literature), and a claim
resting on a missing fact now evaluates to `⊥`: *not current at all*, which is the true answer. It also
quietly fixes something above: the ingest-clock homomorphism needs a semiring to land in, and as I first
wrote it, it didn't have one. What the repair doesn't give you is an aggregate — "how current, given how many
routes support it" still needs semimodule structure.

Here's why this matters for the actual system. MAYA 0.3.0 has no polynomial, but it does have **three**
computations of exactly this shape — one operation for both "and" and "or", over the leaves of a derivation:

| Valuation | How it combines |
|---|---|
| licence terms | most restrictive, clause by clause |
| non-causality | any operand |
| a feature-set row's knowledge time | latest member |

And each does precisely what the negative result predicts with a gap: **a missing annotation contributes the
identity, not a zero.** A source that declares no licence contributes no restriction, so a feature built
from one licensed and one undeclared source carries only the licensed source's terms. A member with no
knowledge time on a row contributes nothing, so the row reports its other members' clocks. Same defect, three
places, one proposition. Treating an undeclared licence as unrestricted may well be the right *policy* for
data a firm owns outright — but it's a decision the arithmetic makes silently, and the `⊥` construction is
what would make it explicit: "terms unknown", carried forward, refusable by name.

---

## What you still have to declare

An argument that four facts derive owes you an account of the ones that don't. There are three kinds, and
only the third is irreducible.

**Derived from a declared rule.** Risk tiering. The *value* is arithmetic: apply an agreed rule to a fact
set. There's no judgement in the computation at all. What's declared is the rule — the tiering matrix, the
lattices, the control mapping — and it should be. Two properties are then worth enforcing on it:
*monotonicity* (nothing you can learn that makes a model more consequential or more complex will ever move it
into a *lighter* control regime — which is exactly the guarantee an examiner wants and exactly what an
unconstrained scoring formula can't give), and an *adjunction* between required controls and defensible tier,
which means a control gap and an inflated tier are one defect seen from two sides rather than two problems
that never converge.

**Declared, but with a consistency oracle.** Regulatory scope. The same artefact can be outside one regime's
population, inside a second's, high-risk under a third and a key control under a fourth — simultaneously.
These are not four values of one attribute. They're four logical systems, each with its own vocabulary and
its own notion of what makes a sentence true of an inventory record.

Goguen and Burstall's **institutions** are exactly the abstraction for "a logical system", and they've been
on the shelf since 1992. Each regime is an institution; translations between them are comorphisms; adding a
regulator is adding a module. And institutions come with the **satisfaction condition**: *truth is invariant
under change of notation.* Evaluate an obligation in the regulator's vocabulary, or translate it into yours
and evaluate there — you must get the same answer.

Which gives you a **falsifiable consistency test** on your own encoding. If the two sides disagree, your
encoding of that regulation is wrong. Not "arguably suboptimal" — wrong, demonstrably. The encoding is still
a declaration, a claim *about* a regulation rather than the regulation. But a declaration with an oracle
attached is a strictly better position than a checkbox with a comment.

The same shape shows up for contradiction: whether a regime obliges and forbids the same term is decidable
over the sentences whose form is declared — and the sentences the checker *cannot* read are **named** rather
than assumed consistent. A check that silently ignores what it can't judge reports success for exactly the
cases it was least able to judge.

**Irreducibly declared.** Concluding a validation. Granting an approval. Accepting residual risk. Choosing
the tiering rule. These aren't weakly-checkable tasks we're conservatively withholding. They have no notion
of correctness independent of the authority exercising them. More on that in a moment, because it turns out
to be the whole point.

(MAYA 0.3.0 has none of the first two: no tiering, no encoded regimes. It does have one construction from
this territory — **covenants** on an execution warrant, declared bounds on inputs, outputs and usage whose
breach *suspends* the warrant until someone reinstates it on the record. That is an operating boundary with
teeth: when the assumption fails, the guarantee is void, and the software acts on it.)

---

## Laws, or it didn't happen

A foundation that's documented and unenforced becomes ornament within a few releases, and thereafter
misleads. So: every result above is restated as an executable law and checked by property-based testing
against *generated* inputs, with failure treated as a build failure.

One discipline matters more than the rest. Each law is tested **as it is stated**, not as the implementation
happens to behave. A test written from the code proves only that the code agrees with itself.

The old build had twenty-one of these laws in one test file — eighteen ran, three were listed with their
reasons, and a test kept the file and the paper's table in agreement. **That file didn't survive the
rebuild**, and nothing in MAYA 0.3.0 takes its place as a register. So the register of what runs now lives in
the paper, not in a test — a weaker arrangement than the one I'm arguing for, and I'd rather say so than
imply otherwise. The short version, over twenty-five claims:

| State in MAYA 0.3.0 | How many | Which |
|---|---|---|
| runs | 6 | refits aren't new versions; composite parameters accumulate; the partial meet; the cut-and-certificate relation; copy-don't-connect for SQL and Python sources; the assistant's no-write boundary |
| runs in part | 10 | the kernel's input roles; trainability (one row); typed fitting evidence (one row, permissively); change closure; one relation (three lines, three routines); missing vs narrowed; edit laws; the ingest clock; operating contracts (covenants); probe identity (sampled conformance) |
| not there | 7 | the fibration; rule-set reachability; the order and the lattice as such; edge type-checking; the `AsOf` operator itself; the provenance polynomial and citation checking; tiering and regimes |
| mathematics only | 2 | the aggregate-risk theorem; the `(max, max)` result and its repair |

What the rebuild *does* run, that no earlier version of this argument stated, is a set of laws about the
evidence path itself, checked against generated inputs: the canonical encoding is injective up to its
documented identifications; a pin's hash ignores column order and arrival order and notices any changed value;
content-defined fragments tile every table, and an inserted row leaves every earlier fragment untouched; a
restatement never overwrites. Those are the laws that make *"the same bytes"* a checkable sentence.

### What an executable law gives you that a written one doesn't

It isn't diligence. A statement in a document and the code it describes are two accounts of one rule, and two
accounts of one rule drift apart — not because anyone lets them, but because only one of the two ever gets
executed, and the executed one is the only one anything pushes back on. An executable law is the comparison
between them, run by a machine, on a schedule nobody has to remember.

Four things follow, and each is a property of the arrangement rather than of the people in it:

1. **A rule stated once can't disagree with itself.** Four questions, one function. (MAYA 0.3.0 is the
   counter-example: three routines, and they already disagree about integers.)
2. **A published contract can be executed rather than quoted.** Where you hand a rule to a system you don't
   run, the law runs the published rule and compares answers — a check on the contract, not on its spelling.
3. **Two routes to one answer can be required to be the same route.** Independent recomputation earns its
   cost only under that requirement, and the requirement is a law rather than a habit.
4. **A property that holds on the examples somebody chose is not the property.** Laws run against *generated*
   inputs, and are written from the law rather than from the code.

The fourth decides whether the other three are real. It's also why the claims that don't run are listed rather
than described: what they're missing isn't documentation.

---

## The part I didn't expect: this is where AI belongs

Here's what happened when I finished the structural work and looked at it again.

Every one of those derivations is a **decision procedure**. The order decides whether one thing can stand
where another stood. The operator decides whether a row is admissible. The polynomial decides whether cited
evidence supports a claim. The satisfaction condition decides whether a regulatory encoding is faithful.

I built them to make governance defensible. But a decision procedure is also exactly the thing that makes
machine-generated output safe to accept.

### The question everyone asks is the wrong one

Walk into any enterprise AI discussion and the question on the table is *"is the model good enough for this
task?"* It gets answered with benchmarks, a pilot, and a control that reduces to "a competent human will
check it."

That control is weaker than it sounds. It's expensive, it doesn't scale, and — the part that should worry you
— it degrades exactly when the output is fluent, because fluent text gets checked less carefully than rough
text.

There's a better question, and it isn't about the model at all:

> **Do I have a check?**

If yes, it genuinely doesn't matter much what produced the answer. A wrong answer gets caught and thrown
away; the only cost is wasted compute. If no, then trusting the answer is trusting the producer, and no
review process changes that — your reviewer is standing in the same fog you are.

Stated properly: *if a task is oracle-backed, the soundness of automation is independent of the generator.*
Hallucination stops being a correctness risk and becomes a throughput cost. Base-model upgrades stop being
governance events. And the boundary between "automate" and "don't" becomes a property of the domain, stable
as models improve, rather than a nervous guess revisited every six months.

### And here's the thing

**That boundary is the same boundary.**

You have a check exactly where the fact was **derived** rather than **declared**. The derivation *is* the
oracle. And where the fact constitutes the standard everything else is checked against — the tiering rule,
the approval, the accepted residual risk — there is nothing independent for a check to appeal to, so there is
no oracle, and there cannot be one.

I drew that line for governance reasons and then discovered it answers an entirely different question.

| Task | The check |
|---|---|
| Encode a new regulation as an institution | the satisfaction condition |
| Claim two versions behave the same | run the declared probe set |
| Substitute one version for another | the order: contravariant in inputs, covariant in outputs |
| Wire one model into another | `out(A) ⊑ in(B)` |
| Bind a featureset to a kernel | `S(F) ⊑ in(k)` |
| Assemble a training set without leakage | the point-in-time operator, recomputed independently |
| Cite evidence for a written claim | Boolean pushforward of the derivation |
| Propose a remediation plan | *none needed* — it's computed in the `(min,+)` arithmetic |
| Generate a probe, or a query | it runs and discriminates, or it doesn't |
| — | — |
| **Choose the tiering rule** | **none exists** |
| **Conclude a validation** | **none exists** |
| **Accept residual risk** | **none exists** |

The first row inverts what looks like a weakness. Encoding a forty-page supervisory statement into signatures
and sentences is expensive expert work, and that cost is the practical objection to the whole institutional
approach. It's also a task language models are unusually good at. And the output is *checkable*. Generation
becomes cheap, verification is mechanical, and the expert's job changes from authoring to adjudicating an
encoding that has already passed a consistency test. (MAYA encodes no regime, so that row is argument only.)

The rows MAYA 0.3.0 *does* carry are checks on generated output rather than generators. A model's formula is
**lifted** — from LaTeX, from Python, from a spreadsheet's formula graph — and the lift is then checked: a
spreadsheet's lifted formula is evaluated against the workbook's own cached results, and separately against
LibreOffice Calc recalculating the same file, and a workbook that disagrees is reported cell by cell and can't
be submitted. A feature set bound to a model gets the contract check; a training set gets the certificate; a
result handed to a regulator gets a bundle whose verifier re-executes it. The instructive exception is
spec-to-code conformance: sampled agreement can *refute* an implementation and can't certify one, so it isn't
an oracle — and MAYA's report begins with the words "Sampled agreement is not proof".

### Citation checking is arithmetic, not vibes

The dominant failure mode of machine-generated governance text is the unsupported assertion. The standard
mitigation — retrieval with citations — usually leaves *"does this citation actually support this claim?"* to
another model call, which is to say unanswered.

Over a derivation structure it's a computation. Switch on exactly the cited identifiers, evaluate the claim's
derivation in true/false, and see whether it still comes out true. If it does, the citation is genuine. If it
doesn't, the sentence is **rejected** — not flagged for review, rejected — with the missing identifiers named.

Take a drafted paragraph: *"Version 3.2.1 was approved for small-business origination following independent
validation, which found discrimination within tolerance on all monitored slices."* It cites the validation
report and the committee approval. But the claim's derivation requires the three test results too, so under
those citations alone it evaluates false: the citation is incomplete, and the sentence is rejected with the
gap named.

Note also the second clause — *"on all monitored slices"*. That's a quantified claim whose truth isn't in the
derivation at all. It has no supporting monomial, so it's rejected as unsupported rather than published as
plausible. That's the class of sentence human review reliably misses, because it reads exactly like the rest.

### What it classifies as off-limits — and why "risky" is the wrong word

*"Should we let a model assign risk tiers?"* is a malformed question. Assigning a tier isn't a generation
task — it's arithmetic on a rule everyone agreed to, and a spreadsheet could do it. The real questions are:
where do the facts come from (checkable — reconcile against systems of record), and who chose the rule (a
decision with accountability attached).

Automating the second isn't risky-but-tempting. It's a **category error**, because there's nothing for the
automation to be checked against. Same for concluding a validation, granting approval, accepting residual
risk. These aren't tasks we're conservatively withholding. They're tasks with no notion of correctness
independent of the authority exercising them.

### The reviewer is still in the system

An oracle guarantees no incorrect output is accepted *by the oracle*. In a governance process, acceptance is
an act performed by a person, and the composite that actually runs includes them. Machine-drafted text is
fluent, fluency reads as care, and reviewers of polished artefacts find fewer defects than reviewers of rough
ones. I can't dissolve that. Three things the structure does short of dissolving it:

- **It determines the division of attention formally.** Where an oracle exists the reviewer isn't checking
  correctness — that's disposed of — but authority, which admits no oracle. Marking that boundary in the
  interface is a mitigation available only because the boundary is formally determined rather than a matter
  of taste.
- **It supplies constructed objections rather than rhetorical ones.** An uncited claim is a failing conjunct.
  A refused wire names the field that doesn't compose. A featureset that doesn't serve a kernel names the
  slot that's missing or narrowed. These survive being stated in prose as fluent as the draft's, because none
  of them is a matter of emphasis.
- **It makes one thing measurable.** Whether the derivation nodes a claim rests on were actually *retrieved*
  during the review is a fact about the session, not an inference about the reviewer. The sharpest signal is
  the rate at which a reviewer accepts drafts the oracle refused — exactly the population where person and
  procedure disagree, and a quantity that exists only in a system with a procedure to disagree with.

None of that has been evaluated. They're hypotheses the framework generates, not results it establishes.

### Isn't a system that governs AI, using AI, circular?

No, and the reason is stratification rather than good intentions. The governing machinery — the order, the
operator, the derivation structure, the institutions — is one layer. The governed population is another. An
assistant is registered *in* the governed population: it has a parameter object (weights, prompt, corpus,
tools), a fitting morphism (configuration), a contract, a classification, evidence. Nothing in the governing
layer is an element of the governed one, and no construction needs a fixed point.

One dependency does cross, and it's worth naming rather than hiding: if an assistant drafts a regime
encoding, part of the governing layer was produced with help from the governed one. The resolution is that
the dependency is *mediated by an oracle that is not itself machine-produced*. The satisfaction condition is
a property of institutions, and it's evaluated mechanically.

**Generation may cross the strata. Acceptance may not.**

MAYA 0.3.0 draws this line at its most conservative. Its assistant is a **recorded challenger**: on every
submission it reads the version under review and writes a memo — look-ahead rules, unbounded fills, schema
drift, missing limitations, a document that disagrees with its formula, licence terms — attributed to the
provider and model that wrote it. It never approves, never blocks and never writes to the object; the
reviewer records whether they agreed, and neither the author nor someone who can't approve can do that for
them. Its output is never *accepted* by anything — it sits beside a decision that stays a person's — so its
correctness is never load-bearing, and the one thing the system has to guarantee is the no-write boundary,
which is tested. The default provider is a deterministic rule set; the Claude provider is opt-in and has only
been tested against a stub of its client. (One gap against the stratification above: the assistant is
configuration in MAYA, not a model registered in its own register. Its memos are attributed to the provider
and model version that wrote them, which is the record stratification needs, but it has no warrant of its
own.)

---

## The system this came out of

It's called **MAYA** — Model & AI Lifecycle Assurance — and it's at
**[github.com/ajsinha/maya](https://github.com/ajsinha/maya)**. It's proprietary; this article and the paper
are the parts published under an open licence.

The earlier version of this section described a build of 318 modules and 5,394 tests, in which each of the
four derivations was a module and twenty-one laws were a test file. **That build was deleted in September
2026**, and MAYA was rebuilt from nothing against a new specification. It would have been easy to leave the old
numbers standing — they were true when written — and that is exactly the failure this whole article is about:
a record that has drifted from the thing it describes, still reading as fact.

So, what exists now. Version 0.3.0 (19 September 2026) is a system of record for quantitative **features**,
**feature sets**, **models** and **warrants**. A training warrant freezes a model version against a pinned
feature set and receives the parameters training produced; an execution warrant licenses a model, its
parameters and its input contract to run — and can be *suspended* by a covenant breach or revoked on a Friday
afternoon. It doesn't train models and doesn't serve predictions. It's some 170 Python modules, 54 tables in
one typed schema that generates both SQLite and PostgreSQL DDL, an API with a one-to-one SDK, and more than
1,200 tests. It runs on Linux; Windows and macOS are specified and, by decision, not exercised.

It's also been measured, on one shared workstation: resolving a 50-attribute, ten-year daily panel of 500
symbols takes a warm p95 of 0.98 s (6.1 s with a bounded forward fill on every attribute), against a 15 s
target; catalog search over 100,000 objects, 0.16 s; the worst metadata page, 0.15–0.18 s. The fourth target —
200 concurrent users on one node without degradation — is **not met reliably**: three runs gave p95s of 0.34 s,
0.22 s and 0.43 s against 0.3 s.

What of *this* article is in it is the register in the laws section above: six claims run, ten run in part,
seven aren't there. The ones that run are the ones a register of *data and licences to compute* needed — the
point-in-time certificate, the partial meet for composites, parameter accumulation, copy-don't-connect — and
the ones that aren't are the ones a register of *kinds of model* would need.

### Five things building it changed

**The certificate replaced the operator.** The old build implemented `AsOf`, and its first version read `a`
where the definition says `min(ℓ, a)` — the saturation property test caught it. The rebuild doesn't implement
the operator. It reads with one scalar bound and *certifies* the per-row bound afterwards, and the two results
in the operator section above are what that is worth: a clean certificate means the operator's answer, and a
later rebuild is reproducible or refused. I proved those for this revision; I didn't design them in.

**A contract that was true of everything.** The rebuild's own proofs found that a declared black-box model had
an *empty* input contract, so every feature set satisfied it. Fixed. Writing this revision found the same
shape one step later — the parameter check that reads a missing formula body as "non-trainable". Both are a
check reading an absence as compliance. Neither was found by review.

**Two implementations, one authority.** Speed wanted a second implementation in three places: the lake (native
and pure-Python backends), the canonical encoding behind every hash (a column-at-a-time encoder, six to eight
times faster), and the fill rules (vectorised, which took the forward-fill benchmark from 156 s to 6 s). In
none of them is the second implementation trusted. For the encoding and the fills, the original is the
authority and the fast one is tested equal to it on randomised inputs; the lake's two backends answer to one
conformance suite and read each other's tables.

**Reproducibility by hash, not by bytes.** A namespace can choose to seal a feature-set pin by the hash of its
output *without writing the output*, replaying it from the member pins on every read. All three policies seal
the same hash. A replay that differs by one byte is refused rather than served — safe, and then unavailable.
It's the operator's trade made in bytes.

**The clock the algebra dropped.** The feature-set assembly carries the knowledge clock; six feature-algebra
operators don't. Found writing this revision, reported rather than fixed, because the repair belongs to the
platform and this is an article.

### The case studies

The earlier version of this article walked two public cases — the 2012 JPMorgan CIO losses and the Dutch
childcare benefits affair — through the old build, and reported what it caught and what it couldn't. Those
scripts didn't survive the rebuild and nothing in 0.3.0 reproduces them. Their findings were findings about a
system that no longer exists, so I've taken them out rather than let them stand as claims about this one.

### And the part that's for practitioners

The mathematical audience and the model-risk audience barely overlap, and a paper that serves both usually
serves neither. MAYA carries help written with no notation in it — topics on bitemporality, pins, warrants,
licences and conformance, four tutorials and thirteen reference guides. They describe the system rather than
this argument; if you want to know what the platform does rather than why, start there.

---

## The part where I try to talk you out of it

**There's no adoption study.** There's an implementation, and part of the argument runs in it — see the section
above — which is more than a conceptual paper usually has and much less than evidence. A large test suite shows a
thing is internally consistent, not that it is useful. I have not shown that a system built this way is
easier to build, extend or operate than one built without it, there's no comparative study and no
deployment at a supervised institution, and I wrote both the paper and the system, so it demonstrates
sufficiency rather than independent replication.

**The derivations still read declarations.** The class reads a declared fit procedure. The order compares
declared schemas. The operator reads declared clocks. The polynomial is built over declared derivation edges.
The claim is that the declared surface *shrinks and becomes checkable*, not that it vanishes — and where a
derivation's fallback is permissive, the old failure mode comes back in a smaller place. MAYA 0.3.0 shows it
coming back in three: the parameter check, the certificate's blind spot for rows with no clock, and the
valuations that read a missing annotation as "no restriction".

**Three routines for one relation.** The argument says write fit once; MAYA 0.3.0 has three routines, and
they already disagree about whether an integer may stand in for a float. The old build had a subtler version
of the same problem — two variance rules for outputs, one for composition and one for substitution — which the
rebuild hasn't reached only because it compares no bounds yet.

**Most of the argument doesn't run in the system.** Six of twenty-five claims run, ten in part, seven not at
all — and that register lives in the paper, not in a test, so nothing keeps it true. The interaction premium
in particular is computed nowhere: the theorem says what a correct aggregate can't be, and doesn't build one.

**The lattice is finite-fragment, and half of it isn't built.** No bottom element, and the meet is partial —
both honest, and both meaning the structure is weaker than "schemas form a complete lattice" would lead you to
believe. In the rebuild the meet is in daily use and the join doesn't exist.

**Formalising regulation is lossy and contestable.** An institution encoding is a claim *about* a regulation.
Two competent people may encode the same text differently and both be defensible. What the formalism gives
you is that the claim is explicit, citable and testable for internal consistency — not that it's right.

**The oracle boundary might be drawn too conveniently.** It classifies the decisions that matter most as
admitting no oracle, which is a very comfortable conclusion for anyone who'd prefer humans keep them. I
believe the argument — a rule that constitutes a standard cannot be checked against that standard — but it's
exactly the sort of argument whose conclusion deserves scrutiny in proportion to how much you like it.

**What would falsify this?** An artefact class that can't be presented as a parameter object plus a fitting
morphism without distortion. A governance question about fit that genuinely isn't an instance of the order —
which would show the unification was a coincidence of four cases. A fragility-sensitive aggregate risk
measure that is nonetheless compositional. And, most likely of all: a demonstration that practitioners can't
actually *use* the derivations — that a refusal naming a slot with no meet is no more actionable in practice
than a flag with a comment.

---

## Why I think this matters beyond banking

Strip the domain away and the shape is general.

Every system that governs something maintains a set of facts about what it governs. Some of those facts are
consequences of structure the system already has. Some of them constitute the standard the system exists to
apply. Almost every such system stores both kinds the same way — as fields somebody types in — and thereby
loses the ability to tell them apart.

Separating them buys two things at once. The derived facts stop rotting, because they're recomputed rather
than remembered, and a machine can tell you when they've stopped being true. And the declared facts get the
attention they deserve, because they're no longer buried among a hundred fields that could have computed
themselves.

The second reason to care, which I'd have found unconvincing a year ago: every one of these organisations is
also being asked how much of this work AI can do. The honest answer depends almost entirely on the same
separation. Where a fact derives, generation is free because acceptance is checked. Where it constitutes the
standard, there is nothing to check against, and the question isn't risk appetite — it's category.

So the generalisation, for whatever it's worth: when you're deciding how much of a judgement-laden process to
hand to a language model, the first question isn't how good the model is. It's *what, in this domain, could
ever tell us that the answer was wrong?*

If there's an answer, build aggressively — verification is doing the work, not trust.

If there isn't, no review process will save you, because your reviewer is standing in the same fog. Either
build the structure that supplies a standard, or keep the decision with a person who can be held to account
for it.

---

*The technical treatment — the lattice theorem and the partiality of the meet, the four properties of the
point-in-time operator with the saturation proof, the certified cut and "reproducible or refused", the
universality of the provenance polynomial, the proof that `(max, max)` cannot be a semiring and the adjoined
zero that repairs it, the impossibility result for aggregate risk, the citation-soundness proposition, and the
full register of what runs in MAYA 0.3.0 — is in the accompanying paper,*
**[Models as Parametric Kernels: An Order, an Operator and a Polynomial](models-as-parametric-kernels.pdf)**
*([LaTeX source](models-as-parametric-kernels.tex)).*

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>.
Licensed under [CC BY-NC-ND 4.0](LICENSE). See [NOTICE](../../NOTICE) for quoted material and disclaimers.
*Not legal, regulatory or financial advice — see NOTICE §4.*
