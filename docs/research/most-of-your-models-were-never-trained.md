# Most of Your Models Were Never Trained

### And fixing that tells you exactly where AI can safely do your governance work

---

There is a question that sounds trivial and turns out to be the hardest one in the room:

**What is a model?**

Not *which* model. Not *whose* model. What *is* one — formally, generally, in a way that covers
everything an organisation actually has to govern?

I spent a while on this recently and came away convinced that a whole category of expensive software
failure traces back to nobody having a good answer.

This is that answer. And then — this is the part I didn't see coming — it turns out to answer a
completely different question that everyone is currently arguing about badly: **where can you let an AI
do the work?**

---

## The population problem

Picture the quantitative assets running inside a large bank.

There is a Black–Scholes implementation. Its parameters come from financial theory. It has never
been trained on anything and never will be.

There is a volatility surface, re-solved against market quotes every single morning before the desk
opens. Its parameters change daily. Its *methodology* changes maybe once every three years.

There is a credit scorecard, refitted annually on a historical sample. A gradient-boosted fraud
model retrained weekly. An adaptive threshold that updates itself continuously in production, with
no human in the loop.

There is a language model drafting suspicious-activity narratives, whose "parameters" are a base
model, a prompt, a document corpus and a set of tools.

There is a third-party credit score whose internals are contractually unavailable and always will
be.

There is a country-risk rating scheme whose weights were set by a committee of nine people in a
room.

And there are several thousand spreadsheets.

Every one of these has to appear in one inventory. Every one has to be classified by how much damage
it could do, reviewed by someone independent, monitored, documented, and change-controlled. That is
not a preference. In most jurisdictions it is supervisory expectation, and in some it is law.

Now go and look at the tools built to do this.

---

## Two halves of a product, neither of them whole

The market splits with unusual cleanliness.

**On one side: governance platforms.** Excellent workflow. Beautiful approval chains, findings
registers, reporting. They are the descendants of enterprise GRC, and they are good at what they do.

They also cannot see the model. Not "have limited visibility" — cannot see it. The record says a
model was validated. Nothing in the system establishes that the model described in the record is the
model executing in production. The claim is unfalsifiable, which is roughly the opposite of what
assurance is supposed to be.

**On the other side: MLOps platforms.** Genuinely excellent artefact lineage. You can trace a
deployed model back to the run that produced it, the notebook, the dataset. This is real
engineering and it works.

They also have no concept of materiality, approved use, independent challenge, remediation, or
overlay. And — this is the part that gets underestimated — somewhere between 60% and 80% of the
population above never passes through them at all. The pricer doesn't. The vendor score doesn't.
The committee-set scorecard doesn't. The spreadsheets certainly don't.

So organisations buy both, end up with two inventories that disagree, and the disagreement is itself
an audit finding.

The obvious diagnosis is that somebody should build a better product. I think that's wrong. I think
the problem is that nobody wrote down a definition.

---

## Four pathologies with one cause

Here is what actually goes wrong, repeatedly, in systems built to manage this population.

**The training assumption.** Tooling inherited from machine learning assumes a pipeline: train,
register, deploy. So it asks every artefact for its training dataset. For the Black–Scholes
implementation, that is not a missing value. It is a *category error* — like asking what colour the
number seven is. But the system has no way to express that, so the field sits empty, an exception is
raised, someone types "N/A", and within two years the inventory is full of records that mean
nothing.

**Schema rigidity.** When "kind of model" is a column or an enum, every new kind is a database
migration that touches every module. Guess what happens? New kinds never get added. The artefacts
excluded from the inventory are, reliably, the newest and least understood ones — which is exactly
backwards.

**Scope as a boolean.** Whether an artefact is inside the governed population is not one fact. It is
several, one per regulator, and they disagree by design. One regime deliberately narrows its
definition to exclude spreadsheets and deterministic rules — and, as of 2026, generative AI.
Another defines it broadly enough to include expert judgment and qualitative outputs. An institution
operating in both must satisfy a narrow scope and a broad scope over the same inventory,
simultaneously. Model that as a checkbox and you will re-architect every time a regulator publishes.

I want to be concrete about how real this is. While I was working on this, the principal US
supervisory guidance for model risk — in force since 2011, the document an entire industry's
practice was built around — was superseded. The replacement narrowed the definition of what counts
as a model and explicitly put generative AI outside its scope. Under a boolean encoding, that is a
migration and a re-platforming project. It should have been a configuration change.

