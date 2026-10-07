"""
The deck, as data. The opening, and Part 1: the vocabulary.

The opening is told the way a briefing is: the summary first, as questions a reader
asks; the question every model must answer; ten principles; what supervisors say;
the objects MAYA keeps; how it is built; one model's journey through it; and what that
buys. The deck is split across modules only to keep each file under the repository's
file-size gate; read them in order (see GUIDE.md).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

OPENING: list[dict[str, Any]] = [
    {
        "kind": "cover",
        "title": ["Model & AI Lifecycle", "Assurance"],
        "sub": "Evidence, not assertion.",
        "date": "October 2026",
        "chain": [
            ("Feature", "two clocks"),
            ("Pin", "sealed by hash"),
            ("Model", "a typed formula"),
            ("Training warrant", "fit, escrowed"),
            ("Execution warrant", "a live licence"),
        ],
    },
    {
        "kind": "tldr",
        "title": "TL;DR — Executive summary",
        "rows": [
            (
                "What is the problem?",
                "Months after a model's number was used, nobody can say which data it saw, which "
                "mathematics ran, or whose approval it ran under. A model register lists things "
                "people typed; none of the three answers was ever stored.",
            ),
            (
                "What is MAYA?",
                "A system of record for models and the data they read. It keeps features with two "
                "clocks, freezes training data by content hash, holds the mathematics as a typed "
                "formula, and licenses fitting and running through warrants.",
            ),
            (
                "Why does it matter?",
                "The facts a supervisor asks for are derived from the work rather than declared "
                "about it — so they cannot be typed wrong, cannot drift, and verify on a machine "
                "with no MAYA installed.",
            ),
            (
                "What can it do today?",
                "The whole lifecycle in version 1.0.0: features to execution warrants, findings, "
                "tiers, periodic review that suspends, monitoring, champion and challenger, "
                "black boxes and LLM applications, 268 API endpoints, 15 case studies run end to "
                "end.",
            ),
            (
                "Where is it going?",
                "Live certification of the MLflow and SageMaker connectors, an external security "
                "review, a timed first-model study with real users, and OS isolation on Windows.",
            ),
        ],
    },
    {
        "kind": "numbered",
        "title": "Months later: which data, which mathematics, whose approval?",
        "question": "A committee asks about one number in last March's impairment charge.",
        "items": [
            (
                "Which data did it see?",
                "Not which table — which rows, with which values, as they stood that day. A vendor "
                "restated two quarters in August and the row was updated in place.",
            ),
            (
                "Which mathematics ran?",
                "A PDF describes the model, a repository implements it, the desk runs a "
                "spreadsheet. Each was right once; no test compares them.",
            ),
            (
                "Whose approval was it under?",
                "The memo has a date. It names no code version, no parameters, no data — so it "
                "approves something that can no longer be identified.",
            ),
        ],
        "head_w": 0.25,
        "size": 17,
        "insight": "None of these is a documentation problem. Each is a question about an object "
        "that was never stored — and everything in MAYA exists to make all three a lookup.",
    },
    {
        "kind": "numbered",
        "title": "10 principles: why every model needs evidence, not assertion",
        "items": [
            (
                "Derive, don't declare",
                "A fact a person types rots silently. A fact computed from the work cannot "
                "disagree with it.",
            ),
            (
                "Keep two clocks",
                "When a value was true and when it was known. A correction is a new row, never an "
                "overwrite.",
            ),
            (
                "Freeze what you train on",
                "A pin is named by the hash of its rows; the same name always means the same "
                "bytes.",
            ),
            (
                "License before you compute",
                "No fit without a training warrant; no run without a live execution warrant.",
            ),
            (
                "Score blind",
                "The holdout is escrowed when the warrant is drawn; the developer never sees it, "
                "and every attempt is counted.",
            ),
            (
                "Nobody approves their own work",
                "Separation of duties on every governed object, a finding included.",
            ),
            (
                "Policy is data",
                "Workflow states, checks and approvals are records, and changing them is itself "
                "governed.",
            ),
            (
                "Evidence leaves the building",
                "A signed bundle verifies and re-executes with Python, pyarrow and numpy — no "
                "MAYA, no network.",
            ),
            (
                "One contract, every surface",
                "The web UI is an SDK client; every endpoint has an SDK method, held by a gate.",
            ),
            (
                "State the limits",
                "What MAYA cannot check is said in the report's first words, not discovered later.",
            ),
        ],
        "head_w": 0.25,
        "size": 14,
    },
    {
        "kind": "quotes",
        "title": "What supervisors say",
        "items": [
            (
                "The use of models invariably presents model risk, which is the potential for "
                "adverse consequences from decisions based on incorrect or misused model outputs "
                "and reports.",
                "Federal Reserve and OCC, SR 11-7 (2011)",
            ),
            (
                "Model risk should be managed like other types of risk.",
                "Federal Reserve and OCC, SR 11-7 (2011)",
            ),
            (
                "Critical analysis by objective, informed parties who can identify model "
                "limitations and assumptions and produce appropriate changes.",
                "SR 11-7's definition of effective challenge",
            ),
        ],
        "insight": "The PRA's SS1/23, in force since May 2024, sets five principles to the same end: "
        "model identification and risk classification, governance, development and use, "
        "independent validation, and risk mitigants.",
    },
    {
        "kind": "table",
        "title": "The objects MAYA keeps",
        "rows": [
            ["Object", "What it is", "What it guarantees"],
            [
                "Feature",
                "A governed series: a name, an owner, a schema, a source, a rule for gaps",
                "Two clocks on every value; a correction never overwrites",
            ],
            [
                "Feature set",
                "Features aligned on one index, mapped to a model's inputs",
                "One place where the join — the judgement — is reviewable",
            ],
            [
                "Pin",
                "A feature or feature set resolved as of a date and sealed",
                "Named by the hash of its rows: the same name, the same bytes, forever",
            ],
            [
                "Model version",
                "The mathematics as a typed formula, its specification and code",
                "Code checked against the formula; diffs by meaning, not text",
            ],
            [
                "Parameter set",
                "The fitted or agreed values a model's parameters take",
                "Tied by checksum to the training data MAYA issued",
            ],
            [
                "Training warrant",
                "A licence to fit one model version on one pinned feature set",
                "Holdout escrowed; leakage certified; every score counted",
            ],
            [
                "Execution warrant",
                "A licence to run approved parameters, where, until when",
                "Expires, can be revoked, suspends itself on a covenant breach",
            ],
        ],
        "col_w": [2.0, 4.9, 4.7],
        "size": 13,
    },
    {
        "kind": "arch",
        "title": "MAYA architecture — surfaces, platform, stores",
        "bands": [
            ("Surfaces", "Web UI  |  REST API, 268 endpoints  |  Python SDK  |  Command line"),
            (
                "Governance",
                "Workflow  |  Findings  |  Tiers  |  Periodic review  |  Monitoring  |  Inventory",
            ),
            (
                "Core",
                "Features & pins  |  Formula IR  |  Warrants  |  Lineage  |  Hash-chained audit",
            ),
            (
                "Boundary",
                "Sandbox for uploaded code  |  Resolution engine  |  Signed evidence bundles",
            ),
            ("Stores", "SQLite or PostgreSQL, never both  |  maya_delta lake  |  Blob store"),
        ],
        "items": [
            "The web UI is a client of the SDK with no private path; a gate fails the build if the "
            "web tier imports past it.",
            "MAYA never trains a model and never serves a prediction: it is where the evidence "
            "lives, not where the arithmetic runs.",
            "FastAPI on Python 3.13, one process by default; several web processes and job workers "
            "on PostgreSQL.",
        ],
    },
    {
        "kind": "numbered",
        "title": "How a model travels through MAYA",
        "items": [
            (
                "Define the features",
                "Sources, schemas, gap rules; values loaded with the time "
                "they became known; approved by somebody else.",
            ),
            ("Pin the data", "A feature set frozen as of a date, sealed by the hash of its rows."),
            (
                "Register the mathematics",
                "LaTeX, Python or a spreadsheet becomes a typed formula, "
                "with a specification and generated code.",
            ),
            (
                "Fit under a training warrant",
                "Train and validation rows downloaded by checksum; "
                "the holdout escrowed; leakage certified.",
            ),
            (
                "Score blind, then approve",
                "MAYA scores the uploaded parameters on rows the "
                "developer never saw; a manager approves.",
            ),
            (
                "License it to run",
                "An execution warrant with environments, an expiry and "
                "covenants that suspend it on a breach.",
            ),
        ],
        "head_w": 0.27,
        "insight": "Every arrow is a refusal waiting to happen: an unapproved feature cannot be "
        "pinned, unpinned data cannot be warranted, and parameters fitted on data MAYA did not "
        "issue cannot be approved.",
    },
    {
        "kind": "table",
        "title": "What that buys",
        "rows": [
            ["Benefit", "What it means in practice"],
            [
                "Answers instead of archaeology",
                "Which data, which maths, whose approval: three lookups",
            ],
            [
                "Restatements that cannot rewrite history",
                "What was known on 31 March stays answerable",
            ],
            [
                "Code that is the mathematics",
                "Generated reference code; uploaded code compared to it",
            ],
            [
                "Validation the developer cannot game",
                "Escrowed holdout, counted attempts, blind scores",
            ],
            [
                "Controls that act",
                "An overdue review or a breached covenant stops the model running",
            ],
            [
                "Evidence a supervisor can verify",
                "A signed bundle re-executes offline, byte for byte",
            ],
            ["One inventory, never re-typed", "SR 11-7 and SS1/23 layouts read from the records"],
            [
                "Every kind of model",
                "Formulas, black boxes, imports and LLM applications, one chain",
            ],
        ],
        "col_w": [4.4, 7.2],
        "size": 14,
    },
]

VOCABULARY: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "1",
        "title": "The vocabulary",
        "sub": "Seven words, each defined before it is used, each earning its place by naming the "
        "failure it prevents.",
        "points": [
            "Kernel and dials",
            "Features, parameters, constants",
            "Two clocks",
            "Pins",
            "Warrants",
        ],
    },
    {
        "kind": "cards",
        "title": "A model is a compute kernel, and a set of dials",
        "cols": 3,
        "cards": [
            (
                "INPUTS",
                "What varies row by row",
                "This borrower's arrears, this option's strike: one value per row, per input.",
            ),
            (
                "THE KERNEL",
                "The fixed arithmetic",
                "Turns inputs into an output. It does not change "
                "between rows, and it does not change between runs.",
            ),
            (
                "THE DIALS",
                "Numbers held apart",
                "The same for every row of a run: a coefficient, a "
                "threshold, a fee. They change every time the model is refitted.",
            ),
        ],
        "note": "Holding the dials apart is where everything else comes from: almost every "
        "question a reviewer asks — what sample, what estimator, whose sign-off — is about how "
        "the dials were set.",
    },
    {
        "kind": "table",
        "title": "Features, parameters and constants",
        "intro": "Every input of a model has a role, and the role says where its value comes from.",
        "rows": [
            ["Role", "What it is", "Where its value comes from", "PD scorecard example"],
            [
                "Feature",
                "A fact about each case — one value per row",
                "Data: a warrant maps it to a feature set column",
                "bureau, delinquencies, dti, utilisation",
            ],
            [
                "Parameter",
                "A setting of the model itself — one value for every row",
                "Fitted on training data, or agreed, and approved as a parameter set",
                "intercept and four weights",
            ],
            [
                "Constant",
                "A number written into the definition",
                "Changes only with a new model version",
                "the 680 and 60 that scale the bureau score",
            ],
        ],
        "col_w": [1.6, 3.4, 3.8, 2.8],
        "size": 13.5,
        "note": "They fail differently, so they are controlled differently: a wrong feature is bad "
        "data, caught by quality checks and pins; a wrong parameter is a bad model, caught by "
        "blind scoring and approval.",
    },
    {
        "kind": "split",
        "title": "Two clocks: when it was true, and when you found out",
        "left": {
            "head": "The two times",
            "items": [
                ("Event time", "When the fact held: the quarter a set of accounts describes."),
                (
                    "Knowledge time",
                    "When MAYA could first have known it: the night the file landed.",
                ),
                (
                    "Never the same",
                    "Accounts arrive weeks after their quarter; a default is "
                    "confirmed months after the missed payment.",
                ),
            ],
        },
        "right": {
            "head": "What follows",
            "items": [
                (
                    "A correction is a new row",
                    "Same event time, later knowledge time; nothing is overwritten.",
                ),
                (
                    "“What did we know on 31 March?”",
                    "Becomes a filter, not an archaeology project.",
                ),
                (
                    "Look-ahead is caught",
                    "The silent failure that improves every metric it corrupts.",
                ),
            ],
        },
    },
    {
        "kind": "cards",
        "title": "A version freezes how; a pin freezes what",
        "cols": 3,
        "cards": [
            (
                "VALUES, SEALED",
                "Resolved once",
                "One version, read as of a date under its gap rules, "
                "written down and never recomputed.",
            ),
            (
                "IMMUTABLE",
                "By construction",
                "No operation edits a pin. A correction makes a new "
                "pin; the old one returns the same bytes for ever.",
            ),
            (
                "NAMED BY ITS HASH",
                "Verifiable by anyone",
                "The name is a hash of canonical values, "
                "so a reviewer outside the firm recomputes it rather than trusting it.",
            ),
        ],
        "note": "Re-pinning unchanged data costs nothing: identical rows give identical fragments, "
        "so a month-end pin shares almost everything with last month's.",
    },
    {
        "kind": "split",
        "title": "A warrant is a licence to compute, not a document about one",
        "left": {
            "head": "Training warrant",
            "items": [
                (
                    "What may be fitted, on what",
                    "This model version, this pinned feature set, until this date.",
                ),
                ("Drawn only if the data fits", "Every missing input is named in the refusal."),
                ("Certifies the data first", "No row known later than the decision it describes."),
            ],
        },
        "right": {
            "head": "Execution warrant",
            "items": [
                (
                    "What may run, with what",
                    "This version, these approved parameters, in these environments.",
                ),
                (
                    "It is alive",
                    "It expires, it can be revoked, and covenants suspend it on a breach.",
                ),
                (
                    "So a wrong model stops",
                    "Every consuming call fails closed and says whom to contact.",
                ),
            ],
        },
    },
    {
        "kind": "flow",
        "title": "Seven words, and each one now means something",
        "steps": [
            ("Source", "Where rows come from"),
            ("Feature", "An input with two clocks"),
            ("Pin", "Rows frozen by hash"),
            ("Model", "A kernel and its dials"),
            ("Parameters", "The dials, with provenance"),
            ("Warrant", "A licence binding it all"),
        ],
        "box_h": 1.7,
        "items": [
            "Which data? The pin. Which mathematics? The model version. Whose approval? The "
            "warrant. The three questions the deck opened with are now three lookups.",
            "Every arrow is checked: a model cannot be bound to data that does not satisfy it, and "
            "a warrant cannot be drawn against unpinned data.",
        ],
    },
]

SLIDES = OPENING + VOCABULARY
