"""
The concepts deck: the mathematics MAYA is shaped by, presented in its own right.

Four facts a model governance system normally asks somebody to type in — what
kind of artefact this is, whether one thing fits where another fitted, what a
training row could have known, what a conclusion rests on — are consequences of
structure, and this deck gives the structure: a definition, an order, an
operator and a polynomial. It also gives the two results that go the other way,
because an account that only derives is an advertisement.

Every slide's note names the section of ``docs/research/models-as-parametric-kernels.tex``
the mathematics comes from, and every construction is glossed in plain terms and,
where it earns one, carried by a worked example from a bank.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

from concepts_deck_2 import SLIDES as LATER

CHAPTER = "MAYA · Concepts and Formalism"
TITLE = "MAYA — Concepts, Mathematics and Formalism"
SUBJECT = "An order, an operator and a polynomial: the mathematics MAYA is shaped by"

KERNEL = [
    {
        "kind": "title",
        "kicker": "CONCEPTS, MATHEMATICS AND FORMALISM  ·  AN ORDER, AN OPERATOR AND A POLYNOMIAL",
        "title": ["Four facts nobody", "should have to declare"],
        "sub": "The mathematics MAYA is shaped by, and the two results that bound it.",
        "agenda": [
            "A model, and its dials",
            "One order: can this stand in for that?",
            "Composition, and the risk that does not compose",
            "One operator: what could have been known",
            "One polynomial: what a claim rests on",
            "What must still be declared",
        ],
    },
    {
        "kind": "divider",
        "num": "1",
        "title": "A model, and its dials",
        "sub": "A closed-form pricer, a calibrated surface, a retrained classifier, an elicited "
        "rating scheme and a bought-in black box have nothing in common at the level of "
        "implementation. They have one shape — a kernel, and a parameter object that decides how "
        "it behaves — and what each one owes a reviewer follows from how that object is filled.",
        "points": [
            "A parameter object and a kernel",
            "Nine classes, one kind of thing",
            "Evidence demands that are well-typed",
            "A refit is a point, not a version",
        ],
    },
    {
        "kind": "split",
        "kicker": "The definition",
        "title": "A kernel, and the dials that decide what it does",
        "left": {
            "head": "What a model is",
            "items": [
                (
                    "A parameter object P and a kernel",
                    "f : P ⊗ X → Y. X is what goes in, Y is what comes out, and P is the dials "
                    "that decide how the machine behaves. The definition insists on holding the "
                    "dials apart from the machinery, because that separation is where every "
                    "consequence in this deck comes from.",
                ),
                (
                    "The output is allowed to be random",
                    "A kernel returns a distribution rather than a value, so a language model "
                    "sampling text is an instance rather than an exception, and deterministic "
                    "behaviour is the special case where the randomness is trivial.",
                ),
                (
                    "Composition keeps both sets of dials",
                    "Plug one model into another and the combined parameter object is Q ⊗ P. "
                    "Nothing is absorbed, which is why an upstream recalibration is formally a "
                    "change to everything downstream of it.",
                ),
            ],
        },
        "right": {
            "head": "How the dials get filled",
            "items": [
                (
                    "One construction, seven acts",
                    "A fitting morphism carries evidence into the parameter object. Estimation, "
                    "calibration, training, elicitation, configuration and authorship are not "
                    "different kinds of model; they are different ways into the same P — which is "
                    "the observation the rest of this part rests on.",
                ),
                (
                    "Accompanied, or opaque",
                    "A model is accompanied when the fitting morphism is available to whoever "
                    "governs it, and opaque when it is not. That decides what evidence can exist "
                    "at all, before anybody gets as far as asking for it.",
                ),
                (
                    "Same shape, different reality",
                    "Black–Scholes takes spot, strike, tenor, rate and volatility and has no "
                    "dials: fed the same inputs it returns the same price forever. A SABR surface "
                    "has the same shape and four numbers solved afresh against every morning's "
                    "quotes. The whole of the difference lives in P.",
                ),
            ],
        },
        "note": "Paper §2.2, the definition of a model as a morphism with a parameter object and "
        "of a fitting morphism into it, with the worked pair of a closed-form pricer and a "
        "calibrated surface.",
    },
    {
        "kind": "table",
        "kicker": "The classification",
        "title": "Nine classes, and not one of them is typed into a form",
        "intro": "The class is a total function of three things: whether the parameter object is "
        "empty, whether it is reachable, and which act filled it. It is computed when it is "
        "asked for and never stored, so it cannot drift from the artefact it describes — and the "
        "argument about whether a pricer or a rule set “is a model” dissolves, because these are "
        "one kind of thing distinguished by how the dials get set.",
        "rows": [
            ["Class", "The parameter object", "The act that fills it", "What triggers a refresh"],
            [
                "T0  Analytical",
                "empty — there are no dials",
                "none; there is nothing to fit",
                "the specification, or regulation",
            ],
            [
                "T1  Calibrated",
                "a calibration set",
                "a solver on quoted instruments",
                "each market close",
            ],
            ["T2  Estimated", "coefficients", "an estimator on a sample", "a periodic refit"],
            ["T3  Learned", "weights", "a training run", "schedule, drift or decay"],
            [
                "T4  Adaptive",
                "weights that move in production",
                "a training run, and then itself",
                "continuously, by the model",
            ],
            [
                "T5  Configured",
                "base model, prompt, corpus, tools",
                "configuration and retrieval",
                "any of those, or the base model",
            ],
            [
                "T6  Opaque",
                "exists, and is unreachable",
                "somebody else's, unavailable",
                "a vendor release",
            ],
            [
                "T7  Elicited",
                "weights a panel agreed",
                "an elicitation protocol",
                "the committee cycle",
            ],
            ["T8  Authored", "a rule set", "authorship", "a policy change"],
        ],
        "col_w": [1.8, 2.9, 3.3, 2.9],
        "note": "Paper §2.3, “Trainability is derived”: the classification proposition and the "
        "table that follows it. The two ends carry the argument — at the top the dials do not "
        "exist, so asking about them is meaningless; at T6 they exist behind a contract, so "
        "asking about them is futile.",
    },
    {
        "kind": "cards",
        "kicker": "What each one owes a reviewer",
        "title": "Three artefacts, one lens, three different questions",
        "cols": 3,
        "cards": [
            (
                "T0 · ANALYTICAL",
                "A regulatory exposure calculator",
                "The formula is prescribed, so there are no dials. No sample, no estimator, no "
                "retraining schedule. What must be evidenced is that the implementation computes "
                "what the regulation says: a suite against reference values. A register that "
                "demands a training set here is not recording a missing value — it is asking an "
                "ill-typed question and getting a meaningless answer typed into a mandatory field.",
            ),
            (
                "T2 · ESTIMATED",
                "A small-business PD scorecard",
                "Forty-two coefficients, from a logistic regression over eight years of "
                "originations. Here the fitting questions are exactly the right ones: the sample "
                "and whether it is representative, the estimator, out-of-time performance, "
                "calibration. This is the artefact the whole evidence apparatus was designed "
                "around, which is why it is the one that never causes trouble.",
            ),
            (
                "T6 · OPAQUE",
                "A bought-in bureau score",
                "The dials exist — somebody at the bureau fitted them — and neither they nor the "
                "act that set them is reachable. Demanding development documentation is futile. "
                "Watching the composite against your own realised defaults is not a compromise "
                "forced by commercial reality; it is what the structure says is the only evidence "
                "obtainable, so it is where the review effort belongs.",
            ),
        ],
        "note": "Paper §2.3, the corollary that a demand for fitting evidence is well-typed "
        "exactly when the parameter object is neither empty nor unreachable, and the worked "
        "triple that follows it.",
    },
    {
        "kind": "bullets",
        "kicker": "Why the class has to be computed",
        "title": "A monitor that ran for two years and meant nothing",
        "intro": "Evidence requirements, lifecycles, monitors and compilable documents are one "
        "family indexed by kind of artefact. Two properties of such a family are worth having, "
        "and an index somebody types in cannot deliver both.",
        "items": [
            (
                "The story",
                "A discount-curve pricer is registered, and somebody attaches a performance "
                "monitor: discrimination against realised outcomes, evaluated monthly. It runs. "
                "It never fires. On the estate screen the model is green and monitored.",
            ),
            (
                "Why it meant nothing",
                "The pricer has no parameters and no fitted relationship to outcomes, so "
                "discrimination is not a question about it. The monitor was not failing to detect "
                "anything; there was nothing of that kind to detect. And that is worse than an "
                "absent monitor, because an absent one appears in the coverage worklist and a "
                "meaningless one reads as coverage.",
            ),
            (
                "Adding a kind should cost only that kind",
                "Supply the requirements for a new class and nothing already judged is disturbed: "
                "every existing kind keeps exactly the obligations it had. That guarantee is "
                "worth having, and it is worth nothing unless every kind actually carries its "
                "requirements — a drawer with no forms in it is worse than an absent drawer, "
                "because the cabinet looks complete.",
            ),
            (
                "Which is why the index is computed, not recorded",
                "If the admissible kinds are a closed list, admitting a new one edits the index "
                "rather than supplying requirements, and the guarantee no longer describes what "
                "adding a kind costs. If the list is open, a kind with no requirements can be "
                "written down at any moment, so the completeness check quantifies over a set that "
                "does not contain the values in use, and passes. An index computed from the "
                "artefact has neither horn: it cannot be typed wrong, cannot be extended by "
                "accident, and cannot disagree with the thing it indexes.",
            ),
        ],
        "note": "Paper §2.4, “The classification is the index”: conservative extension, totality, "
        "and the proposition that a declared base admits no total family of obligations.",
    },
    {
        "kind": "bullets",
        "kicker": "Points of the parameter object",
        "title": "A refit is a new point, not a new model",
        "items": [
            (
                "Two different events, usually recorded as one",
                "A new fitting procedure, parameter object, input or output is a change of the "
                "model. New numbers from the same procedure on newer data is a change of point "
                "within it: the morphism is untouched, because the parameters are inhabitants of "
                "its parameter object rather than distinct morphisms. Mint a version for both and "
                "a supervisor asking whether the model changed between two dates has asked a "
                "question with two answers.",
            ),
            (
                "So an inhabitant of P is a record in its own right",
                "With its own identity, immutability and provenance: which act produced it, from "
                "which data, over which window. A daily recalibration then governs the procedure "
                "once and a periodic re-estimation governs each inhabitant, and the two are the "
                "same construction at different frequencies rather than two policies.",
            ),
            (
                "Parameters accumulate along a network",
                "The parameter object of a composite is the tensor of every constituent's, so any "
                "change to a constituent's numbers changes the composite's. Recalibrating an "
                "upstream artefact is, formally, a change event for every artefact downstream.",
            ),
            (
                "The daily recalibration nobody calls a change",
                "At 6:30 each morning a discount curve is re-solved against market instruments. "
                "Downstream sit a swaption pricer, an XVA engine, a VaR engine, a capital "
                "calculator and a capital plan, and formally every one of them has just changed. "
                "The change process records nothing, because curves are “market data”. Both "
                "readings are defensible; the usual resolution is that routine recalibration "
                "inside a declared tolerance is governed by monitoring and recalibration outside "
                "it is a change event. The formalism does not choose. It forces somebody to "
                "notice that a choice is being made, and to write the tolerance down.",
            ),
        ],
        "note": "Paper §2.7, “Points of P, and what a version is”: refitting preserves the "
        "morphism, parameters accumulate along a composite, and the worked recalibration that "
        "shows why the distinction is not pedantry.",
    },
]

ORDER = [
    {
        "kind": "divider",
        "num": "2",
        "title": "One order",
        "sub": "Four places in a register ask whether one thing fits where another fitted. In the "
        "registers we have examined each has its own code path, and four implementations of one "
        "relation are four opportunities to disagree — predictably in the direction of permitting "
        "more, because nobody files a bug against a check that wrongly allows.",
        "points": [
            "Four questions, one comparison",
            "A ⊑ B: A can stand in for B",
            "A lattice, and a partial meet",
            "A refusal that names the remedy",
        ],
    },
    {
        "kind": "table",
        "kicker": "Where fit is asked",
        "title": "Four questions that were one question",
        "intro": "A variance routine, a slot loop, a contract refinement check — and, for the "
        "dependency edge, frequently nothing at all. The fourth row is the worst of them, because "
        "a graph whose edges were never checked is followed by a blast radius that trusts them.",
        "rows": [
            ["Where it is asked", "What it actually asks", "The comparison"],
            [
                "A replacement version",
                "May this version stand where the incumbent stood?",
                "in(v') ⊑ in(v), and out(v') still provides out(v)",
            ],
            [
                "Binding data to a model",
                "Does this feature set provide what the kernel declares it reads?",
                "S(F) ⊑ in(k)",
            ],
            [
                "A dependency edge",
                "Does what the source produces arrive where the target reads it?",
                "out(a) ⊑ in(b)",
            ],
            [
                "One feature set, two models",
                "Can a single feature set serve both of these?",
                "S(F) ⊑ in(k1) ⊓ in(k2)",
            ],
        ],
        "col_w": [2.6, 4.9, 4.1],
        "note": "Paper §3.1 and §3.5, “Four questions that were one question” and “One relation, "
        "four answers”. The fourth line is the meet doing work, and when the meet does not exist "
        "the honest answer is that no feature set can serve both, with the offending slot named.",
    },
    {
        "kind": "bullets",
        "kicker": "The order",
        "title": "A ⊑ B, read: A can stand in for B",
        "items": [
            (
                "One field accepts another",
                "Same datatype; nullable if the other is; a lower bound no greater and an upper "
                "bound no less, an absent bound being the widest there is. A ⊑ B holds when every "
                "field B declares is present in A at a field that accepts it.",
            ),
            (
                "Extra fields are free",
                "A may carry fields B does not. Nobody has to look at them, so a richer provider "
                "is always admissible — which is what makes the relation usable in a bank, where "
                "the feature set that serves one model always carries more than that model reads.",
            ),
            (
                "Being fussier is not free",
                "Each shared field must accept at least what B's accepted, because a replacement "
                "that rejects an input its predecessor took is a replacement that breaks a "
                "caller. Somebody was relying on the old tolerance.",
            ),
            (
                "And the direction is counterintuitive, reliably so",
                "“Refinement” suggests narrowing, and a subtype is narrower in the values it "
                "denotes. But a schema here is read as the set of inputs a slot will accept, and "
                "standing in for something requires accepting at least what it accepted — so a "
                "wider acceptance is admissible and a narrower one regresses. The two readings of "
                "“narrower” are easy to hold at once and impossible to hold consistently, and the "
                "failure they produce is silent: an order stated in the intuitive direction "
                "admits exactly the replacements that break callers. That is why it is worth "
                "writing down as an order with a stated direction rather than as a rule of thumb.",
            ),
        ],
        "note": "Paper §3.2, “The order”: field acceptance, the schema order, and the remark on "
        "why the direction is the one nobody guesses.",
    },
    {
        "kind": "split",
        "kicker": "A lattice",
        "title": "The meet and the join, and the question each one answers",
        "left": {
            "head": "Meet  ⊓  — what can serve both",
            "items": [
                (
                    "All the fields either one had, each loosened",
                    "Nullable if either is, the lesser lower bound, the greater upper bound, and "
                    "an absent bound absorbing.",
                ),
                (
                    "The question it answers",
                    "What would a single feature set have to provide in order to serve both of "
                    "these models? Nothing weaker than the meet will do, and anything at least as "
                    "strong will.",
                ),
                (
                    "It is a greatest lower bound",
                    "So a refusal derived from it is not a heuristic. Everything that serves both "
                    "stands in for the meet, which is what makes the comparison against the meet "
                    "the whole of the test rather than a first pass.",
                ),
            ],
        },
        "right": {
            "head": "Join  ⊔  — what both promise",
            "items": [
                (
                    "Only the fields both have, each tightened",
                    "Nullable only if both are, the greater lower bound, the lesser upper bound.",
                ),
                (
                    "The question it answers",
                    "What may a consumer of either of these rely on? That is the contract a "
                    "downstream model may be written against when its input might come from "
                    "either source.",
                ),
                (
                    "A top, and no bottom",
                    "The empty schema imposes no condition, so everything can stand in for it. "
                    "There is no least element, because it would have to carry every field name "
                    "that could ever exist. The structure is a lattice on each finite fragment, "
                    "which is the only fragment anything inhabits.",
                ),
            ],
        },
        "note": "Paper §3.3, “It is a lattice”: the meet and join, the lattice theorem, and the "
        "absorption law that makes this a lattice order rather than an order with two unrelated "
        "operations.",
    },
    {
        "kind": "bullets",
        "kicker": "The partiality is the useful part",
        "title": "No meet, and the refusal that names the remedy",
        "items": [
            (
                "Two schemas can have no lower bound at all",
                "If a shared field name carries a different datatype on each side then no field "
                "accepts both, so nothing can serve both. The meet is partial, and the partiality "
                "is the informative part rather than a gap in the construction.",
            ),
            (
                "An empty answer is worse than an error",
                "Whoever asked for the meet has a decision to make, usually that these two models "
                "cannot share a feature set. An absent value threaded through three layers "
                "becomes a silent empty schema somewhere downstream; a named refusal carrying the "
                "slot, both datatypes and which side wanted each is the answer to the question "
                "that was actually asked.",
            ),
            (
                "A failure of the order decomposes into two different mistakes",
                "Names B has that A lacks are missing. Names A has that accept less than B's did "
                "are narrowed. They have different remedies: a missing slot means the wrong data "
                "was bound, and a narrowed one means somebody tightened a constraint without "
                "noticing it was a promise.",
            ),
            (
                "Which changes the character of a control",
                "“Incompatible” is a message. “Does not provide turnover; accepts less than "
                "before at dscr” is an instruction. And reporting every failure rather than the "
                "first is the difference between one round of correction and six — a refusal that "
                "reveals one obstacle at a time is a refusal whose author never computed the "
                "obstruction set.",
            ),
        ],
        "note": "Paper §3.4 and §3.6: the proposition that two schemas disagreeing on a datatype "
        "have no meet, and the observation that a failure of the order splits into missing and "
        "narrowed.",
    },
]

COMPOSITION = [
    {
        "kind": "divider",
        "num": "3",
        "title": "Composition, and the risk that does not compose",
        "sub": "Wiring one model into another is a type-check, and decidable. What cannot be had "
        "at all is an aggregate risk figure that both adds up from its parts and notices a single "
        "point of failure — and the obstruction is a piece of structure rather than a modelling "
        "difficulty a better dependency assumption removes.",
        "points": [
            "An edge is a claim about types",
            "Two banks, one curve or two",
            "The obstruction, and what laxity leaves",
        ],
    },
    {
        "kind": "bullets",
        "kicker": "Composition as a type-check",
        "title": "An edge is a claim about types, not a line on a diagram",
        "items": [
            (
                "The check",
                "An edge from a to b asserts that a's output is read as an input by b, and holds "
                "only when out(a) ⊑ in(b). Where it holds the composite's signature is derived — "
                "a's inputs, b's outputs — and type-correctness of a whole wiring is decidable.",
            ),
            (
                "Extra outputs are fine; a missing one is not",
                "A richer output composes, because the surplus is simply unread. A name the "
                "target reads and the source does not produce is a wire to nowhere, and the "
                "refusal names it.",
            ),
            (
                "A composite's schema is derived, never written down",
                "A signature somebody typed is a signature that can disagree with its parts. The "
                "composite's input contract is the partial meet of its members', so two members "
                "wanting one attribute at two datatypes is refused when the composite is defined "
                "rather than discovered when it runs.",
            ),
            (
                "Not every relation between two models is a wire",
                "“Challenger of” and “benchmark for” record how somebody thinks about a model. "
                "There is no wire, so there is nothing to type — and treating a challenger as a "
                "dependency would inflate every blast radius it appears in.",
            ),
            (
                "What composes, and what does not",
                "A composite's maturity is capped at its least mature member's: a meet on a "
                "finite chain, which composes, and every member below the target named rather "
                "than the first. A risk magnitude is what does not compose, and the next two "
                "slides are why.",
            ),
        ],
        "note": "Paper §4.1, “An edge is a claim about types”: the composition type-check, and the "
        "remark that vocabulary is part of the formalism — an edge named “feeds” is read in a "
        "bank as a nightly data drop, and the defect is in the account rather than the audience.",
    },
    {
        "kind": "bullets",
        "kicker": "Worked example",
        "title": "The wire that was a drawing",
        "intro": "An expected-credit-loss stack records that a PD model feeds a provisioning "
        "engine. Both entries have existed for two years and the edge is on the diagram in every "
        "committee pack.",
        "items": [
            (
                "What the register held",
                "The PD model's current version produces pd_12m. The provisioning engine's "
                "current version reads pd_lifetime. Nobody had wired the two systems together.",
            ),
            (
                "What was actually there",
                "An adapter in between, computing one from the other using a term structure that "
                "belongs to a third model — which is not in the register at all.",
            ),
            (
                "What the unchecked edge reports",
                "A two-node dependency, and a blast radius wrong in both directions at once: it "
                "claims a change to the PD model reaches provisioning directly, and it omits the "
                "term structure entirely. Nothing about the drawing said so.",
            ),
            (
                "What the check does instead",
                "The edge is refused at the moment somebody records it, with pd_lifetime named as "
                "the output that does not exist. The conversation that follows is the one that "
                "discovers the third model — which is the whole value of the refusal, and it is "
                "available only because the edge asserts something checkable.",
            ),
        ],
        "note": "Paper §4.1, the worked example following the composition type-check.",
    },
    {
        "kind": "bullets",
        "kicker": "Aggregate risk",
        "title": "Two banks, one curve or two",
        "intro": "Supervisory guidance asks that risk be assessed both individually and in "
        "aggregate, reflecting interactions and dependencies among models and reliance on common "
        "assumptions, data or methodologies. That expectation has precise formal content: it "
        "asserts that compositionality fails.",
        "items": [
            (
                "The two banks",
                "Each runs one curve model and two pricers. Bank A feeds both pricers from a "
                "single curve. Bank B built two curves independently, one for each pricer.",
            ),
            (
                "Rated individually they are identical",
                "Same curve rating, same two pricer ratings. So any method that computes the "
                "total from the constituent ratings — taking the maximum, or the join, which is "
                "standard practice — returns the same answer for both banks.",
            ),
            (
                "They are not the same bank",
                "Bank A has a single point of failure and Bank B does not. That is the whole of "
                "it: the risk of the whole is not a function of the risks of the parts, because "
                "part of it lives in the wiring.",
            ),
            (
                "Stated exactly",
                "No risk assignment is both compositional — the whole being the join of its parts "
                "— and fragility-sensitive, where a network in which one artefact reaches more of "
                "the outputs rates strictly higher than one in which it reaches fewer, the "
                "multiset of constituent risks being equal. Two distinct ratings in the scale are "
                "enough to force the contradiction, so no richer scale escapes it.",
            ),
        ],
        "note": "Paper §4.2, “Aggregate risk”: the definitions of a risk assignment and of "
        "fragility, and the theorem that no assignment is both compositional and "
        "fragility-sensitive.",
    },
    {
        "kind": "bullets",
        "kicker": "The obstruction",
        "title": "It is the copy map, so it cannot be approximated away",
        "items": [
            (
                "The two networks differ in exactly one thing",
                "One copies an output and hands it to two consumers; the other runs two "
                "independent instances. Shared dependency is that copy — a piece of the algebra, "
                "not a correlation assumption somebody chose badly.",
            ),
            (
                "Which is why the ambient setting matters",
                "Where copying is implicit it is structurally invisible, and the distinction "
                "between the two banks cannot be expressed at the level of the algebra at all. "
                "Making the copy explicit is a concrete reason to work in a setting that names "
                "it, even when every governed artefact is deterministic.",
            ),
            (
                "So the result is a constraint, not a measure",
                "It says what a correct aggregate cannot be. It does not construct one, and an "
                "account that claimed otherwise would be selling the thing it had just proved "
                "impossible.",
            ),
            (
                "What remains is laxity",
                "Any fragility-sensitive assignment is at best lax: the whole is at least the "
                "join of its parts. The discrepancy is the interaction premium, and it is the "
                "quantity the guidance is actually asking about.",
            ),
            (
                "And therefore what a correct aggregate must report",
                "The join of the constituents and the composite figure, with the difference "
                "attributed — to common parameter objects, common inputs, common fitting "
                "evidence, common methodology. The first three are computable from a typed graph. "
                "The fourth is not, and an aggregate that implies it is becomes decorative.",
            ),
        ],
        "note": "Paper §4.2, the remark identifying the copy map as the obstruction and the "
        "corollary that laxity is necessary, with the interaction premium as the discrepancy.",
    },
]

SLIDES = KERNEL + ORDER + COMPOSITION + LATER