**Evidence as assertion.** Covered above. The record asserts; nothing verifies.

Four pathologies. One root cause: there is no formal answer to *what is a model?*, so every system
invents an informal one, and every informal one is wrong in a slightly different way.

---

## The definition

Here it is, and I promise the payoff is worth the two lines of notation.

> A **model** is a parameter object `P`, an input object `X`, an output object `Y`, and a map
>
> ```
> f : P ⊗ X → Y
> ```
>
> that consumes parameters and input and produces output — possibly stochastically.

That's it. In the jargon: a morphism in `Para(Stoch)` — a parametric map in a *Markov category*,
where morphisms behave like probability kernels rather than plain functions.

The whole trick is the separation of `P` from `f`.

Because now ask the question that actually distinguishes your artefacts. Not *what kind of model is
this?* — a question with no principled answer. Instead:

**How does the parameter object get filled in?**

| The artefact | Its parameter object `P` | How `P` gets filled |
|---|---|---|
| Black–Scholes | *empty* — the terminal object | it doesn't; there's nothing to fill |
| Volatility surface | calibration parameters | a solver, run against market quotes, daily |
| Credit scorecard | coefficients | a statistical estimator, run annually |
| Fraud classifier | weights | a training algorithm, run weekly |
| Adaptive threshold | parameters indexed by time | a process, running continuously |
| LLM application | base model + prompt + corpus + tools | configuration and retrieval |
| Vendor score | *exists, but you cannot see it* | someone else's problem, and unavailable |
| Committee scorecard | weights | nine people in a room |
| Rule set | the rules | somebody wrote them down |

Look at what just happened.

The taxonomy people argue about endlessly — is this an ML model? is a pricer a model? does a rule
set count? — is not a taxonomy of *things*. It's a taxonomy of *how one slot gets filled*.

And the two extreme cases are the interesting ones:

- **Black–Scholes is the case where `P` is empty.** Not a degenerate model. Not a special case. The
  parameter object is the terminal object, so `P ⊗ X ≅ X`, and the fitting question is *vacuous*.
  The system can now say, precisely and correctly: asking this artefact for a training set is a type
  error.

- **The vendor score is the case where `P` exists but is inaccessible.** All you can observe is the
  composite. Which is *exactly why* the only evidence you can ever gather about a vendor model is
  behavioural — you compare its outputs against your own realised outcomes. That's not a workaround.
  It's what the mathematics says is available.

Pathology one, dissolved. Training was never part of the definition of a model. It is one way of
inhabiting a parameter object.

---

## Then something surprising falls out

Here's the part I didn't expect.

Supervisory guidance has said, for fifteen years and in almost identical words across jurisdictions,
that you must assess model risk *individually and in aggregate*, and that aggregate risk "reflects
interactions and dependencies among models; reliance on common assumptions, data, or
methodologies."

Everyone nods at this. Almost nobody implements it. In practice, aggregate risk gets computed as the
maximum — or the join — of the component ratings.

That practice is provably wrong, and the proof is three lines.

Take a curve model `A`, and two pricers `B` and `C`.

**Network 1:** `A` feeds both `B` and `C`. One curve, two consumers.

**Network 2:** `A` feeds `B`, and a *separate, independently built* curve `A′` feeds `C`.

The component risk ratings are identical between the two networks. Same three ratings, same values.
So any scheme that computes the aggregate as the max — or the join, or any function of the component
ratings alone — gives the two networks **the same aggregate risk**.

But they are obviously not equally risky. In Network 1, one failure takes down both outputs. In
Network 2, one failure takes down one. That is the entire concept of concentration risk, and the
standard method is structurally blind to it.

So: *no aggregate risk measure can be both sensitive to shared dependency and computed
compositionally from its parts.* Pick one. And since the regulators explicitly want the first, the
second has to go.

Now the bit that made me sit up.

**What is the difference between the two networks?** Exactly one thing. Network 1 *copies* `A`'s
output. Network 2 doesn't.

Shared dependency **is** the copy operation.

And this is why the choice of mathematical setting matters in a way that is usually invisible. In an
ordinary Cartesian setting — normal functions, normal composition — copying is free and implicit and
structurally invisible. You literally cannot see the difference between the two networks in the
algebra. In a **Markov category**, copying is an explicit piece of structure you have to draw.

