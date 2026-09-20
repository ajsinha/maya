"""
The one MAYA deck: the formalism with an engineer's lens, then the system.

Four decks told one story four times, which is four places to keep it current.
This deck replaces them. It starts from nothing — what a model is, what a
parameter is, what a feature is, what training and pinning mean — and only then
describes what MAYA does with any of it, because the earlier decks assumed a
vocabulary their readers did not have.

Parts 1 and 2 are here: the vocabulary, and the four facts that follow from it
rather than being typed into a form. Parts 3 and 4 are in ``maya_deck_2``, parts
5 and 6 in ``maya_deck_3``.

Every figure comes from the code, ``maya/core/version.py``, the README's
"What's shipped", ``docs/BENCHMARKS.md`` or a study's recorded run, and every
slide's note names its source.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

from maya_deck_1b import SLIDES as DERIVED
from maya_deck_2 import SLIDES as SYSTEM
from maya_deck_3 import SLIDES as STUDIES

CHAPTER = "MAYA · Model Management"
TITLE = "MAYA — Model Management Formalism and System Design"
SUBJECT = "What a model is, what follows from that, and what MAYA does about it"

OPENING = [
    {
        "kind": "title",
        "kicker": "MODEL MANAGEMENT  ·  THE FORMALISM, AND THE SYSTEM BUILT FROM IT",
        "title": ["What a model is,", "and what follows from that"],
        "sub": "MAYA — Model & AI Lifecycle Assurance.  Evidence, not assertion.",
        "version": "MAYA 0.3.0 · specification revision 2.6",
        "agenda": [
            "What a model actually is",
            "Four facts you should not have to type",
            "The objects MAYA keeps",
            "How it runs",
            "Four models, end to end",
            "What is measured, and what MAYA does not do",
        ],
    },
]

VOCABULARY = [
    {
        "kind": "divider",
        "num": "1",
        "title": "What a model actually is",
        "sub": "Nothing in this deck is used before it is defined. This part builds the "
        "vocabulary from nothing — kernel, parameter, feature, clock, feature set, training, "
        "pin, warrant — one idea to a slide, each carried by an example from a bank and each "
        "earning its place by naming the failure it prevents.",
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
        "kind": "bullets",
        "kicker": "The question",
        "title": "Months later: which data, which mathematics, whose approval",
        "intro": "A committee asks about one number in last March's impairment charge. Three "
        "questions follow, and in most quantitative shops each is answered by archaeology "
        "rather than by a query. Everything in this deck exists to make all three a lookup.",
        "items": [
            (
                "Which data did it see?",
                "Not which table — which rows, with which values, as they stood on the day. "
                "The table has moved since: a vendor restated two quarters in August and the "
                "warehouse row was updated in place, so the number the model saw in March no "
                "longer exists anywhere.",
            ),
            (
                "Which mathematics did it run?",
                "There is a PDF that describes the model, a repository that implements it, and "
                "a spreadsheet the desk actually uses. All three were correct once. Nobody "
                "knows which of them is the model, and no test compares them.",
            ),
            (
                "Whose approval was it running under?",
                "There is an approval memo with a date. It does not name the version of the "
                "code, the numbers in the parameters, or the data the numbers were fitted on, "
                "so it approves a thing that cannot now be identified.",
            ),
            (
                "None of these is a documentation problem",
                "Each is a question about an object that was never stored. A better template "
                "does not help; the answer has to be a consequence of how the work is done.",
            ),
        ],
        "note": "Specification §1, the four reproducibility failures. Every part of this deck "
        "traces back to one of these three questions.",
    },
    {
        "kind": "split",
        "kicker": "The definition",
        "title": "A model is a compute kernel, and a set of dials",
        "intro": "Strip away the implementation and every model has the same shape: something "
        "goes in, something comes out, and a set of numbers held apart from the machinery "
        "decides how it behaves. Those numbers are the parameters, and separating them from "
        "the machine is where everything else in this deck comes from.",
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
        "separation is not a modelling convenience: the nine-class table in Part 2 and the "
        "warrant in Part 3 both follow from it.",
    },
    {
        "kind": "table",
        "kicker": "Same shape, different reality",
        "title": "A pricer with no dials, beside a scorecard with forty-two",
        "intro": "Two artefacts that a model register would list on the same screen. They have "
        "the same shape under the definition, and almost nothing in common operationally — and "
        "the whole of the difference lives in the dials.",
        "rows": [
            ["", "Black–Scholes option price", "Small-business PD scorecard"],
            [
                "Inputs",
                "Spot, strike, tenor, rate, volatility",
                "Arrears, utilisation, loan-to-value, turnover and thirty-eight more",
            ],
            [
                "The kernel",
                "One closed-form expression, prescribed by the theory",
                "A logistic function of a weighted sum",
            ],
            [
                "The dials",
                "None. There is nothing to set",
                "Forty-two coefficients",
            ],
            [
                "How they were set",
                "They were not. The formula is the whole of it",
                "A logistic regression over eight years of originations",
            ],
            [
                "What makes it change",
                "Somebody deciding a different formula is correct",
                "A refit, a drift alarm, or a decayed sample",
            ],
            [
                "What a reviewer should ask",
                "Does the code compute what the formula says?",
                "Was the sample representative, and does it still discriminate out of time?",
            ],
            [
                "What a reviewer should not ask",
                "For the training set, the estimator, or the retraining schedule",
                "Whether the coefficients are prescribed by anybody",
            ],
        ],
        "col_w": [2.2, 4.6, 4.8],
        "note": "Paper §2.2, the worked pair of a closed-form pricer and a fitted artefact. The "
        "last row is the point: a register that demands the same evidence of both is not "
        "recording a missing value, it is asking a question that has no meaning.",
    },
    {
        "kind": "bullets",
        "kicker": "Parameters",
        "title": "A dial is not an input, and the difference is a declaration",
        "items": [
            (
                "An input varies per row; a parameter does not",
                "Feed a thousand borrowers through a scorecard and each has their own arrears "
                "figure. All thousand are scored with the same forty-two coefficients. That is "
                "the whole of the distinction, and it is a statement about the run rather than "
                "about the symbol.",
            ),
            (
                "So the same symbol can be either, and it matters which",
                "Volatility is an input to a Black–Scholes pricer: it arrives per option. In a "
                "calibrated volatility surface it is the thing being solved for, so it is a "
                "dial. Same letter, same arithmetic, different object — and the evidence each "
                "owes is different.",
            ),
            (
                "Which is why the role is declared rather than inferred",
                "Whoever writes the mathematics says, symbol by symbol, whether it is an input, "
                "a dial or a constant. A system that guessed would guess wrong on exactly the "
                "cases where it matters, and would do so silently.",
            ),
            (
                "And a dial usually carries a range it is allowed to sit in",
                "A probability between zero and one; a conversion factor at or above zero; a "
                "correlation inside minus one and one. A number outside its range is not a poor "
                "fit, it is an arithmetic error that has not yet surfaced.",
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
        "intro": "These are not six kinds of model. They are six routes into the same set of "
        "dials, and which route was taken decides what evidence can exist — before anybody gets "
        "as far as asking for it.",
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
        "note": "Paper §2.3. Two further routes exist and are taken up in Part 2: configuration, "
        "where the dials are a base model, a prompt and a corpus; and somebody else's fitting, "
        "where the dials exist behind a contract and cannot be reached at all.",
    },
    {
        "kind": "bullets",
        "kicker": "The consequence",
        "title": "Training is a way of setting dials, not what makes something a model",
        "intro": "This is the first place the vocabulary earns its keep. Treating “trained” "
        "as the definition of a model, rather than as one route into the dials, produces two "
        "failures that are common enough to be unremarkable.",
        "items": [
            (
                "The ill-typed question, answered anyway",
                "A register demands a training set for a closed-form pricer. There is none, and "
                "there could not be one. The field is mandatory, so somebody types “n/a” "
                "or the date of the last release, and a meaningless value is now on the record "
                "in a field that reads as meaningful.",
            ),
            (
                "The argument that cannot be settled",
                "“Is the rule set a model?” Whichever way it is decided, the decision "
                "is about a boundary nobody can state. Under this definition the question "
                "dissolves: a rule set is a kernel whose dials were set by authorship, and it "
                "owes the evidence authorship owes.",
            ),
            (
                "And the artefact that is governed as though it were fitted",
                "A bought-in bureau score is demanded to produce development documentation it "
                "cannot produce, because the fitting happened at the bureau. The demand is not "
                "refused; it goes unanswered for two years while the model runs.",
            ),
            (
                "The repair is not a bigger form",
                "It is to stop asking the artefact what kind it is. Part 2 shows the kind being "
                "computed from how the dials were set, so it cannot be typed wrong and cannot "
                "drift from the thing it describes.",
            ),
        ],
        "note": "Paper §2.3, the corollary that a demand for fitting evidence is well-typed "
        "exactly when the dials exist and are reachable.",
    },
    {
        "kind": "split",
        "kicker": "Features",
        "title": "An input is not a column in somebody's table",
        "intro": "A model reads inputs. Where those inputs come from is usually treated as "
        "plumbing, and that is where reproducibility is lost. A feature is what an input is "
        "when it has been given an identity.",
        "left": {
            "head": "The failure it prevents",
            "items": [
                (
                    "Two desks, one name, two numbers",
                    "Both compute “adjusted close”. One adjusts for dividends and "
                    "splits, the other for splits alone. Neither is wrong; they are answering "
                    "different questions under one name, and the name is what travels.",
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
                    "row — a date, and usually an entity. The index is fixed for the life of the "
                    "feature.",
                ),
                (
                    "A statement of where rows come from",
                    "A file, a read-only query, a reviewed producer, or an expression over other "
                    "features. Not “somebody loads it”.",
                ),
                (
                    "And a rule for the gaps",
                    "What to do when a date has no value: leave it null, carry the last one "
                    "forward for at most n days, or interpolate. Declared once, not decided "
                    "afresh in each query.",
                ),
            ],
        },
        "note": "Specification §5. A feature is the unit MAYA governs; the four things on the "
        "right are what make the two-desk disagreement a conversation that has to happen before "
        "the second definition exists rather than after both have been used.",
    },
    {
        "kind": "table",
        "kicker": "Three layers",
        "title": "A definition, its versions, and — shortly — its data",
        "intro": "A feature is not one object. Separating how a number is produced from a frozen "
        "record of how it was produced is what lets a definition be corrected without rewriting "
        "history, and it is the pattern every governed object in MAYA follows.",
        "rows": [
            ["Layer", "What it is", "What changing it means", "Written as"],
            [
                "Definition",
                "The named description of how the values are produced: schema, source, fill "
                "rules, quality checks",
                "Editable while it is a draft; after that, a change mints a version",
                "maya://feature/dscr",
            ],
            [
                "Version",
                "An immutable snapshot of the definition, minted when its content changes, and "
                "classified breaking, behavioural or additive",
                "Nothing. A version is frozen, and the old one stays resolvable",
                "maya://feature/dscr@v3",
            ],
            [
                "The data",
                "The rows themselves, which arrive over time and are restated over time",
                "Covered four slides on, once the two clocks have been introduced",
                "—",
            ],
        ],
        "col_w": [1.5, 5.0, 3.4, 1.7],
        "note": "Specification §4. A version freezes how a number is produced. It does not "
        "freeze the number: resolve one version a hundred times as its source moves and it may "
        "return a hundred different answers, each of them correct.",
    },
    {
        "kind": "split",
        "kicker": "The two clocks",
        "title": "When it was true, and when you found out",
        "intro": "Every fact a model reads carries two independent times. Treating them as one "
        "is the dominant silent failure in this domain, because it improves every metric it "
        "corrupts — so nothing in the numbers ever asks to be investigated.",
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
                    "Not slowly — at all. Once the correction has replaced the earlier row, what "
                    "the decision saw is gone, and no query written afterwards can recover it.",
                ),
            ],
        },
        "note": "Specification §5.1 and paper §5.1. maya/resolution/resolver.py holds the cut; "
        "tests/test_properties.py::test_a_restatement_never_overwrites holds the append. The "
        "next slide is why this is worth two columns of a schema.",
    },
    {
        "kind": "bullets",
        "kicker": "Why one clock leaks",
        "title": "The filed accounts that were restated",
        "intro": "A borrower files Q1 accounts dated 31 March. They land in the warehouse on "
        "20 May. The bank declines an application on 15 June. In August the borrower restates "
        "those accounts downward, and the debt-service ratio falls from 1.20 to 0.40. Both rows "
        "are true, and both belong in the store.",
        "items": [
            (
                "Read with one clock, the training row gets 0.40",
                "Because 0.40 is the current value for Q1, and “Q1” is all the query "
                "asks for. The model now learns to predict defaults using a number that exists "
                "because the default already happened.",
            ),
            (
                "The model then assesses excellently and performs badly",
                "It has been shown the answers. Discrimination on the development sample is "
                "outstanding, discrimination in production is ordinary, and the post-mortem "
                "blames drift.",
            ),
            (
                "Read with two clocks, it gets 1.20",
                "Because on 15 June the restatement had not been made, so nothing in the world "
                "could have told the bank about it. That is the number the decision was actually "
                "taken on.",
            ),
            (
                "And a row labelled in September correctly gets 0.40",
                "The rule is not “ignore restatements”. It is a rule about the moment "
                "each one becomes knowable, and it gives a different answer for each decision "
                "date — which is exactly what makes it a rule rather than a convention.",
            ),
        ],
        "note": "Paper §5.2, the worked example of the restated accounts. Part 2 states the read "
        "as an operator and shows why the bound that matters is the earlier of the two dates, "
        "which is one character and the whole guarantee.",
    },
    {
        "kind": "split",
        "kicker": "Feature sets",
        "title": "A named bundle of features, aligned on one index",
        "intro": "A model is not defined over a feature. It is defined over several of them, "
        "lined up so that each row carries a value for every input. That object has a name of "
        "its own because it is versioned, approved and pinned as a unit.",
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
                    "So the question “does this data fit this model” is asked once, "
                    "against one object, rather than once per input by whoever wrote the script.",
                ),
                (
                    "Because it stores nothing until it is asked to",
                    "A feature set is a view. It holds the recipe, and produces rows when "
                    "somebody resolves it — which keeps the definition and the data separate all "
                    "the way up.",
                ),
            ],
        },
        "note": "Specification §6; maya/resolution/featureset.py. A member index carrying columns "
        "the set does not have is refused unless an aggregation is declared for them, because "
        "silently collapsing rows is a modelling decision and not a plumbing one.",
    },
    {
        "kind": "bullets",
        "kicker": "Schema and contents",
        "title": "What a model reads is a list of names and types, not a table",
        "intro": "A feature set has a schema — the attributes it provides, each with a type, a "
        "nullability and any bounds — and, separately, the rows that fill it. Keeping those two "
        "apart is what makes several later questions answerable at all.",
        "items": [
            (
                "A model declares the schema it needs",
                "Not the feature set it was built with. “I read dscr as a non-null float "
                "between 0 and 20, arrears as a non-negative integer, and ltv as a float.” "
                "That is the model's input contract.",
            ),
            (
                "Any set whose schema satisfies it will do",
                "Which is what lets a model be re-bound to next year's data, or to a different "
                "region's, without anybody re-reading the code to work out whether it is safe.",
            ),
            (
                "So “does this data fit this model” is a comparison of two schemas",
                "It is decidable, it does not require reading a single row, and it can be "
                "answered before the data exists. Part 2 shows it is the same comparison as "
                "three other questions a register normally implements separately.",
            ),
            (
                "And the answer, when it is no, can name the remedy",
                "A missing attribute means the wrong data was bound. An attribute that accepts "
                "less than the contract asked for means somebody tightened a constraint without "
                "noticing it was a promise. Different mistakes, different fixes.",
            ),
        ],
        "note": "maya/formula/ir.py holds the contract; maya/services/warrants.py checks it and "
        "lists every attribute that misses rather than the first "
        "(tests/test_warrants.py::test_contract_mismatch_is_refused_listing_every_attribute).",
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
            (
                "A procedure",
                "The estimator or optimiser, with its settings and its seed",
            ),
            (
                "A record",
                "Which dials came out, from which rows, by which act, and who ran it",
            ),
        ],
        "box_h": 1.9,
        "items": [
            "Training is this and nothing more: searching the space of dial settings for the one "
            "that best reproduces the target on the frozen input. The word carries connotations "
            "of scale and of neural networks; neither is part of the definition.",
            "Calibration and estimation are the same construction with different search "
            "procedures and different targets. Elicitation and authorship skip the search, which "
            "is precisely why they owe a minute rather than a sample.",
            "Every one of the four boxes above is an object that has to exist somewhere. Where "
            "one of them does not, the fit cannot be challenged — and the next slide is what each "
            "absence actually costs.",
        ],
        "note": "Paper §2.2, the fitting morphism. In MAYA the four boxes are, in order: a pinned "
        "feature set, the declared target attribute, the training run on the firm's own compute, "
        "and the parameter set with its provenance.",
    },
    {
        "kind": "cards",
        "kicker": "Why each is needed",
        "title": "Three absences, and what each one costs",
        "cols": 3,
        "cards": [
            (
                "WITHOUT A FROZEN INPUT",
                "The fit cannot be reproduced or challenged",
                "“The data” becomes whatever the query returned that afternoon. Re-run "
                "it a month later and the sample has grown, two vendors have restated and one "
                "join now matches differently. The refit does not reproduce the fit, and nobody "
                "can tell whether the difference is the data or the code. A challenger cannot "
                "challenge a number they cannot recreate.",
            ),
            (
                "WITHOUT A NAMED TARGET",
                "You cannot tell a predictor from the answer in disguise",
                "The target is what the dials are chosen to reproduce, so it is also the one "
                "thing no input may secretly contain. Unnamed, there is nothing to test inputs "
                "against, and a field derived from the outcome — a recovery amount, a workout "
                "flag, a restated ratio — enters the fit looking like a legitimate predictor and "
                "performing like one.",
            ),
            (
                "WITHOUT A RECORD",
                "A refit and a redesign look identical six months on",
                "Both arrive as “new numbers”. One is the same model on newer data and "
                "needs monitoring; the other is a different model and needs review. Absent a "
                "record of which act produced which dials, from which rows, over which window, a "
                "supervisor asking whether the model changed between two dates has asked a "
                "question with two defensible answers.",
            ),
        ],
        "note": "Specification §9 (parameter sets) and §29.1 (the leakage certificate). The "
        "second card is why the two clocks were introduced before this slide: a restated value "
        "is the commonest way the answer gets into the inputs.",
    },
    {
        "kind": "split",
        "kicker": "Pinning",
        "title": "A version freezes how; a pin freezes what",
        "intro": "The third layer, promised earlier. A pin is a materialisation of one version "
        "of one feature, computed once and then immutable — the exact rows, with the exact "
        "values, as they stood when it was taken.",
        "left": {
            "head": "The failure it prevents",
            "items": [
                (
                    "A stable name over moving contents",
                    "“The March training set” names a file on a share drive. The file "
                    "is regenerated in April from a corrected feed, under the same name. Nothing "
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
                    "filled and the longest run it filled — and the backends that produced it.",
                ),
            ],
        },
        "note": "Specification §4 and §7.2; maya/services/feature_data.py. Only a pinned object "
        "claims to be reproducible: a version resolved twice may legitimately differ, and MAYA "
        "does not pretend otherwise.",
    },
    {
        "kind": "bullets",
        "kicker": "Content addressing",
        "title": "A pin is named by the hash of what is in it",
        "items": [
            (
                "The name is computed, not chosen",
                "A pin's identity is a hash over its own contents. Two pins of the same values "
                "have the same hash; change one value anywhere and the hash changes. There is "
                "no way to have a name that agrees while the contents differ.",
            ),
            (
                "Over values, not over file bytes",
                "The hash is taken over a canonical form of the data, so column order does not "
                "affect it, and two pins taken on different machines with different library "
                "versions agree if and only if the numbers agree.",
            ),
            (
                "Which makes verification a computation rather than a trust exercise",
                "Hand a pin to somebody outside the firm and they can recompute the hash "
                "themselves. They are not taking the platform's word for anything: the name "
                "either follows from the contents or it does not.",
            ),
            (
                "And re-pinning unchanged data costs nothing and changes nothing",
                "The same rows produce the same hash and the same stored fragments, so a "
                "month-end pin of a slow-moving feature shares almost everything with last "
                "month's. The storage cost of freezing history is the part that actually changed.",
            ),
        ],
        "note": "maya/core/canonical.py is the definition of the hash and maya/core/chunker.py "
        "the fragment boundaries; tests/test_features.py::"
        "test_sc1_repin_is_byte_identical_and_changed_data_is_not, and ::"
        "test_sc12_unchanged_month_costs_under_five_percent for the sharing.",
    },
    {
        "kind": "bullets",
        "kicker": "Pinning a set",
        "title": "Every member pinned, or none of them",
        "intro": "A feature set is pinned by pinning its members. There is no partial state, and "
        "the reason is not tidiness.",
        "items": [
            (
                "A half-pinned set is not partly reproducible",
                "It is not reproducible. Whichever members were left live can move underneath "
                "it, so a re-read of the “same” set returns different numbers — and "
                "the pinned members make it look as though it could not.",
            ),
            (
                "So the set refuses to pin while any member is unpinned",
                "And a cascade pins them all under one shared name and as-of date, in one job. "
                "If any member fails its quality checks the whole cascade is rolled back, "
                "because a set that pinned four of five members is the state being avoided.",
            ),
            (
                "The set's own pin is content-addressed too",
                "Sealed by a hash over the resolved output, whether or not the rows were written "
                "down. Where they were not, the set is rebuilt from the member pins on read and "
                "the read fails if the hash does not come back — safe, and honest about it.",
            ),
            (
                "Which is what a training set actually is",
                "Not a file, and not a query. A pinned feature set: a named, immutable, "
                "hash-verified set of rows whose every member is also named, immutable and "
                "hash-verified.",
            ),
        ],
        "note": "maya/services/featuresets.py; tests/test_warrants.py::"
        "test_cascade_rolls_back_entirely_on_a_member_failure and tests/test_materialization.py, "
        "which checks that all three materialisation policies seal by the same hash.",
    },
    {
        "kind": "split",
        "kicker": "Warrants",
        "title": "A licence to compute, rather than a document about one",
        "intro": "The last word in the vocabulary. A warrant binds a model, a set of data and a "
        "set of dials into one object that can be granted, checked, transferred and withdrawn — "
        "which an approval memo cannot.",
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
                    "This model version, these approved dials, in this environment. It is what a "
                    "downstream system or a regulator is handed.",
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
        "note": "Specification §29.4 and §29.5; maya/services/warrants.py and execution.py. The "
        "middle step between the two — fitting on the firm's own compute and uploading the dials "
        "against a checksum — is Part 3.",
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
            "Nothing in the rest of this deck introduces a concept that is not on this line. "
            "Part 2 shows that four facts a governance system normally asks somebody to type in "
            "are consequences of this structure; Part 3 shows what MAYA stores for each word.",
            "The line runs in one direction and every arrow is checked. A model may not be bound "
            "to data whose schema does not satisfy it; a warrant may not be drawn against "
            "unpinned data; an execution warrant may not be sealed on dials that were never "
            "approved.",
            "It is also the answer to the three questions this part opened with. Which data: the "
            "pin. Which mathematics: the model version. Whose approval: the warrant.",
        ],
        "note": "README, “The shape of the thing”. The same spine runs through the web "
        "interface, the REST API, the Python SDK and the command line, and the interface is "
        "itself a client of the SDK with no private path of its own.",
    },
]

SLIDES = OPENING + VOCABULARY + DERIVED + SYSTEM + STUDIES
