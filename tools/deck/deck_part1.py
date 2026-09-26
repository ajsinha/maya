"""
The deck, as data. Parts 1 and 2: why model governance fails, and the vocabulary from nothing.

One deck split across four modules only to keep each file under the repository's file-size gate; read them in order (see GUIDE.md).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

SLIDES: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "1",
        "title": "Why model governance fails",
        "sub": "Every bank keeps a model register, and most registers are lists of things people typed. "
        "This part says what supervisors now expect, where a typed register breaks, and what MAYA "
        "is in one sentence: a system of record whose facts are derived from the work, not "
        "declared about it.",
        "points": [
            "The question every model must answer",
            "What SR 11-7 and SS1/23 ask for",
            "Four places a register breaks",
            "MAYA, in one slide",
        ],
    },
    {
        "kind": "bullets",
        "kicker": "The question",
        "title": "Months later: which data, which mathematics, whose approval",
        "intro": "A committee asks about one number in last March's impairment charge. Three questions "
        "follow, and in most quantitative shops each is answered by archaeology rather than by "
        "a query. Everything in this deck exists to make all three a lookup.",
        "items": [
            (
                "Which data did it see?",
                "Not which table — which rows, with which values, as they stood on the day. The table "
                "has moved since: a vendor restated two quarters in August and the warehouse row was "
                "updated in place, so the number the model saw in March no longer exists anywhere.",
            ),
            (
                "Which mathematics did it run?",
                "There is a PDF that describes the model, a repository that implements it, and a "
                "spreadsheet the desk actually uses. All three were correct once. Nobody knows which "
                "of them is the model, and no test compares them.",
            ),
            (
                "Whose approval was it running under?",
                "There is an approval memo with a date. It does not name the version of the code, the "
                "numbers in the parameters, or the data the numbers were fitted on, so it approves a "
                "thing that cannot now be identified.",
            ),
            (
                "None of these is a documentation problem",
                "Each is a question about an object that was never stored. A better template does not "
                "help; the answer has to be a consequence of how the work is done.",
            ),
        ],
        "note": "Specification §1, the four reproducibility failures. Every part of this deck traces "
        "back to one of these three questions.",
    },
    {
        "kind": "table",
        "kicker": "What supervisors ask",
        "title": "Two supervisory statements, one set of expectations",
        "intro": "The Federal Reserve's SR 11-7 (2011) and the PRA's SS1/23 (2024) are written a decade "
        "apart and ask for the same things. Each row is an expectation, and where MAYA answers "
        "it from records it already keeps rather than from a form somebody fills in.",
        "rows": [
            ["Expectation", "SR 11-7 · SS1/23", "Where MAYA answers it"],
            [
                "A complete inventory, with materiality",
                "Inventory · Principle 1, model tiering",
                "The inventory export, tier derived from use, exposure, reach and a questionnaire",
            ],
            [
                "Sound development and documentation",
                "Development · Principle 3",
                "A specification bound to the formula's hash; nine required sections",
            ],
            [
                "Independent validation",
                "Validation · Principle 4",
                "Blind scoring on escrowed data; reconciliation; champion and challenger",
            ],
            [
                "Ongoing monitoring",
                "Monitoring · Principle 4.4",
                "Covenants on every reported run; dashboards graded ok, watch, breach",
            ],
            [
                "Issues tracked to closure",
                "Governance · Principle 2",
                "A findings register; nobody closes their own fix",
            ],
            [
                "Periodic review, and limits on use",
                "Governance · Principle 5",
                "Review intervals by tier; an overdue review suspends the model",
            ],
        ],
    },
    {
        "kind": "cards",
        "kicker": "Where a register breaks",
        "title": "Four failures a typed register cannot see",
        "cols": 2,
        "cards": [
            (
                "THE DATA MOVED",
                "Nobody can say which rows a model saw",
                "The warehouse row was restated in place in August. The number the model read in "
                "March no longer exists anywhere, and the register still says “trained on the loans "
                "table”.",
            ),
            (
                "THE CODE IS NOT THE MATHS",
                "Three artefacts, each correct once",
                "A PDF describes the model, a repository implements it, and the desk runs a "
                "spreadsheet. No test compares them, so nobody knows which of the three is the "
                "model.",
            ),
            (
                "THE BLACK BOX",
                "Bought, opaque, and still in use",
                "A vendor score or a neural network has no formula to review. A register records that "
                "it exists; it cannot record whether it still works on today's population.",
            ),
            (
                "THE PROMPT",
                "An LLM application nobody versioned",
                "A prompt edited on a Friday changes the model's behaviour as surely as a new "
                "coefficient, and no register sees the change or asks what it was tested on.",
            ),
        ],
    },
    {
        "kind": "bullets",
        "kicker": "MAYA, in one slide",
        "title": "A system of record whose facts are derived, not declared",
        "intro": "MAYA holds the models, the data they read and the licences to fit and run them, and "
        "derives the facts a register would ask somebody to type. It never trains a model and "
        "never serves a prediction: it is where the evidence lives, not where the arithmetic "
        "runs.",
        "items": [
            (
                "Data, frozen by content",
                "Features with two clocks — when a value was true and when it was known — and pins "
                "sealed by the hash of their rows.",
            ),
            (
                "Mathematics, as a typed tree",
                "A model's formula parsed from LaTeX, Python or Excel; code checked against it; a "
                "black box declared as one.",
            ),
            (
                "Licences, not documents",
                "Training and execution warrants that bind a model to data, expire, suspend "
                "themselves on a breach, and prove themselves offline.",
            ),
            (
                "Governance, from the same records",
                "Findings, tiers, reviews, monitoring, challengers, fairness evidence and the "
                "supervisory inventory, all read from the objects above.",
            ),
        ],
    },
    {
        "kind": "divider",
        "num": "2",
        "title": "The vocabulary, from nothing",
        "sub": "Nothing in this deck is used before it is defined. This part builds the vocabulary from "
        "nothing — kernel, parameter, feature, clock, feature set, training, pin, warrant — one "
        "idea to a slide, each carried by an example from a bank and each earning its place by "
        "naming the failure it prevents.",
        "points": [
            "The question every model must answer",
            "A kernel, and its dials",
            "Parameters, and the six ways they get set",
            "Features, and the two clocks",
            "Feature sets, and what a model reads",
            "What training means, precisely",
            "What pinning means",
            "Warrants, and the vocabulary assembled",
        ],
    },
    {
        "kind": "split",
        "kicker": "The definition",
        "title": "A model is a compute kernel, and a set of dials",
        "intro": "Strip away the implementation and every model has the same shape: something goes in, "
        "something comes out, and a set of numbers held apart from the machinery decides how it "
        "behaves. Those numbers are the parameters, and separating them from the machine is "
        "where everything else in this deck comes from.",
        "left": {
            "head": "The shape",
            "items": [
                (
                    "Inputs",
                    "The things that vary from one row to the next: this borrower's arrears, "
                    "this option's strike. One value per row, per input.",
                ),
                (
                    "The kernel",
                    "The fixed arithmetic that turns those inputs into an output. It does not "
                    "change between rows and it does not change between runs.",
                ),
                (
                    "The dials",
                    "Numbers that are the same for every row of a run, and that decide what the "
                    "kernel does with the inputs. A coefficient, a threshold, a volatility.",
                ),
            ],
        },
        "right": {
            "head": "Why hold the dials apart",
            "items": [
                (
                    "Because they change on a different clock",
                    "The arithmetic changes when somebody redesigns the model. The dials change "
                    "every time it is refitted. Recording both as one thing loses the "
                    "distinction a supervisor is asking about.",
                ),
                (
                    "Because they are what evidence is about",
                    "Almost every question a reviewer asks — what sample, what estimator, what "
                    "window, whose sign-off — is a question about how the dials were set, not "
                    "about the arithmetic.",
                ),
                (
                    "Because the output may be a distribution",
                    "Nothing here requires the kernel to return one number. It may return a "
                    "spread of them, so a model that samples is an instance of the definition "
                    "rather than an exception to it.",
                ),
            ],
        },
        "note": "Paper §2.2, the definition of a model as a kernel with a parameter object. The "
        "separation is not a modelling convenience: the derived facts of Part 6 and the "
        "warrants of Part 3 both follow from it.",
    },
    {
        "kind": "bullets",
        "kicker": "Parameters",
        "title": "A dial is not an input, and the difference is a declaration",
        "items": [
            (
                "An input varies per row; a parameter does not",
                "Feed a thousand borrowers through a scorecard and each has their own arrears figure. "
                "All thousand are scored with the same forty-two coefficients. That is the whole of "
                "the distinction, and it is a statement about the run rather than about the symbol.",
            ),
            (
                "So the same symbol can be either, and it matters which",
                "Volatility is an input to a Black–Scholes pricer: it arrives per option. In a "
                "calibrated volatility surface it is the thing being solved for, so it is a dial. "
                "Same letter, same arithmetic, different object — and the evidence each owes is "
                "different.",
            ),
            (
                "Which is why the role is declared rather than inferred",
                "Whoever writes the mathematics says, symbol by symbol, whether it is an input, a "
                "dial or a constant. A system that guessed would guess wrong on exactly the cases "
                "where it matters, and would do so silently.",
            ),
            (
                "And a dial usually carries a range it is allowed to sit in",
                "A probability between zero and one; a conversion factor at or above zero; a "
                "correlation inside minus one and one. A number outside its range is not a poor fit, "
                "it is an arithmetic error that has not yet surfaced.",
            ),
        ],
        "note": "maya/formula/ir.py: every input of a registered model carries a role — feature, "
        "parameter or constant — and a parameter carries its bounds. The bounds are checked when "
        "numbers are uploaded, not when they first produce a strange answer.",
    },
    {
        "kind": "table",
        "kicker": "Where the numbers come from",
        "title": "Six ways a dial gets set, and training is one of them",
        "intro": "These are not six kinds of model. They are six routes into the same set of dials, and "
        "which route was taken decides what evidence can exist — before anybody gets as far as "
        "asking for it.",
        "rows": [
            ["The act", "What it does", "A banking example", "What it owes a reviewer"],
            [
                "Theory",
                "Nothing: the formula prescribes the behaviour and leaves no dials",
                "A regulatory exposure calculator",
                "That the code computes what the text says",
            ],
            [
                "Calibration",
                "Solves the dials so the model reproduces prices the market is quoting now",
                "A volatility surface, four numbers re-solved each morning",
                "The instruments, and the residuals left over",
            ],
            [
                "Estimation",
                "Fits the dials to a sample by a named statistical procedure",
                "A PD scorecard, forty-two coefficients over eight years",
                "The sample, the estimator, performance out of time",
            ],
            [
                "Training",
                "The same act where the dials are too many to be individually meaningful",
                "A card-fraud network with thousands of weights",
                "The frozen input, the target, and the record of the run",
            ],
            [
                "Elicitation",
                "A panel agrees the numbers, because there is no data to fit them to",
                "An impairment committee's lifetime multiple",
                "Who agreed, when, and on what reasoning",
            ],
            [
                "Authorship",
                "Somebody writes the numbers down as policy",
                "A sanctions screening rule set",
                "The policy decision that caused the change",
            ],
        ],
        "col_w": [1.5, 3.5, 3.2, 3.4],
        "note": "Paper §2.3. Two further routes exist and are taken up in Part 6: configuration, where "
        "the dials are a base model, a prompt and a corpus; and somebody else's fitting, where "
        "the dials exist behind a contract and cannot be reached at all.",
    },
    {
        "kind": "split",
        "kicker": "Features",
        "title": "An input is not a column in somebody's table",
        "intro": "A model reads inputs. Where those inputs come from is usually treated as plumbing, and "
        "that is where reproducibility is lost. A feature is what an input is when it has been "
        "given an identity.",
        "left": {
            "head": "The failure it prevents",
            "items": [
                (
                    "Two desks, one name, two numbers",
                    "Both compute “adjusted close”. One adjusts for dividends and splits, the "
                    "other for splits alone. Neither is wrong; they are answering different "
                    "questions under one name, and the name is what travels.",
                ),
                (
                    "Nobody notices, because both are plausible",
                    "The two numbers differ by a few per cent. Every downstream check passes. "
                    "The disagreement surfaces years later, in a reconciliation nobody budgeted "
                    "for.",
                ),
                (
                    "A column cannot fix this",
                    "A column is a place values sit. It has no owner, no definition and no "
                    "history, so there is nothing for the two desks to disagree about "
                    "explicitly.",
                ),
            ],
        },
        "right": {
            "head": "What a feature adds",
            "items": [
                (
                    "A name, a namespace and an owner",
                    "So there is exactly one adjusted close in a namespace, and somebody "
                    "answerable for what it means.",
                ),
                (
                    "A typed schema and an index",
                    "The attributes with their types and units, and the columns that identify a "
                    "row — a date, and usually an entity. The index is fixed for the life of "
                    "the feature.",
                ),
                (
                    "A statement of where rows come from",
                    "A file, a read-only query, a reviewed producer, or an expression over "
                    "other features. Not “somebody loads it”.",
                ),
                (
                    "And a rule for the gaps",
                    "What to do when a date has no value: leave it null, carry the last one "
                    "forward for at most n days, or interpolate. Declared once, not decided "
                    "afresh in each query.",
                ),
            ],
        },
        "note": "Specification §5. A feature is the unit MAYA governs; the four things on the right are "
        "what make the two-desk disagreement a conversation that has to happen before the second "
        "definition exists rather than after both have been used.",
    },
    {
        "kind": "split",
        "kicker": "The two clocks",
        "title": "When it was true, and when you found out",
        "intro": "Every fact a model reads carries two independent times. Treating them as one is the "
        "dominant silent failure in this domain, because it improves every metric it corrupts — "
        "so nothing in the numbers ever asks to be investigated.",
        "left": {
            "head": "The two times",
            "items": [
                (
                    "Event time",
                    "The moment the fact held in the world. The quarter a set of accounts is "
                    "about; the day a balance stood at that level.",
                ),
                (
                    "Ingest time",
                    "The moment the recording system could first have known it. The day the "
                    "accounts landed in the warehouse; the night the file was loaded.",
                ),
                (
                    "They are not the same, and the gap is not small",
                    "Filed accounts reach a bank weeks after the quarter they describe. A "
                    "default is confirmed months after the missed payment that caused it.",
                ),
            ],
        },
        "right": {
            "head": "What follows",
            "items": [
                (
                    "A correction is a new record, not an edit",
                    "Same event time, later ingest time, nothing overwritten. Both rows are "
                    "true: one is what was known then, the other what is known now.",
                ),
                (
                    "So “what did we know on 31 March” is a filter",
                    "Rather than an archaeology project. Keep every row whose ingest time is at "
                    "or before the cut, then take the latest per key.",
                ),
                (
                    "And a store that overwrites cannot answer it at all",
                    "Not slowly — at all. Once the correction has replaced the earlier row, "
                    "what the decision saw is gone, and no query written afterwards can recover "
                    "it.",
                ),
            ],
        },
        "note": "Specification §5.1 and paper §5.1. maya/resolution/resolver.py holds the cut; "
        "tests/test_properties.py::test_a_restatement_never_overwrites holds the append. The "
        "next slide is why this is worth two columns of a schema.",
    },
    {
        "kind": "split",
        "kicker": "Feature sets",
        "title": "A named bundle of features, aligned on one index",
        "intro": "A model is not defined over a feature. It is defined over several of them, lined up so "
        "that each row carries a value for every input. That object has a name of its own "
        "because it is versioned, approved and pinned as a unit.",
        "left": {
            "head": "What it holds",
            "items": [
                (
                    "Attributes mapped from members",
                    "Each attribute of the set names the feature it comes from, the attribute "
                    "inside that feature, and any cast or override it needs.",
                ),
                (
                    "One index for all of them",
                    "The members may be daily, monthly and event-driven. The set declares the "
                    "grid every row sits on, and how each member is brought onto it.",
                ),
                (
                    "An alignment rule, stated",
                    "Inner keeps only rows every member has; outer keeps them all; left follows "
                    "one member; as-of takes the most recent value within a stated tolerance.",
                ),
            ],
        },
        "right": {
            "head": "Why it is a separate object",
            "items": [
                (
                    "Because the join is where judgement hides",
                    "Whether a monthly figure is carried forward into daily rows, and for how "
                    "long, changes the numbers materially. Written in a query, it is invisible; "
                    "written in the set, it is reviewable.",
                ),
                (
                    "Because a model reads a set, not a feature",
                    "So the question “does this data fit this model” is asked once, against one "
                    "object, rather than once per input by whoever wrote the script.",
                ),
                (
                    "Because it stores nothing until it is asked to",
                    "A feature set is a view. It holds the recipe, and produces rows when "
                    "somebody resolves it — which keeps the definition and the data separate "
                    "all the way up.",
                ),
            ],
        },
        "note": "Specification §6; maya/resolution/featureset.py. A member index carrying columns the "
        "set does not have is refused unless an aggregation is declared for them, because "
        "silently collapsing rows is a modelling decision and not a plumbing one.",
    },
    {
        "kind": "flow",
        "kicker": "Training",
        "title": "Choosing the dials from data — and the three things that takes",
        "steps": [
            (
                "A frozen input",
                "An exact, unchanging set of rows: these borrowers, these dates, these values",
            ),
            (
                "A target",
                "The thing the dials are chosen to reproduce — the outcome, named and dated",
            ),
            ("A procedure", "The estimator or optimiser, with its settings and its seed"),
            ("A record", "Which dials came out, from which rows, by which act, and who ran it"),
        ],
        "box_h": 1.9,
        "items": [
            "Training is this and nothing more: searching the space of dial settings for the one "
            "that best reproduces the target on the frozen input. The word carries connotations of "
            "scale and of neural networks; neither is part of the definition.",
            "Calibration and estimation are the same construction with different search procedures "
            "and different targets. Elicitation and authorship skip the search, which is precisely "
            "why they owe a minute rather than a sample.",
            "Every one of the four boxes above is an object that has to exist somewhere. Where one "
            "of them does not, the fit cannot be challenged — and the next slide is what each "
            "absence actually costs.",
        ],
        "note": "Paper §2.2, the fitting morphism. In MAYA the four boxes are, in order: a pinned "
        "feature set, the declared target attribute, the training run on the firm's own compute, "
        "and the parameter set with its provenance.",
    },
    {
        "kind": "split",
        "kicker": "Pinning",
        "title": "A version freezes how; a pin freezes what",
        "intro": "The third layer, promised earlier. A pin is a materialisation of one version of one "
        "feature, computed once and then immutable — the exact rows, with the exact values, as "
        "they stood when it was taken.",
        "left": {
            "head": "The failure it prevents",
            "items": [
                (
                    "A stable name over moving contents",
                    "“The March training set” names a file on a share drive. The file is "
                    "regenerated in April from a corrected feed, under the same name. Nothing "
                    "records that it changed, and every document that cites it now cites "
                    "something else.",
                ),
                (
                    "Which is not carelessness",
                    "It is the default behaviour of every path, table and view anybody has. "
                    "Reproducibility is not something a careful team achieves by being careful; "
                    "it is a property a store either has or lacks.",
                ),
                (
                    "And it fails silently, in the useful direction",
                    "The regenerated file is better data. The re-run gives better numbers. "
                    "Nobody investigates an improvement.",
                ),
            ],
        },
        "right": {
            "head": "What a pin is",
            "items": [
                (
                    "Values, resolved and sealed",
                    "One version, read as of a stated date under the declared fill rules, "
                    "written down, and never recomputed.",
                ),
                (
                    "Immutable, by construction rather than by policy",
                    "There is no operation that edits a pin. A correction produces a new pin, "
                    "and the old one keeps returning the bytes it always returned.",
                ),
                (
                    "Carrying what it took to make it",
                    "The version, the as-of date, the fill report — how many rows each rule "
                    "filled and the longest run it filled — and the backends that produced "
                    "it.",
                ),
            ],
        },
        "note": "Specification §4 and §7.2; maya/services/feature_data.py. Only a pinned object claims "
        "to be reproducible: a version resolved twice may legitimately differ, and MAYA does not "
        "pretend otherwise.",
    },
    {
        "kind": "bullets",
        "kicker": "Content addressing",
        "title": "A pin is named by the hash of what is in it",
        "items": [
            (
                "The name is computed, not chosen",
                "A pin's identity is a hash over its own contents. Two pins of the same values have "
                "the same hash; change one value anywhere and the hash changes. There is no way to "
                "have a name that agrees while the contents differ.",
            ),
            (
                "Over values, not over file bytes",
                "The hash is taken over a canonical form of the data, so column order does not affect "
                "it, and two pins taken on different machines with different library versions agree "
                "if and only if the numbers agree.",
            ),
            (
                "Which makes verification a computation rather than a trust exercise",
                "Hand a pin to somebody outside the firm and they can recompute the hash themselves. "
                "They are not taking the platform's word for anything: the name either follows from "
                "the contents or it does not.",
            ),
            (
                "And re-pinning unchanged data costs nothing and changes nothing",
                "The same rows produce the same hash and the same stored fragments, so a month-end "
                "pin of a slow-moving feature shares almost everything with last month's. The storage "
                "cost of freezing history is the part that actually changed.",
            ),
        ],
        "note": "maya/core/canonical.py is the definition of the hash and maya/core/chunker.py the "
        "fragment boundaries; "
        "tests/test_features.py::test_sc1_repin_is_byte_identical_and_changed_data_is_not, and "
        "::test_sc12_unchanged_month_costs_under_five_percent for the sharing.",
    },
    {
        "kind": "split",
        "kicker": "Warrants",
        "title": "A licence to compute, rather than a document about one",
        "intro": "The last word in the vocabulary. A warrant binds a model, a set of data and a set of "
        "dials into one object that can be granted, checked, transferred and withdrawn — which "
        "an approval memo cannot.",
        "left": {
            "head": "A training warrant",
            "items": [
                (
                    "Names what may be fitted, on what",
                    "This approved model version, against this pinned feature set, by these "
                    "people, until this date.",
                ),
                (
                    "Drawn only when the contract is satisfied",
                    "The set's schema must provide what the model declares it reads. Where it "
                    "does not, the warrant is refused with every missing attribute named.",
                ),
                (
                    "And it certifies the data before the work starts",
                    "A signed statement that no row in the frame was known later than the "
                    "decision it describes — so look-ahead is ruled out at the point it could "
                    "still be corrected.",
                ),
            ],
        },
        "right": {
            "head": "An execution warrant",
            "items": [
                (
                    "Names what may be run, with what",
                    "This model version, these approved dials, in this environment. It is what "
                    "a downstream system or a regulator is handed.",
                ),
                (
                    "It is alive",
                    "It expires on a date. It can be revoked. And it carries covenants — bounds "
                    "on its own inputs and outputs whose breach suspends it automatically.",
                ),
                (
                    "So a wrong model stops running",
                    "Rather than continuing until somebody remembers to send an email. Every "
                    "consuming call fails closed, naming the covenant that broke.",
                ),
            ],
        },
        "note": "Specification §29.4 and §29.5; maya/services/warrants.py and execution.py. The middle "
        "step between the two — fitting on the firm's own compute and uploading the dials "
        "against a checksum — is in Part 3.",
    },
    {
        "kind": "flow",
        "kicker": "The vocabulary assembled",
        "title": "Seven words, and each one now means something",
        "steps": [
            ("Source", "Where rows come from, declared"),
            ("Feature", "An input with an identity and two clocks"),
            ("Pin", "Those rows, frozen and named by their hash"),
            ("Model", "A kernel, and the dials it reads"),
            ("Parameters", "The dials, with how they were set"),
            ("Warrant", "A licence binding all of it"),
        ],
        "box_h": 1.75,
        "items": [
            "Nothing in the rest of this deck introduces a concept that is not on this line. Part "
            "3 carries it end to end, Part 4 governs it, and Part 6 shows that four facts a "
            "register normally asks somebody to type are consequences of this structure.",
            "The line runs in one direction and every arrow is checked. A model may not be bound "
            "to data whose schema does not satisfy it; a warrant may not be drawn against unpinned "
            "data; an execution warrant may not be sealed on dials that were never approved.",
            "It is also the answer to the three questions this part opened with. Which data: the "
            "pin. Which mathematics: the model version. Whose approval: the warrant.",
        ],
        "note": "README, “The shape of the thing”. The same spine runs through the web interface, the "
        "REST API, the Python SDK and the command line, and the interface is itself a client of "
        "the SDK with no private path of its own.",
    },
]