Which means: choosing the setting where probability lives naturally *also* gives you the setting
where concentration risk becomes visible. The regulator's paragraph about "reliance on common
assumptions, data, or methodologies" turns out to have precise mathematical content, and that
content is a comonoid.

The practical consequence is a number you can actually compute and put in a report: the **interaction
premium** — how much the whole exceeds the join of its parts, attributed to the specific shared
parameters, shared inputs, and shared methodologies that caused it.

---

## Two more, quickly

I'll be brief, because the pattern is now clear: pick the structure that matches the problem, and
the guarantee you wanted falls out.

**Kinds of model as fibres.** Instead of "kind" being a column, make it the index of a *fibration* —
a family of structures indexed by kind. Each kind supplies its own fibre: what evidence it requires,
what lifecycle it follows, what metrics it's monitored on, what documents it produces.

Adding a kind means supplying a fibre. And there's a small theorem that says the extension is
*conservative*: nothing about any existing kind changes, because the existing fibres are literally
untouched.

That's pathology two gone, and it converts "we support new kinds of model" from a marketing claim
into a structural property. Including kinds nobody has invented yet.

**Regulators as institutions.** This one is my favourite, because the tool has been sitting on the
shelf since 1992.

Goguen and Burstall defined an **institution**: an abstract formalisation of "a logical system" —
signatures (vocabulary), sentences (statements), models (things statements are true of), and a
satisfaction relation. It was built for combining different specification logics.

A regulatory regime is a logical system. It has its own vocabulary (*complexity*, *exposure*,
*purpose*, *natural persons*, *intended purpose*), its own sentences (the obligations), and its own
notion of what makes a sentence true of an inventory record.

So: each regime is an institution. Translations between them are institution comorphisms. Adding a
regulator is adding a module.

And institutions come with the **satisfaction condition**: *truth is invariant under change of
notation.* Evaluate an obligation in the regulator's vocabulary, or translate it into yours and
evaluate there — you must get the same answer.

Which gives you something governance systems essentially never have: a **falsifiable consistency
test**. If the two sides disagree, your encoding of that regulation is wrong. Not "arguably
suboptimal" — wrong, demonstrably, and detectable by generating inventory states and checking.

Scope determinations are among the most consequential judgements anyone makes in this domain —
whether an artefact is in the governed population determines whether *any* control applies to it —
and they are almost always a checkbox with a comment. This turns them into a derivation: the
sentence, the facts, the specific conjunct that failed, the citation.

---

## The part I didn't expect: this tells you where AI belongs

Here's what happened when I finished the structural work and looked at it again.

Every one of those constructions is a **decision procedure**. The satisfaction condition decides whether
a regulatory encoding is faithful. Provenance decides whether cited evidence supports a claim. Contract
refinement decides whether one version may replace another. Probe equivalence decides whether two
versions behave the same.

I built them to make governance defensible. But a decision procedure is also exactly the thing that
makes machine-generated output safe to accept.

### The question everyone asks is the wrong one

Walk into any enterprise AI discussion and the question on the table is *"is the model good enough for
this task?"* It gets answered with benchmarks, a pilot, and a control that reduces to "a competent human
will check it."

That control is weaker than it sounds. It's expensive, it doesn't scale, and — the part that should
worry you — it degrades exactly when the output is fluent, because fluent text gets checked less
carefully than rough text.

There's a better question available, and it isn't about the model at all:

> **Do I have a check?**

If yes, it genuinely does not matter much what produced the answer. A wrong answer gets caught and
thrown away; the only cost is wasted compute. If no, then trusting the answer is trusting the producer,
and no review process changes that — the reviewer is facing the same absence of a standard you are.

Stated properly: *if a task is oracle-backed, the soundness of automation is independent of the
generator.* Hallucination stops being a risk and becomes a throughput cost. Base-model upgrades stop
being governance events. And the boundary between "automate" and "don't" becomes a property of the
domain, stable as models improve, rather than a nervous guess that has to be revisited every six months.

### What that classifies as safe

Once you ask that question, the answer for this domain is surprisingly generous:

| Task | The check |
|---|---|
| **Encode a new regulation** as an institution | The satisfaction condition — generated inventory states, tested |
| **Claim two model versions behave the same** | Run the probe set |
| **Substitute one version for another** | Contract refinement — decidable |
| **Convert a model to a portable format** | Run both over the probes, compare numerically |
| **Cite evidence for a written claim** | Boolean evaluation of the derivation (see below) |
| **Generate a probe, or a query** | It runs and discriminates, or it doesn't |
| **Plan how to close a governance gap** | *No check needed* — the plan is computed, not proposed |

