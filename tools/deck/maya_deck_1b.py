"""
The deck's second part: the four facts that need not be declared.

Split from ``maya_deck`` only because one module may not exceed the repository's file-size
gate; the two are one section of one deck and are meant to be read together.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

DERIVED = [
    {
        "kind": "divider",
        "num": "2",
        "title": "Four facts you should not have to type",
        "sub": "A register asks somebody to declare what kind of artefact this is, whether one "
        "thing fits where another fitted, what a training row could have known, and what a "
        "conclusion rests on. All four are consequences of the structure Part 1 built. Each one "
        "here is motivated by the failure it prevents, not by the theorem it follows from.",
        "points": [
            "Declared facts rot: D1 to D4",
            "Kind, computed from the dials",
            "One order: can A stand in for B?",
            "Composition, and the risk that does not compose",
            "The point-in-time read, as an operator",
            "Provenance: one traversal, many questions",
            "What must still be declared",
        ],
    },
    {
        "kind": "table",
        "kicker": "The problem with forms",
        "title": "Four declared facts, and how each one rots",
        "intro": "These are not hypothetical. Each is a field that exists in registers now, each "
        "is filled in by a person, and each decays in a way that is invisible from the field "
        "itself — which is what makes a declared fact worse than an absent one.",
        "rows": [
            ["", "The declaration", "How it rots", "What the damage looks like"],
            [
                "D1  Kind",
                "What sort of artefact this is: pricer, scorecard, network, rule set",
                "Typed once, at registration, by whoever was filling the form",
                "A monitor that cannot detect anything runs for two years and reads as coverage",
            ],
            [
                "D2  Fit",
                "Whether this data, or this replacement version, fits where the last one did",
                "Implemented four times in four code paths that drift apart",
                "They drift towards permitting more, because nobody files a bug against a check "
                "that wrongly allows",
            ],
            [
                "D3  Currency",
                "What a training row could have known at the moment it describes",
                "A convention in whoever wrote the query, applied unevenly",
                "Look-ahead that improves every metric it corrupts, so nothing asks to be "
                "investigated",
            ],
            [
                "D4  Support",
                "What a conclusion rests on: which tests, which approvals, which data",
                "A log of what happened, which is not the same as a derivation",
                "“Is this still supported?” cannot be answered without a person reading the log",
            ],
        ],
        "col_w": [1.4, 3.3, 3.2, 3.7],
        "note": "Paper §1. The claim of this part is narrow: each of these four is derivable from "
        "structure that has to exist anyway, and a derived fact cannot be typed wrong, cannot "
        "drift, and cannot disagree with the object it describes.",
    },
    {
        "kind": "table",
        "kicker": "D1 · Kind",
        "title": "Nine classes, and not one of them is typed into a form",
        "intro": "The kind of an artefact is a function of three things Part 1 already defined: "
        "whether it has dials at all, whether they can be reached, and which act set them. It is "
        "computed when it is asked for and never stored, so it cannot drift.",
        "rows": [
            ["Class", "The dials", "The act that set them", "What triggers a refresh"],
            [
                "T0  Analytical",
                "none — there are none to set",
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
                "exist, and are unreachable",
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
        "note": "Paper §2.3. The two ends carry the argument: at T0 the dials do not exist, so "
        "asking about them is meaningless; at T6 they exist behind a contract, so asking about "
        "them is futile. A closed-form pricer becomes a type rather than an exception.",
    },
    {
        "kind": "cards",
        "kicker": "What each one owes",
        "title": "Three artefacts, one lens, three different questions",
        "cols": 3,
        "cards": [
            (
                "T0 · ANALYTICAL",
                "A regulatory exposure calculator",
                "The formula is prescribed, so there are no dials. No sample, no estimator, no "
                "retraining schedule. What must be evidenced is that the implementation computes "
                "what the regulation says: a suite against reference values. A register "
                "demanding a training set here is asking an ill-typed question and getting a "
                "meaningless answer in a mandatory field.",
            ),
            (
                "T2 · ESTIMATED",
                "A small-business PD scorecard",
                "Forty-two coefficients from a logistic regression over eight years of "
                "originations. Here the fitting questions are exactly the right ones: the sample "
                "and whether it is representative, the estimator, out-of-time performance, "
                "calibration. This is the artefact the whole evidence apparatus was designed "
                "around, which is why it never causes trouble.",
            ),
            (
                "T6 · OPAQUE",
                "A bought-in bureau score",
                "The dials exist — somebody at the bureau fitted them — and neither they nor the "
                "act that set them is reachable. Demanding development documentation is futile. "
                "Watching the composite against your own realised defaults is not a compromise "
                "forced by commerce; it is what the structure says is the only evidence "
                "obtainable, so it is where review effort belongs.",
            ),
        ],
        "note": "Paper §2.3, the corollary that a demand for fitting evidence is well-typed "
        "exactly when the dials are neither absent nor unreachable, and the worked triple that "
        "follows it.",
    },
    {
        "kind": "bullets",
        "kicker": "Why it has to be computed",
        "title": "A monitor that ran for two years and meant nothing",
        "intro": "Evidence requirements, lifecycles, monitors and documents are one family "
        "indexed by kind of artefact. Two properties of such a family are worth having, and an "
        "index somebody types in cannot deliver both.",
        "items": [
            (
                "The story",
                "A discount-curve pricer is registered, and somebody attaches a performance "
                "monitor: discrimination against realised outcomes, evaluated monthly. It runs. "
                "It never fires. On the estate screen the model is green and monitored.",
            ),
            (
                "Why it meant nothing",
                "The pricer has no dials and no fitted relationship to outcomes, so "
                "discrimination is not a question about it. The monitor was not failing to "
                "detect anything; there was nothing of that kind to detect. That is worse than "
                "an absent monitor, because an absent one appears in the coverage worklist and a "
                "meaningless one reads as coverage.",
            ),
            (
                "Adding a kind should cost only that kind",
                "Supply the requirements for a new class and nothing already judged is "
                "disturbed. That guarantee is worth having, and worth nothing unless every kind "
                "actually carries requirements — a drawer with no forms in it is worse than an "
                "absent drawer, because the cabinet looks complete.",
            ),
            (
                "Which is why the index is computed",
                "A closed list of kinds means admitting a new one edits the index rather than "
                "supplying requirements. An open list means a kind with no requirements can be "
                "written down at any moment, so the completeness check quantifies over a set "
                "that does not contain the values in use, and passes. An index computed from the "
                "artefact has neither horn.",
            ),
        ],
        "note": "Paper §2.4, “The classification is the index”: conservative extension, "
        "totality, and the proposition that a declared base admits no total family of "
        "obligations.",
    },
    {
        "kind": "bullets",
        "kicker": "A consequence for change control",
        "title": "A refit is a new point, not a new model",
        "items": [
            (
                "Two different events, usually recorded as one",
                "A new fitting procedure, a new input or a new output is a change of the model. "
                "New numbers from the same procedure on newer data is a change of dial settings "
                "within it. Mint a version for both and a supervisor asking whether the model "
                "changed between two dates has asked a question with two answers.",
            ),
            (
                "So a set of dial values is a record in its own right",
                "With its own identity, its own immutability and its own provenance: which act "
                "produced it, from which rows, over which window, approved by whom. A daily "
                "recalibration then governs the procedure once, and a periodic re-estimation "
                "governs each set of numbers.",
            ),
            (
                "Dials accumulate along a chain",
                "Wire one model into another and the combination has both sets. Nothing is "
                "absorbed, so recalibrating an upstream artefact is formally a change to "
                "everything downstream of it.",
            ),
            (
                "The daily recalibration nobody calls a change",
                "At 06:30 a discount curve is re-solved against market instruments. Downstream "
                "sit a swaption pricer, an XVA engine, a VaR engine and a capital plan, and "
                "formally every one has just changed. The change process records nothing, "
                "because curves are “market data”. The usual resolution is that "
                "recalibration inside a declared tolerance is governed by monitoring and outside "
                "it is a change event. The formalism does not choose — it forces somebody to "
                "notice a choice is being made, and to write the tolerance down.",
            ),
        ],
        "note": "Paper §2.7. In MAYA this is the parameter set: a governed object with its own "
        "approval, its own workflow state and its own lineage, distinct from the model version "
        "it belongs to.",
    },
    {
        "kind": "table",
        "kicker": "D2 · Fit",
        "title": "Four questions that were one question",
        "intro": "Each of these is asked somewhere in a model register, and in the registers we "
        "have examined each has a code path of its own: a variance routine, a slot loop, a "
        "contract refinement check — and for the dependency edge, frequently nothing at all.",
        "rows": [
            ["Where it is asked", "What it actually asks", "The comparison"],
            [
                "A replacement version",
                "May this version stand where the incumbent stood?",
                "Its inputs accept at least what the incumbent's did, and its outputs still "
                "provide what the incumbent's provided",
            ],
            [
                "Binding data to a model",
                "Does this feature set provide what the model declares it reads?",
                "The set's schema can stand in for the model's input contract",
            ],
            [
                "A dependency edge",
                "Does what the source produces arrive where the target reads it?",
                "The source's output schema can stand in for the target's input contract",
            ],
            [
                "One feature set, two models",
                "Can a single feature set serve both of these?",
                "The set can stand in for the greatest lower bound of the two contracts",
            ],
        ],
        "col_w": [2.4, 4.2, 5.0],
        "note": "Paper §3.1 and §3.5. Four implementations of one relation are four opportunities "
        "to disagree — predictably in the direction of permitting more, because a check that "
        "wrongly refuses is reported within the hour and a check that wrongly allows is not "
        "reported at all.",
    },
    {
        "kind": "bullets",
        "kicker": "The order",
        "title": "A can stand in for B: one relation, written down once",
        "items": [
            (
                "When one field accepts another",
                "Same datatype; nullable if the other is; a lower bound no greater and an upper "
                "bound no less, an absent bound being the widest there is. A can stand in for B "
                "when every field B declares is present in A at a field that accepts it.",
            ),
            (
                "Extra fields are free",
                "A may carry fields B does not. Nobody has to look at them, so a richer provider "
                "is always admissible — which is what makes the relation usable in a bank, where "
                "the feature set serving one model always carries more than that model reads.",
            ),
            (
                "Being fussier is not free",
                "Each shared field must accept at least what B's accepted. A replacement that "
                "rejects an input its predecessor took is a replacement that breaks a caller: "
                "somebody was relying on the old tolerance, and nothing recorded that they were.",
            ),
            (
                "And the direction is the one nobody guesses",
                "“Refinement” suggests narrowing, and a subtype is narrower in what it "
                "denotes. But a schema here is the set of inputs a slot will accept, and "
                "standing in for something means accepting at least what it accepted — so wider "
                "acceptance is admissible and narrower regresses. The two readings of "
                "“narrower” are easy to hold at once and impossible to hold "
                "consistently, and an order stated in the intuitive direction admits exactly the "
                "replacements that break callers.",
            ),
        ],
        "note": "Paper §3.2. This is why it is worth writing down as an order with a stated "
        "direction rather than as a rule of thumb: the failure a rule of thumb produces here is "
        "silent, and it is in the permissive direction.",
    },
    {
        "kind": "split",
        "kicker": "The meet and the join",
        "title": "Two derived schemas, and the question each one answers",
        "left": {
            "head": "The meet — what can serve both",
            "items": [
                (
                    "All the fields either one had, each loosened",
                    "Nullable if either is, the lesser lower bound, the greater upper bound, and "
                    "an absent bound absorbing.",
                ),
                (
                    "The question it answers",
                    "What would a single feature set have to provide in order to serve both of "
                    "these models? Nothing weaker will do, and anything at least as strong will.",
                ),
                (
                    "It is a greatest lower bound",
                    "So a refusal derived from it is not a heuristic. Everything that serves "
                    "both stands in for the meet, which makes the comparison against the meet "
                    "the whole of the test rather than a first pass.",
                ),
            ],
        },
        "right": {
            "head": "The join — what both promise",
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
                    "There is no least element: it would have to carry every field name that "
                    "could ever exist. The structure is a lattice on each finite fragment, which "
                    "is the only fragment anything inhabits.",
                ),
            ],
        },
        "note": "Paper §3.3. Two operations on one order rather than two unrelated constructions: "
        "the absorption law is what makes this a lattice, and it is why the four questions on "
        "the previous slide are genuinely one question rather than four similar ones.",
    },
    {
        "kind": "bullets",
        "kicker": "The partiality is the useful part",
        "title": "No meet, and the refusal that names the remedy",
        "items": [
            (
                "Two schemas can have no lower bound at all",
                "If a shared field name carries a different datatype on each side then no field "
                "accepts both, so nothing can serve both. The meet is partial, and the "
                "partiality is the informative part rather than a gap in the construction.",
            ),
            (
                "An empty answer is worse than an error",
                "Whoever asked has a decision to make, usually that these two models cannot "
                "share a feature set. An absent value threaded through three layers becomes a "
                "silent empty schema somewhere downstream; a named refusal carrying the slot, "
                "both datatypes and which side wanted each is the answer to the question that "
                "was actually asked.",
            ),
            (
                "A failure of the order splits into two different mistakes",
                "Names B has that A lacks are missing. Names A has that accept less than B's did "
                "are narrowed. The remedies differ: a missing slot means the wrong data was "
                "bound, and a narrowed one means somebody tightened a constraint without "
                "noticing it was a promise.",
            ),
            (
                "Which changes the character of a control",
                "“Incompatible” is a message. “Does not provide turnover; accepts "
                "less than before at dscr” is an instruction. Reporting every failure "
                "rather than the first is the difference between one round of correction and "
                "six.",
            ),
        ],
        "note": "Paper §3.4 and §3.6. MAYA implements the second half literally: a contract "
        "mismatch lists every attribute that misses "
        "(tests/test_warrants.py::test_contract_mismatch_is_refused_listing_every_attribute).",
    },
    {
        "kind": "bullets",
        "kicker": "Composition",
        "title": "An edge is a claim about types, not a line on a diagram",
        "items": [
            (
                "The check",
                "An edge from a to b asserts that a's output is read as an input by b, and holds "
                "only when a's output schema can stand in for b's input contract. Where it "
                "holds, the composite's own signature is derived — a's inputs, b's outputs — and "
                "type-correctness of a whole wiring is decidable.",
            ),
            (
                "Extra outputs are fine; a missing one is not",
                "A richer output composes, because the surplus is simply unread. A name the "
                "target reads and the source does not produce is a wire to nowhere, and the "
                "refusal names it.",
            ),
            (
                "A composite's contract is derived, never written down",
                "A signature somebody typed is a signature that can disagree with its parts. "
                "Deriving it means two members wanting one attribute at two datatypes is refused "
                "when the composite is defined, rather than discovered when it runs.",
            ),
            (
                "Not every relation between two models is a wire",
                "“Challenger of” and “benchmark for” record how somebody "
                "thinks about a model. There is no wire, so there is nothing to type — and "
                "treating a challenger as a dependency would inflate every blast radius it "
                "appears in.",
            ),
        ],
        "note": "Paper §4.1. Vocabulary is part of the formalism here: an edge named "
        "“feeds” is read in a bank as a nightly data drop, so where the reading goes "
        "wrong the defect is in the account rather than in the audience.",
    },
    {
        "kind": "bullets",
        "kicker": "Worked example",
        "title": "The wire that was a drawing",
        "intro": "An expected-credit-loss stack records that a PD model feeds a provisioning "
        "engine. Both entries have existed for two years, and the edge is on the diagram in "
        "every committee pack.",
        "items": [
            (
                "What the register held",
                "The PD model's current version produces a twelve-month probability of default. "
                "The provisioning engine's current version reads a lifetime one. Nobody had "
                "wired the two systems together.",
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
                "The edge is refused at the moment somebody records it, with the missing output "
                "named. The conversation that follows is the one that discovers the third model "
                "— which is the whole value of the refusal, and it is available only because the "
                "edge asserts something checkable.",
            ),
        ],
        "note": "Paper §4.1, the worked example following the composition type-check. In MAYA the "
        "same check runs when a composite model is defined (maya/formula/composite.py).",
    },
    {
        "kind": "bullets",
        "kicker": "What does not compose",
        "title": "Two banks, one curve or two",
        "intro": "Supervisory guidance asks that model risk be assessed both individually and in "
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
                "No risk assignment is both compositional — the whole being the join of its "
                "parts — and fragility-sensitive, where a network in which one artefact reaches "
                "more of the outputs rates strictly higher than one in which it reaches fewer, "
                "the multiset of constituent risks being equal. Two distinct ratings in the "
                "scale are enough to force the contradiction, so no richer scale escapes it.",
            ),
        ],
        "note": "Paper §4.2. This is a negative result and it is here deliberately: an account "
        "that only derives is an advertisement, and the boundary of what can be derived is as "
        "much a design input as the derivations are.",
    },
    {
        "kind": "bullets",
        "kicker": "The obstruction",
        "title": "It is the sharing itself, so no assumption removes it",
        "items": [
            (
                "The two networks differ in exactly one thing",
                "One takes an output and hands it to two consumers; the other runs two "
                "independent instances. Shared dependency is that copy — a piece of the "
                "structure, not a correlation assumption somebody chose badly.",
            ),
            (
                "So a better dependency assumption does not help",
                "There is nothing to estimate. The difference between the two banks is not a "
                "number that was got wrong; it is a distinction the arithmetic of joining "
                "constituent ratings cannot express at all.",
            ),
            (
                "The result is a constraint, not a measure",
                "It says what a correct aggregate cannot be. It does not construct one, and an "
                "account claiming otherwise would be selling the thing it had just proved "
                "impossible.",
            ),
            (
                "What remains is laxity, and it is the useful quantity",
                "Any fragility-sensitive assignment is at best lax: the whole is at least the "
                "join of its parts. The discrepancy is the interaction premium, and it is what "
                "the guidance is actually asking about — so a correct aggregate reports the join "
                "of the constituents, the composite figure, and the difference attributed to "
                "common dials, common inputs, common fitting evidence and common methodology. "
                "The first three are computable from a typed graph; the fourth is not, and an "
                "aggregate that implies it is becomes decorative.",
            ),
        ],
        "note": "Paper §4.2, the remark identifying the copy as the obstruction and the corollary "
        "that laxity is necessary. MAYA computes the first three attributions from lineage and "
        "does not claim the fourth.",
    },
    {
        "kind": "bullets",
        "kicker": "D3 · Currency",
        "title": "The point-in-time read, stated as an operator",
        "intro": "Part 1 gave the rule in words: the latest fact that was both true by the "
        "decision date and known by the decision date. Written as an operator it acquires two "
        "properties a convention cannot have — it can be reasoned about, and it can be wrong in "
        "a way somebody notices.",
        "items": [
            (
                "The admissible set",
                "For a label time — the moment the decision was taken — and an observation time "
                "at which the assembly is run, the records admissible for a row are those whose "
                "event time is at or before the label, and whose ingest time is at or before the "
                "earlier of the label and the observation.",
            ),
            (
                "The read",
                "The latest admissible record, by event time and then by ingest time. It is "
                "undefined when nothing is admissible, rather than empty: a row for which "
                "nothing could have been known is a different fact about the world from a row "
                "whose value was zero, and an operator returning the same thing for both would "
                "lose it.",
            ),
            (
                "Both bounds are present because they refuse different things",
                "The event bound is what the world had done by the moment of the decision. The "
                "ingest bound is what could have been known at that moment. A read with one "
                "clock answers a question nobody asked — what do we think now about what was "
                "true then — and answers it without saying so.",
            ),
            (
                "And the ingest bound is the earlier of the two, not the observation",
                "The observation time is a single date for a whole assembly and is usually far "
                "later than any individual label. Bounding knowledge by the assembly date "
                "admits, for every early row, everything learned between that row's own decision "
                "date and the moment somebody pressed the button.",
            ),
        ],
        "note": "Paper §5.2. That last bound is one character of the definition and it is the "
        "whole guarantee; its omission is invisible in every test that does not restate a fact.",
    },
    {
        "kind": "table",
        "kicker": "Four properties",
        "title": "And the fourth one is reproducibility",
        "intro": "Each is elementary to prove and none is ornamental. Together they are the "
        "difference between a read that is correct and a read that is stable — and the fourth "
        "makes reproducibility a property of the operator rather than of the discipline of "
        "whoever re-runs it.",
        "rows": [
            ["Property", "What it says", "Why it is worth having"],
            [
                "Idempotent",
                "Reading the record it just returned returns that record",
                "A cached row and a recomputed row agree, so the operator may be applied twice "
                "without an answer moving",
            ],
            [
                "Commutes with projection",
                "Dropping non-clock columns before or after the read gives the same row",
                "Admissibility depends on the two clocks alone, so a narrower query is the same "
                "query rather than a cheaper approximation of it",
            ],
            [
                "Monotone in the observation time",
                "A later observation admits a superset",
                "Nothing that was knowable stops being knowable. It is monotonicity of the set "
                "and not of the chosen row, which is why the fourth property has to be separate",
            ],
            [
                "Saturating at the label",
                "At every observation at or after the label, the admissible set is the same set",
                "A row assembled at any time after its label is the row that would have been "
                "assembled at the label, whatever arrived in between. This is reproducibility, "
                "and it is what the earlier-of-the-two bound buys",
            ],
        ],
        "col_w": [2.5, 4.0, 5.1],
        "note": "Paper §5.2. Without saturation a re-run quietly improves on the original, and "
        "the numbers then agree with nothing — including themselves. Nobody notices, because the "
        "second set is better by every measure that gets looked at.",
    },
    {
        "kind": "bullets",
        "kicker": "Where the data may live",
        "title": "Copy, do not connect",
        "intro": "The operator is usually read as a statement about how to query a store. It is "
        "also a statement about which stores may be queried at all, and the second reading is "
        "the operational one.",
        "items": [
            (
                "The guarantee has two premises about the store",
                "That every record carries both clocks, and that a correction appends rather "
                "than amends. Neither is a property of the query, so no operator applied at read "
                "time can supply what the store does not keep.",
            ),
            (
                "A source that overwrites has neither",
                "An ordinary warehouse table, a view maintained by a nightly job, a file "
                "replaced on a schedule: the May row is simply gone once the August restatement "
                "lands, and what the June decision saw cannot be recovered by anybody.",
            ),
            (
                "And the read does not fail",
                "It returns the restated number and says nothing, which is the failure mode the "
                "operator exists to eliminate. Binding a model's input directly to an external "
                "table implements a query that usually agrees with the operator: the two are "
                "indistinguishable until the first restatement, and indistinguishable again "
                "afterwards, because nothing records that they diverged.",
            ),
            (
                "So pull the source, and read the snapshot",
                "An external source is read once, given its two clocks, and written into storage "
                "under the platform's own control as an immutable, versioned snapshot; models "
                "read the snapshot. Connecting is cheaper and gives up the guarantee — this is "
                "not a preference between storage technologies but the observation that an "
                "operator defined over rows that can be overwritten is defined over the wrong "
                "object.",
            ),
        ],
        "note": "Paper §5.4. It is also the reason MAYA has a lake of its own rather than a set "
        "of connectors: maya/storage/lake.py, the append-only ingest log every source writes to.",
    },
    {
        "kind": "table",
        "kicker": "D4 · Support",
        "title": "Keep the shape, change the arithmetic",
        "intro": "Assurance evidence is a derivation rather than a log: this rests on that test "
        "and that approval; this requirement is met by this route or that one. Evidence has a "
        "fixed shape — joint dependence, and alternative routes — so it needs one operation for "
        "each. Swap the pair, and the same traversal answers a different question.",
        "rows": [
            ["The arithmetic", "Alternatives, joint dependence", "The question it answers"],
            ["true or false", "or, and", "Is the claim supported at all?"],
            ["counting", "plus, times", "How many independent derivations corroborate it?"],
            [
                "minimal supports",
                "absorptive union, pairwise union",
                "Which smallest set of evidence would suffice?",
            ],
            [
                "polynomials over the evidence",
                "plus, times",
                "Exactly how was it derived — counting distinct routes, and repeated use of one "
                "fact?",
            ],
            ["confidence", "max, times", "How much should the conclusion be trusted?"],
            ["least cost", "min, plus", "What is the cheapest way to close a gap?"],
            ["sets of regimes", "intersection, union", "For which regimes is it admissible?"],
        ],
        "col_w": [2.7, 3.4, 5.5],
        "note": "Paper §6.1. Annotating the derivation once in the richest of these keeps "
        "everything, so the others are read off it rather than recomputed — and where a direct "
        "evaluation and a projection disagree, one of the two routes is not structure-preserving, "
        "which is a fact about the evidence rather than a bug in a report.",
    },
    {
        "kind": "bullets",
        "kicker": "One layer across",
        "title": "The ingest clock of a derived feature, as arithmetic that cannot be forgotten",
        "items": [
            (
                "The rule, as arithmetic",
                "The moment a derived feature became knowable is the latest ingest time among "
                "the base features it reads. Stated that way it is a rule, and a rule can have "
                "exceptions somebody forgets.",
            ),
            (
                "The rule, as a consequence of the derivation",
                "It is the derivation itself, evaluated with each base feature replaced by its "
                "own ingest time. The upgrade is not cosmetic: every route to the number now "
                "goes through the same object, so there is no exception to forget.",
            ),
            (
                "What does this rest on?",
                "The base features the derivation actually reads — deliberately not the "
                "transitive ancestor set, because the two answer different questions. The "
                "ancestor walk returns every ancestor, derived ones included, which is the right "
                "answer to what breaks if this changes. The base features are the right answer "
                "to what data this ultimately reads.",
            ),
            (
                "Does it touch the label?",
                "Whether the target's own feature appears among those base features. A feature "
                "derived from a derivation of the target is still the target, so leakage "
                "detection becomes a membership test rather than a graph walk with a depth limit "
                "and a hope.",
            ),
        ],
        "note": "Paper §6.2. Two routes to one answer are worth having only while they agree, so "
        "the identity between them is asserted rather than assumed.",
    },
    {
        "kind": "bullets",
        "kicker": "A negative result, and its repair",
        "title": "A zero that does not annihilate",
        "items": [
            (
                "The valuation that looked obvious",
                "“As of when is this claim current?” — take the later of the two, for "
                "alternatives and for joint dependence alike. It is not a valuation of the "
                "derivation at all, and no choice of constants inside its own carrier repairs "
                "it.",
            ),
            (
                "Why not",
                "An identity for “the later of” has to be the least element, and so "
                "does the one, so the two coincide and the whole carrier collapses to a point. "
                "Independently, annihilation fails outright: combine the zero with a real "
                "timestamp and the timestamp comes back.",
            ),
            (
                "Which is a practical defect rather than a technicality",
                "A claim resting on a missing fact reports the currency of the facts that are "
                "present, instead of reporting that it has none. A structure answering “as "
                "of when” for a claim it cannot support is exactly the kind of instrument "
                "that reads as reassurance — and this shape is easy to build three times without "
                "noticing, because each instance looks like sensible arithmetic.",
            ),
            (
                "The repair is elementary, and it is the whole point",
                "Adjoin a fresh bottom meaning no derivation: the identity for alternatives, and "
                "absorbing for joint dependence. Then a claim resting on a missing fact "
                "evaluates to “not current at all”. The zero has to be a new element "
                "meaning no support, never the least of the old ones — the same move that makes "
                "an undeclared licence read as terms unknown, which an export can refuse by "
                "name, instead of as the most permissive licence there is.",
            ),
        ],
        "note": "Paper §6.3. MAYA's licence algebra takes the repair literally: an object with no "
        "declared terms inherits terms unknown, and an export that would breach unknown terms is "
        "refused rather than permitted (maya/security/licence.py).",
    },
    {
        "kind": "bullets",
        "kicker": "The complement, drawn honestly",
        "title": "Facts that constitute the standard they would be checked against",
        "intro": "An account arguing that four facts derive owes an account of the ones that do "
        "not. Three kinds are worth telling apart, and only the third is irreducible.",
        "items": [
            (
                "Derived from a declared rule",
                "A risk classification, a control requirement, a scope determination: computing "
                "one is deterministic and involves no judgement. The judgement lives in "
                "supplying the inputs and in choosing the function — and the function "
                "constitutes the standard, so there is no independent specification against "
                "which a proposed one could be checked.",
            ),
            (
                "Which is worth constraining even so",
                "Require the tiering map to be monotone and nothing that can be learned about a "
                "model will move it into a lighter regime as it becomes more consequential. That "
                "is trivial as mathematics, exactly the guarantee an examiner seeks, and exactly "
                "what an unconstrained scoring formula fails to provide.",
            ),
            (
                "Declared, but with an oracle attached",
                "One artefact may sit outside one regime's governed population, inside a "
                "second's, high-risk under a third and a financial-reporting key control under a "
                "fourth. These are four logical systems, each with its own vocabulary — and once "
                "each is encoded, a determination computed natively and one computed on the "
                "translated obligation must agree, so a disagreement witnesses a defect in the "
                "encoding rather than a genuine conflict between regimes.",
            ),
            (
                "Irreducibly declared",
                "Concluding a validation, granting an approval, accepting residual risk, "
                "choosing the tiering rule. These are not weakly-checkable tasks conservatively "
                "withheld from derivation; they have no notion of correctness independent of the "
                "authority exercising them, and a system pretending otherwise would be "
                "manufacturing an answer rather than recording a decision.",
            ),
        ],
        "note": "Paper §7. MAYA implements the last line as its workflow primitive: an approval "
        "is a role and a count, and the platform records who exercised it rather than computing "
        "what it should have been.",
    },
    {
        "kind": "split",
        "kicker": "The same boundary, from the other side",
        "title": "Where a machine may do the work",
        "intro": "If an answer can be checked it matters little what produced it: a wrong one is "
        "caught and discarded, and the only cost is wasted effort. If it cannot be checked, then "
        "trusting the answer is trusting the producer, and no amount of process changes that. So "
        "the useful question is not whether the generator is good enough but whether there is a "
        "check — and there is one exactly where the fact derives from structure.",
        "left": {
            "head": "A check exists, so an error costs throughput",
            "items": [
                (
                    "Encode a regulatory regime",
                    "An encoding either keeps truth invariant under translation or it does not. "
                    "Expensive expert work becomes cheap proposal and mechanical verification, "
                    "and the expert adjudicates rather than authors.",
                ),
                (
                    "Bind data to a model, or wire two models",
                    "Both are the one order of D2. A refusal names the slot that is missing or "
                    "the one that narrowed.",
                ),
                (
                    "Assemble fitting evidence, and cite it",
                    "The point-in-time operator, recomputed by a route that does not reuse the "
                    "one that assembled the rows; and a citation checked by evaluating the "
                    "derivation in true-or-false arithmetic.",
                ),
            ],
        },
        "right": {
            "head": "No check exists, so the answer is its producer",
            "items": [
                (
                    "Choose the tiering rule",
                    "It constitutes the standard, so there is nothing independent for it to be "
                    "checked against.",
                ),
                (
                    "Conclude a validation, or accept residual risk",
                    "Correctness here is not a property of the text. It is an exercise of "
                    "authority, and the boundary is drawn by the mathematics rather than by risk "
                    "appetite — which is worth scrutinising in proportion to how comfortable a "
                    "conclusion it is.",
                ),
                (
                    "And one honest exception",
                    "Sampled agreement between a stated formula and an implementation can refute "
                    "the implementation and can never certify it, so however many samples it "
                    "draws it is not a check in this sense. A report saying so in its first four "
                    "words is worth more than one that passes quietly.",
                ),
            ],
        },
        "note": "Paper §9. MAYA's assistant sits entirely in the left column: it proposes, it "
        "never approves, it never blocks, and it never writes to a sealed object.",
    },
    {
        "kind": "bullets",
        "kicker": "Part 2, in one slide",
        "title": "Four declarations that need not be made, and two that do",
        "items": [
            "What kind of artefact this is derives from how its dials are filled, which makes a "
            "closed-form pricer a type rather than an exception, and a meaningless monitor a "
            "refusal rather than a green light.",
            "Whether one thing fits where another fitted derives from a single order, whose meet "
            "answers a question four separate implementations could not even ask, and whose "
            "failure to have a meet is the honest answer to whether one feature set can serve "
            "two models.",
            "What a training row could have known derives from an operator whose fourth property "
            "is reproducibility, and which is supplied by taking the earlier of two dates — easy "
            "to omit, and invisible when omitted.",
            "What a claim rests on derives from one annotated derivation, and so does the ingest "
            "clock of a derived feature, which turns a rule somebody could forget into arithmetic "
            "with no exceptions.",
            "Against that: aggregate risk cannot be both additive and sensitive to a single point "
            "of failure, because the obstruction is the sharing itself; and currency is a "
            "well-behaved valuation only once “no support” has a value of its own.",
            "And some facts — the tiering rule, the regime encoding, the approval — constitute "
            "the standard they would be checked against, which is also the reason a machine may "
            "propose them and may not settle them.",
            (
                "Where to read the proofs",
                "docs/research/ — “Models as Parametric Kernels: An Order, an Operator and a "
                "Polynomial”, with the statements above in full and the source for each "
                "construction.",
            ),
        ],
        "note": "Paper §13, the conclusion. Part 3 turns to what MAYA stores, in the vocabulary "
        "Part 1 built and under the constraints Part 2 derived.",
    },
]

SLIDES = DERIVED
