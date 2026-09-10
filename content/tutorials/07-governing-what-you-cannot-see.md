---
title: Governing what you cannot see
slug: governing-what-you-cannot-see
section: Start here
order: 70
icon: eye-slash
summary: A model somebody else built, a challenger running beside the champion, a model that changes itself, and data you are only allowed to keep for so long — the six screens that answer questions the model page cannot, and why each one refuses to show you a tick it has not earned.
audience: Model risk managers, Validators, Auditors, Model owners
---

# Governing what you cannot see

Everything in the earlier walkthroughs is about a model you built: you have the
kernel, the parameters, the data and the people. This page is about the other
half of a real estate — the model a vendor built, the version running in shadow,
the model that re-fits itself overnight, the personal data you are only allowed
to hold for a year.

Those have one thing in common. **The platform cannot see the thing the control
is about.** It did not train the model, it does not run the challenger, it does
not hold the online store, and it cannot read the vendor's source. So the design
question on every screen below is the same: *what can this honestly claim, and
what must it refuse to claim?*

The answer is always the same shape too. Where MAYA can check, it checks. Where
it cannot, it says so **in the answer** rather than showing a tick — because a
tick is what stops anybody asking.

---

## 1. A model somebody else built

Go to **`/vendor-models`**.

The failure this screen exists for is not laziness. It is a bank asking the
vendor for a validation report, receiving a thorough one, and filing it. That
report describes the vendor's development on the vendor's data. Filing it
validates somebody else's work.

SR 26-2 VII and SS1/23 2.6 both say the same thing: **you cannot validate what
you cannot see, so what is validated is your *use* of the model.**

So every checklist item records **who must discharge it**:

| The vendor can answer | Only you can answer |
|---|---|
| what the model does and on what theory | how it performs on **your** book |
| what population it was developed on | how your population differs from theirs |
| what independent validation they have had | what you changed, or that you changed nothing |
| what they say it cannot do | what happens if they withdraw it |

Concluding anything but `not_fit` while one of the right-hand items is open is
**refused**. Deciding *not* to use something requires less than deciding to, so
`not_fit` needs no such evidence.

```bash
curl -u a.mehta:pw -X POST localhost:5006/api/v1/vendor-assessments \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/credit.pd.vendor","vendor":"Acme Analytics",
       "product":"RiskScore","version":"7.2","artifact_digest":"sha256:…"}'
```

**The part people miss is the version change.** The vendor's version string is
what the vendor calls it; the artifact digest is what is running. They part
company at every silent upgrade. Tell MAYA what is installed and a change in
*either* reopens the assessment and puts every vendor statement outstanding
again — they were made about a release that is no longer there. What **you**
established about your own book survives, because that did not stop being true
when the vendor shipped.

---

## 2. A challenger running beside the champion

Go to **`/lifecycle-profiles`** and read *Challengers running beside the
champion*.

SS1/23 3.3(c) asks for parallel outcomes analysis when a dynamic model changes.
MAYA runs neither model: it records that a run is happening, takes delivery of
what both produced, and does the arithmetic.

**The whole thing turns on one distinction, and nearly every shadow-mode
dashboard gets it wrong.**

- *How often the two disagree* is knowable the moment both have answered. It
  says **nothing** about which is right.
- *Which was right* needs the outcome — the default, the claim, the loss — and
  that arrives months later, or never.

So MAYA reports those two apart and never mixes them, each with what it covers.
An outcomes analysis over four percent of a run is not a result with a caveat; it
is not a result. And **promoting on divergence alone is refused**: divergence
says the two models differ, not that the challenger is better. `inconclusive` is
an honest end and a common one.

One more thing worth knowing: an observation with only one side is reported as
**unpaired**, never dropped. A challenger that silently failed on the hard cases
would otherwise look like the better model.

---

## 3. A model that changes itself

Go to **`/api/v1/adaptive-change`**.

An adaptive model — a T4 — has **no version bump for anything to notice**. Every
other control in this platform fires on a version: a new version is reviewed,
approved, aliased, compared with its predecessor. A T4 changes underneath a
version nobody re-approved, so none of that machinery sees it.

What moves is the **parameter set**, and the trajectory of those points is the
only place the change is visible.