That first row is my favourite, because it inverts an apparent weakness. The whole "regulators as
institutions" idea has one real objection: encoding forty pages of supervisory prose into a formal
vocabulary is expensive expert work, and expensive expert work doesn't happen. But it's a task language
models are unusually good at — and now the output is checkable. Generation gets cheap; verification is
mechanical; the expert stops authoring and starts adjudicating something that already passed a
consistency test.

The last row is a different kind of nice. Remember the "cheapest way to close a gap" semiring? That
already computes the remediation plan. An agent doesn't have to *invent* the plan and be creatively
wrong about it — it just executes a plan the algebra produced.

### Citation checking is arithmetic, not vibes

This one deserves its own paragraph because I think it's genuinely the sharpest thing in the whole
exercise.

The standard fix for made-up facts is retrieval with citations. But *"does this source actually support
this claim?"* is normally answered by another model call, or by lexical overlap — which is to say, not
answered.

Over an annotated derivation structure, it's arithmetic. A generated sentence has to name the evidence
it rests on. You switch on exactly those identifiers, evaluate the claim's derivation in Boolean, and
see whether it still comes out true. If yes, the citation is real. If no, the sentence is **rejected** —
not flagged, rejected.

Worked example. An assistant writes: *"Version 3.2.1 was approved for small-business origination
following independent validation, which found discrimination within tolerance on all monitored slices."*
It cites the validation report and the approval.

Evaluate it. The approval claim's derivation also requires the underlying test results, which aren't in
the cited set — so the product comes out false. Citation incomplete, and the system can name exactly
what's missing.

But look at the second clause. *"On all monitored slices"* is a quantified claim with no supporting
term in the derivation **at all**. It doesn't get flagged as uncertain. It gets rejected as unsupported.

And that is precisely the sentence a human reviewer waves through, because it reads exactly like the
rest of the paragraph.

### What it classifies as off-limits — and why "risky" is the wrong word

Here's where I'd draw a harder line than is currently fashionable.

Should an AI assign risk tiers? People debate this as a risk-appetite question. I think it's malformed.

A risk tier is *defined* as a rule applied to facts. Applying the rule is deterministic — a spreadsheet
could do it. There's no generation task there at all. The real questions are: where do the facts come
from (checkable, by reconciling against source systems), and who chose the rule?

And choosing the rule can't be checked, because **the rule constitutes the standard**. There's no
independent thing to check a proposed rule against. That's not "too risky to automate." It's a category
error: there is nothing for the automation to be verified against, so the automation offers nothing.

Same argument for concluding a validation, granting an approval, accepting residual risk, and closing a
finding. These aren't weakly-checkable tasks we're conservatively withholding. They have no notion of
correctness independent of the authority exercising them.

So the rule I'd write on the wall:

> **A machine may propose anything and decide nothing.**

### Isn't a system that governs AI, using AI, circular?

It sounds like it should be. It isn't — but the reason is structural, not good intentions.

The governing machinery — the classification rule, the evidence structure, the institutions — isn't
AI, and isn't an object in the governed population. Every AI assistant *is* an object in that
population: it has parameters (weights, prompt, corpus, tools), a fitting procedure (configuration), a
contract, a risk tier, evidence, and a kill switch. Two layers, one direction. No fixed point required.

There's one dependency that crosses, and it's worth naming rather than hiding: if an assistant drafts a
regulatory encoding, then part of the governing layer was produced with help from the governed one. The
resolution is that the crossing is mediated by an oracle that *isn't* machine-produced — the
satisfaction condition is a theorem, evaluated mechanically.

Generation may cross the strata. Acceptance may not.

I'd go further and make this a hard rule: no AI capability in the system holds a credential that permits
a governance state transition. Not policy — credentials. Policy erodes under commercial pressure from
sensible people with good reasons. Missing credentials don't.

## The part where I try to talk you out of it

I'd rather flag the weaknesses than have you find them.

**None of this mathematics is new.** Markov categories, the Para construction, institutions,
provenance semirings, assume–guarantee contracts, sound abstraction — all established, all borrowed,
all with better expositions than mine. The contribution is assembly, plus about five results the
assembly makes visible. If you were hoping for a new theorem, this isn't it.

