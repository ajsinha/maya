"""
The concepts deck, parts four to six: the operator, the polynomial, and the
boundary where derivation stops.

Split from ``concepts_deck`` only to keep each file short enough to read. The
deck is one list of slide specs; this module holds the second half of it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

OPERATOR = [
    {
        "kind": "divider",
        "num": "4",
        "title": "One operator",
        "sub": "A fact carries two independent times: the moment it held in the world, and the "
        "moment the recording system learned it. Conflating them is the dominant silent failure "
        "in this domain, because it improves every metric it corrupts. The remedy is not a "
        "convention in whoever wrote the query; it is an operator with laws.",
        "points": [
            "Two clocks, and the one people drop",
            "The admissible set, and the read",
            "Four properties, and the min",
            "Where the data may live",
        ],
    },
    {
        "kind": "split",
        "kicker": "Two clocks",
        "title": "When it was true, and when you found out",
        "left": {
            "head": "What a record carries",
            "items": [
                (
                    "Event time",
                    "The moment the fact held in the world — the date a value is about.",
                ),
                (
                    "Ingest time",
                    "The moment the recording system could first have known it.",
                ),
                (
                    "So a restatement is a new record",
                    "Same event time, later ingest time, and nothing overwritten. The earlier "
                    "answer stays derivable, which is the property every guarantee in this part "
                    "rests on: a store that amends in place has no earlier answer to return.",
                ),
            ],
        },
        "right": {
            "head": "What goes wrong when they are one",
            "items": [
                (
                    "Look-ahead leakage",
                    "An artefact fitted on facts that had not been recorded when the decision was "
                    "taken assesses excellently and performs badly. It has been shown the answers.",
                ),
                (
                    "And the post-mortem blames drift",
                    "The failure is invisible to every performance metric, because it improves "
                    "them. That is what makes it the dominant silent failure rather than merely a "
                    "common one: nothing in the numbers asks to be investigated.",
                ),
                (
                    "The rule, and the half that gets dropped",
                    "Use the latest fact that was both true by the decision date and known by the "
                    "decision date. The second half is the one people drop, usually by bounding "
                    "knowledge with “now” instead.",
                ),
            ],
        },
        "note": "Paper §5.1, “Two clocks”, and the plain-terms gloss that follows it.",
    },
    {
        "kind": "bullets",
        "kicker": "The read as an operator",
        "title": "An admissible set, and the latest thing in it",
        "items": [
            (
                "The admissible set",
                "For a label time ℓ — the moment the decision was taken — and an observation time "
                "a at which the assembly is run, the records admissible for a row are those whose "
                "event time is at or before ℓ and whose ingest time is at or before min(ℓ, a).",
            ),
            (
                "The read",
                "The latest admissible record, by event time and then by ingest time. It is "
                "undefined when nothing is admissible, rather than empty: a row for which nothing "
                "could have been known is a different fact about the world from a row whose value "
                "was zero, and an operator that returned the same thing for both would lose it.",
            ),
            (
                "Both bounds are present because they refuse different things",
                "The event bound is what the world had done by the moment of the decision. The "
                "ingest bound is what could have been known at that moment. A read with one clock "
                "answers a question nobody asked — what do we think now about what was true then "
                "— and answers it without saying so.",
            ),
            (
                "And the ingest bound is min(ℓ, a), not a",
                "Because a is a single scalar for a whole assembly and is usually far later than "
                "any individual label. Bounding knowledge by the assembly date admits, for every "
                "early row, everything learned between that row's own decision date and the "
                "moment somebody pressed the button. The min is one character and it is the whole "
                "guarantee; its omission is invisible in every test that does not restate a fact.",
            ),
        ],
        "note": "Paper §5.2, “The read as an operator”: the admissible set and the point-in-time "
        "read, and the observation that the correct ingest bound is the earlier of the label and "
        "the observation.",
    },
    {
        "kind": "table",
        "kicker": "Four properties",
        "title": "And the fourth one is reproducibility",
        "intro": "Each is elementary to prove and none is ornamental: together they are the "
        "difference between a read that is correct and a read that is stable. The fourth makes "
        "reproducibility a property of the operator rather than of the discipline of whoever "
        "re-runs it.",
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
                "Admissibility and the ordering depend on the two clocks alone, so a narrower "
                "query is the same query rather than a cheaper approximation of it",
            ],
            [
                "Monotone in the observation time",
                "A later observation admits a superset",
                "Nothing that was knowable stops being knowable. It is monotonicity of the set "
                "and not of the chosen row, which is why the fourth property has to be separate",
            ],
            [
                "Saturating at the label",
                "At every observation time at or after the label, the admissible set is the same "
                "set",
                "A row assembled at any time after its label is the row that would have been "
                "assembled at the label, whatever arrived in between. This is reproducibility, "
                "and it is what the min buys",
            ],
        ],
        "col_w": [2.5, 4.0, 5.1],
        "note": "Paper §5.2, the four properties and the corollary that saturation is the "
        "reproducibility guarantee.",
    },
    {
        "kind": "bullets",
        "kicker": "Worked example",
        "title": "The filed accounts that were restated",
        "intro": "A borrower files Q1 accounts dated 31 March. They land in the warehouse on "
        "20 May. The bank declines an application on 15 June. In August the borrower restates "
        "those accounts downward, from a debt-service ratio of 1.20 to 0.40. Both rows are true "
        "and both belong in the store: same event time, different ingest times.",
        "items": [
            (
                "Read with one clock",
                "The training row for the June decision gets 0.40, because that is the current "
                "value for Q1. The model learns to predict defaults using a number that exists "
                "because the default already happened.",
            ),
            (
                "Read with two",
                "It gets 1.20 — and by saturation it still gets 1.20 when the set is rebuilt in "
                "2028, after two more restatements.",
            ),
            (
                "And the row labelled in September gets 0.40",
                "Correctly, because by then the restatement was knowable. The operator is not a "
                "rule for ignoring restatements; it is a rule about the moment each one becomes "
                "admissible, and it gives a different answer for each label date.",
            ),
            (
                "Which is the least useful kind of reproducibility to lack",
                "Without saturation a re-run quietly improves on the original, and the numbers "
                "then agree with nothing — including themselves. Nobody notices, because the "
                "second set is better by every measure that gets looked at.",
            ),
        ],
        "note": "Paper §5.2, the worked example of the restated accounts, read against the "
        "reproducibility corollary.",
    },
    {
        "kind": "bullets",
        "kicker": "Where the data may live",
        "title": "Copy, do not connect",
        "intro": "The operator is usually read as a statement about how to query a store. It is "
        "also a statement about which stores may be queried at all, and the second reading is the "
        "operational one.",
        "items": [
            (
                "The guarantee has two premises about the store",
                "That every record carries both clocks, and that a restatement appends rather "
                "than amends. Neither is a property of the query, so no operator applied at read "
                "time can supply what the store does not keep.",
            ),
            (
                "A source that overwrites has neither",
                "An ordinary warehouse table, a view maintained by a nightly job, a file replaced "
                "on a schedule: the 20 May row is simply gone once the August restatement lands, "
                "and what the June decision saw cannot be recovered by anybody.",
            ),
            (
                "And the read does not fail",
                "It returns 0.40 and says nothing, which is the failure mode the operator exists "
                "to eliminate. Binding a model's input slot directly to an external table "
                "implements a query that usually agrees with the operator: the two are "
                "indistinguishable until the first restatement, and indistinguishable again "
                "afterwards, because nothing records that they diverged.",
            ),
            (
                "So pull the source, and read the snapshot",
                "An external source is read once, given its two clocks, and written into storage "
                "under the platform's own control as an immutable, versioned snapshot; models "
                "read the snapshot. Connecting is cheaper and gives up the guarantee. This is not "
                "a preference between storage technologies — it is the observation that an "
                "operator defined over rows that can be overwritten is defined over the wrong "
                "object, and the guarantee it appears to offer is a guarantee about a table that "
                "no longer exists.",
            ),
        ],
        "note": "Paper §5.4, “A corollary about where the data may live”, which constrains the "
        "operator's argument as tightly as its definition.",
    },
]

POLYNOMIAL = [
    {
        "kind": "divider",
        "num": "5",
        "title": "One polynomial",
        "sub": "Assurance evidence is a derivation rather than a log: this rests on that test and "
        "that approval; this requirement is met by this route or that one. Annotate it once in the "
        "free commutative semiring and every other question about it is the same traversal with "
        "different arithmetic — which is a theorem and not a coincidence.",
        "points": [
            "One traversal, many questions",
            "The ingest clock as a homomorphism",
            "A zero that does not annihilate",
        ],
    },
    {
        "kind": "table",
        "kicker": "One traversal, many questions",
        "title": "Keep the shape, change the arithmetic",
        "intro": "Evidence has a fixed shape — joint dependence, and alternative routes — so it "
        "needs one operation for each. Swap the pair and the same computation answers a different "
        "question. Evaluating in the polynomial keeps everything, so the others are read off it "
        "rather than recomputed; and where a direct evaluation and a pushforward disagree, one of "
        "the two routes is not a homomorphism, which is a fact about the structure.",
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
        "note": "Paper §6.1, the universality of the free commutative semiring ℕ[X] and the table "
        "of valuations over it, with the remark on which minimal-support semiring is the right one.",
    },
    {
        "kind": "bullets",
        "kicker": "One layer across",
        "title": "The ingest clock of a derived feature is a homomorphism",
        "items": [
            (
                "The rule, as arithmetic",
                "The moment a derived feature became knowable is the latest ingest time among the "
                "base features it reads. That was documented as arithmetic, on the grounds that "
                "arithmetic cannot be forgotten.",
            ),
            (
                "The rule, as a homomorphism",
                "It is the image of the derivation's polynomial under the valuation that sends "
                "each base feature to its own ingest time. The upgrade is not cosmetic: a rule can "
                "have exceptions somebody forgets, and a homomorphism cannot, because every route "
                "to the number goes through the same object.",
            ),
            (
                "What does this rest on?",
                "The free variables of the polynomial — and deliberately not the transitive "
                "ancestor set, because the two answer different questions. The ancestor walk "
                "returns every ancestor, derived ones included, which is the right answer to what "
                "breaks if this changes. The free variables are the base features and nothing "
                "else, which is the right answer to what data this ultimately reads. Two routes "
                "to one answer are worth having only while they agree, so the identity between "
                "them is asserted rather than assumed.",
            ),
            (
                "Does it touch the label?",
                "Membership of the label's variable in the free variables. A feature derived from "
                "a derivation of the label is still the label, so leakage detection becomes a "
                "membership test rather than a graph walk with a depth limit and a hope.",
            ),
        ],
        "note": "Paper §6.2, “One layer across: derived features”: the ingest clock as a "
        "homomorphism, and the two questions that fall out of the same polynomial.",
    },
    {
        "kind": "bullets",
        "kicker": "A negative result, and its repair",
        "title": "A zero that does not annihilate",
        "items": [
            (
                "The valuation that looked obvious",
                "“As of when is this claim current?” — take the later of the two, for alternatives "
                "and for joint dependence alike. It is not a valuation of the derivation at all, "
                "and no choice of constants inside its own carrier repairs it.",
            ),
            (
                "Why not",
                "An identity for “the later of” has to be the least element, and so does the one, "
                "so the two coincide and the whole carrier collapses to a point. Independently, "
                "annihilation fails outright: combine the zero with a real timestamp and the "
                "timestamp comes back.",
            ),
            (
                "Which is a practical defect rather than a technicality",
                "A claim resting on a missing fact reports the currency of the facts that are "
                "present, instead of reporting that it has none. A structure that answers “as of "
                "when” for a claim it cannot in fact support is exactly the kind of instrument "
                "that reads as reassurance — and this shape is easy to build three times without "
                "noticing, because each instance looks like sensible arithmetic.",
            ),
            (
                "The repair is elementary, and it is the whole point",
                "Adjoin a fresh bottom ⊥ meaning no derivation: the identity for alternatives, "
                "and absorbing for joint dependence. Then a claim resting on a missing fact "
                "evaluates to “not current at all”. The zero has to be a new element meaning no "
                "support, never the least of the old ones — the same move that makes an undeclared "
                "licence read as terms unknown, which an export can refuse by name, instead of as "
                "the most permissive licence there is.",
            ),
        ],
        "note": "Paper §6.3, the proposition that taking the later of two times for both "
        "operations is not a semiring, and the proposition that adjoining an absorbing zero "
        "repairs it. An aggregate over the routes is a further construction and not a valuation.",
    },
]

DECLARED = [
    {
        "kind": "divider",
        "num": "6",
        "title": "What must still be declared",
        "sub": "An account arguing that four facts derive owes an account of the ones that do not. "
        "Three kinds are worth telling apart, and only the third is irreducible — and the "
        "boundary, drawn for governance reasons, turns out to answer a question nobody set out to "
        "ask.",
        "points": [
            "Facts that constitute the standard",
            "Declared, with an oracle attached",
            "Where a machine may do the work",
        ],
    },
    {
        "kind": "bullets",
        "kicker": "The complement, drawn honestly",
        "title": "Facts that constitute the standard they would be checked against",
        "items": [
            (
                "Derived from a declared rule",
                "A risk classification, a control requirement, a scope determination: computing "
                "one is deterministic and involves no judgement at all. The judgement lives in "
                "supplying the inputs and in choosing the function — and the function constitutes "
                "the standard, so there is no independent specification against which a proposed "
                "one could be checked.",
            ),
            (
                "Which is worth constraining even so",
                "Require the tiering map to be monotone and nothing that can be learned about a "
                "model will move it into a lighter regime as it becomes more consequential. That "
                "is trivial as mathematics and exactly the guarantee an examiner seeks, and "
                "exactly what an unconstrained scoring formula fails to provide. Put the required "
                "controls and the tiers in an adjunction and “the controls meet the tier's "
                "requirements” and “the tier is within what those controls can defend” become one "
                "statement, so a control deficiency and an inflated classification are one defect "
                "seen from two sides.",
            ),
            (
                "Declared, but with an oracle attached",
                "One artefact may sit outside one regime's governed population, inside a "
                "second's, high-risk under a third and a financial-reporting key control under a "
                "fourth. These are not four values of one attribute but four logical systems, each "
                "with its own vocabulary and its own notion of what makes a sentence true of an "
                "inventory. Encode each as an institution and truth must be invariant under "
                "translation, so any disagreement between a determination computed natively and "
                "one computed on the translated obligation witnesses a defect in the encoding "
                "rather than a genuine conflict between regimes.",
            ),
            (
                "Irreducibly declared",
                "Concluding a validation, granting an approval, accepting residual risk, choosing "
                "the tiering rule. These are not weakly-checkable tasks conservatively withheld "
                "from derivation; they have no notion of correctness independent of the authority "
                "exercising them, and a system that pretended otherwise would be manufacturing an "
                "answer rather than recording a decision.",
            ),
        ],
        "note": "Paper §7, “What must still be declared”: constitutive rules, monotone "
        "classification, control adequacy as an adjunction, and the stability of a determination "
        "under translation.",
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
            "head": "A check exists, so the error rate costs throughput",
            "items": [
                (
                    "Encode a regulatory regime",
                    "The satisfaction condition: an encoding either keeps truth invariant under "
                    "translation or it does not. Expensive expert work becomes cheap proposal and "
                    "mechanical verification, and the expert adjudicates rather than authors.",
                ),
                (
                    "Bind data to a model, or wire two models",
                    "S(F) ⊑ in(k), and out(a) ⊑ in(b). A refusal names the slot that is missing "
                    "or the one that narrowed.",
                ),
                (
                    "Assemble fitting evidence, and cite it",
                    "The point-in-time operator, recomputed by a route that does not reuse the "
                    "one that assembled the rows; and a citation checked by evaluating the "
                    "derivation in true-or-false arithmetic, which is an evaluation rather than a "
                    "second opinion.",
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
                    "draws it is not a check in this sense. A report that says so in its first "
                    "four words is worth more than one that passes quietly.",
                ),
            ],
        },
        "note": "Paper §9, “Automation is the same boundary”: the definition of an oracle, the "
        "admissibility proposition, and the table of tasks that have one and tasks that cannot.",
    },
    {
        "kind": "bullets",
        "kicker": "In one slide",
        "title": "Four declarations that need not be made, and two that do",
        "items": [
            "What kind of artefact this is derives from how its parameter object is inhabited, "
            "which makes a closed-form pricer a type rather than an exception.",
            "Whether one thing fits where another fitted derives from a single partial order, "
            "whose meet answers a question four separate implementations could not even ask, and "
            "whose failure to have a meet is the honest answer to whether one feature set can "
            "serve two models.",
            "What a training row could have known derives from an operator whose fourth property "
            "— saturation at the label — is reproducibility, and is supplied by a min that is easy "
            "to omit and whose omission is invisible.",
            "What a claim rests on derives from a polynomial, and so does the ingest clock of a "
            "derived feature, which upgrades a rule somebody could forget into a homomorphism "
            "with no exceptions.",
            "Against that: aggregate risk cannot be both additive and sensitive to a single point "
            "of failure, because the obstruction is the copy map; and currency over a totally "
            "ordered carrier is a valuation only once “no support” has a value of its own.",
            "And some facts — the tiering rule, the regime encoding, the approval — constitute "
            "the standard they would be checked against, which is also the reason a machine may "
            "propose them and may not settle them.",
            (
                "Where to read more",
                "“Models as Parametric Kernels — An Order, an Operator and a Polynomial”, in "
                "docs/research/: the statements above with their proofs, the worked examples in "
                "full, and the sources for each construction.",
            ),
        ],
        "note": "Paper §13, the conclusion.",
    },
]

SLIDES = OPERATOR + POLYNOMIAL + DECLARED