**Read the cumulative figure, not the steps.** A model that re-fits nightly and
moves a tenth of a percent each time has moved three percent in a month, and
every single step passed a per-change threshold comfortably. That is how an
adaptive model ends up somewhere nobody approved without any individual act being
wrong — and it is invisible to exactly the check most firms write. The cumulative
figure is measured from the last **approved** parameter set, because that is the
last moment a person looked.

Where the parameters live in an artifact rather than the register, MAYA says the
model changed and **not how far**. Reporting a magnitude there would be a number
pretending to be a measurement.

---

## 4. What you are holding, and for how long

Go to **`/classification`**.

A feature has been able to say it is confidential since the catalogue was
written. Nothing read the field. Now it propagates: **a model is at least as
sensitive as the most sensitive feature it reads**, and a document is at least as
sensitive as the most sensitive model it describes.

A model's class is therefore **derived, never declared**. You may declare it
*higher* — an output can be more disclosive than any single input, which is most
of what re-identification is — and you may not declare it lower. The refusal
names the feature that forces the floor, because that is where the decision
actually is.

Two things on the same page are worth reading together.

**Retention runs the other way from the instinct.** `restricted` data is kept for
the **shortest** time, not the longest. Important data feels like it should be
kept longer; the obligation is that data you should not be holding is held for
less.

**And a legal hold is the one control here that overrides another.** It has no
end date, and that is correct — it inverts the rule every other bounded thing in
MAYA follows. A hold ends when the *matter* ends, and when that is cannot be
known when it is placed; putting a date on it would be guessing at a litigation
timetable and calling the guess a control. A named owner and a stated matter
replace the deadline.

---

## 5. What the platform's own AI is doing

Go to **`/assist`**.

If you read one number here, read **citation accuracy** — and then read the
sentence beside it. It is 1.0, always, and that is **not good news**: the
grounding gate drops a claim citing something the register does not hold *before
anybody sees it*, so the figure measures the gate and not the model. The number
carrying the information is the **hallucination rate**.

Two more readings that invert:

- **Toxicity and personal-data leakage show as *not measured*, not as zero.**
  MAYA has no classifier and will not ship a keyword list dressed up as one. A
  dashboard showing no toxicity because nothing looked is worse than a blank,
  because a blank prompts somebody to ask.
- **A falling override rate is the alarm, not the goal.** The obvious reading is
  that the capability is improving. The other is that a reviewer who has approved
  forty correct drafts is not reviewing the forty-first — and the two look
  identical in the number.

The same page carries the **budgets** (a budget checked after the call is an
invoice), the **injection sweep** (a signal, never a gate — the fence is the
control), and the **canaries** that notice when the model under a version string
has quietly moved.

---

## 6. What happened without a grant

Go to **`/break-glass`**.

The `admin` role is *described* as break-glass in most platforms, including this
one until recently. That is not break-glass: it is a standing account that
happens to be powerful, which is the thing break-glass exists to replace.

A grant here is asked for with a reason, agreed to by somebody who is not the
requester, ends on its own, and is read afterwards by somebody who is not the
user. An unreviewed grant **refuses that person's next request** — otherwise
"mandatory post-hoc review" is a to-do list.

**And the figure to read first is `unglassed`.** You cannot find break-glass
abuse by watching break-glass: anybody misusing emergency access would simply not
open a grant for it. What finds it is privileged acts that happened under **no**
grant, folded from the evidence chain rather than reported by the people it is
about.

---

## What all six have in common

Every screen above answers a question the model page cannot, and every one of
them refuses to show you something it has not earned:

| Screen | What it refuses to claim |
|---|---|
| vendor models | that a vendor's report validates your use |
| parallel runs | that divergence tells you which model is better |
| adaptive change | a magnitude for parameters it cannot see |
| classification | that a model nobody traced has a derived class |
| machine assistance | a toxicity score from a classifier that does not exist |
| break-glass | that an empty log means nothing happened |

That is the pattern worth taking away. In a governance platform the useful
question is rarely *what does this show* — it is **what would this show if the
control were not working**, and a screen that looks the same either way is a
screen nobody should trust.

Next: [the estate and what needs doing](/help/estate-and-worklist), where all of
this lands as work with somebody's name on it.