**There's no implementation study.** I can argue the extension guarantees are real. I have not
demonstrated that a system built this way is cheaper to build or operate than one built without.
That's the missing evidence and I'm not going to pretend otherwise.

**It doesn't cover everything gracefully.** Stateful simulation engines and agentic systems that
take actions and observe consequences fit only by shoving state into the input object. That's
faithful but ugly, and probably wants coalgebra or open games instead. Unsettled.

**Formalising regulation is lossy and contestable.** Encoding a regime as an institution means
committing to a reading of deliberately open-textured legal prose. The encoding is a *claim about*
the regulation, not the regulation. What you gain is that the claim is explicit, citable, and
testable for internal consistency. What you don't gain is being right.

**Oracles are necessary, not sufficient.** The proposition guarantees no incorrect output is
*accepted*. It says nothing about what a polished, unchecked-but-plausible artefact does to the person
signing it. Citation checking covers claims; it doesn't cover rhetoric. The best instrument I have is
measuring how much reviewers actually change — and treating a reviewer who changes nothing as a signal
rather than a success. That's a partial mitigation, not a fix.

**And I'll flag that my boundary is conveniently drawn.** The constitutivity argument classifies exactly
the decisions people most want to keep — approval, tiering, sign-off — as the ones AI can't touch. I
believe the argument. I also notice it's the conclusion I'd have preferred, and that's worth saying out
loud.

**And there's a real comprehension cost.** I have a rule I tried to hold myself to: an abstraction
earns its place only if it delivers something you'd otherwise hand-build, hand-check or
hand-migrate — *and* only if that something can be written as a test that runs in CI. Everything
above passes. Several things I wanted to include didn't, and I cut them. Homotopy type theory was
one. It was fun to think about and it bought nothing.

That last discipline matters more than any individual construction. A documented-but-unenforced
formalism decays into decoration within about two releases, and after that it actively misleads. If
the monotonicity of your risk classification is a claim in a design document, it will silently stop
being true. If it's a property test over generated inputs, it can't.

---

## Why I think this matters beyond banking

Every one of these pathologies shows up wherever a heterogeneous population of decision-making
artefacts has to be governed as one thing.

Healthcare systems run clinical decision rules, imaging models, risk scores, scheduling optimisers
and now LLM scribes. Insurers run pricing models, reserving models, catastrophe models and
underwriting classifiers. Public agencies run eligibility rules, fraud detection and forecasting.
Every one of them is being told to produce an AI inventory. Every one of them is discovering that
most of what belongs in it isn't AI, isn't trained, and doesn't fit the tool.

The instinct is to buy something. I think the sequence runs the other way. You cannot manage a
population you cannot define, and "model" as currently used is not a definition — it's a gesture at
a family resemblance. Once you have a definition with structure, the tooling questions get
noticeably easier, and several of them stop being questions.

There's a version of this I keep coming back to. Two families of tools each solve half a problem,
and everyone assumes the gap is a product opportunity. Sometimes it is. But sometimes the gap is
where a definition should be, and no amount of product fills it.

And there's a second reason to care now, which I'd have found unconvincing a year ago. Every one of
these organisations is also being asked how much of this work AI can do. The honest answer depends
almost entirely on something they haven't built yet: a structure that can tell them when an answer is
wrong.

So the generalisation, for whatever it's worth beyond this domain: when you're deciding how much of a
judgement-laden process to hand to a language model, the first question isn't how good the model is.
It's *what, in this domain, could ever tell us that the answer was wrong?*

If there's an answer, build aggressively — verification is doing the work, not trust.

If there isn't, no review process will save you, because your reviewer is standing in the same fog.
Either build the structure that supplies a standard, or keep the decision with a person who can be held
to account for it.

---

*The technical treatment — with the impossibility result stated properly, the conservative-extension
and satisfaction-condition propositions, the semiring construction for assurance evidence, the
automation-admissibility and citation-soundness results, and a full account of what I deliberately
didn't adopt and why — is in the accompanying paper,* **Models as Parametric Kernels, Governance as
Verified Automation.**

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>.
Licensed under [CC BY-NC-ND 4.0](LICENSE). See [NOTICE](../../NOTICE) for quoted material and disclaimers.
*Not legal, regulatory or financial advice — see NOTICE §4.*
