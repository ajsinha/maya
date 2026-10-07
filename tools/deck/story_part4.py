"""
The deck, as data. Part 6, worked models; Part 7, the formal core; Part 8, built today
and what comes next; and the close.

Every figure on a case-study slide was reproduced by running the study against a MAYA
built from nothing.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

WORKED: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "6",
        "title": "Fifteen models, carried the whole way",
        "sub": "Each case study is a real modelling problem taken through MAYA end to end by "
        "named people with real roles, so the refusals are the platform's. The suite runs every "
        "one from nothing.",
        "points": [
            "The fifteen",
            "A scorecard",
            "A prescribed formula",
            "A bought score",
            "A challenger",
            "A fairness question",
            "An LLM application",
        ],
    },
    {
        "kind": "table",
        "title": "Fifteen studies, different in kind",
        "rows": [
            ["Study", "Model", "What it is really about"],
            ["01 Retail PD scorecard", "Fitted logistic", "Two clocks; a certificate that refuses"],
            ["02 Mortgage cash flow", "Closed form", "Whether the desk's code is the mathematics"],
            ["03 Prepayment", "Fitted hazard", "A change priced by shadow replay"],
            ["04 HELOC exposure", "Composite router", "Two members, two parameter sets, one seal"],
            ["05 Option pricing", "Calibrated", "A parameter nobody can observe"],
            ["06 IFRS 9 ECL", "Composite", "Committee judgements as parameter sets"],
            ["07 Card fraud", "Declared black box", "What is left to hold to account"],
            ["08 AR(2) and GARCH", "Formula and black box", "The last dates held out"],
            ["09 Basel IRB", "Prescribed formula", "Reconciliation, a finding, closure"],
            ["10 Factor models", "Two versions", "A semantic diff"],
            ["11 Nelson–Siegel", "Non-linear", "A bug a recalibration absorbs"],
            ["19 Vendor bureau score", "Bought, from MLflow", "Blind scoring; drift to breach"],
            ["42 Demand elasticity", "Linear vs log-log", "A paired interval"],
            ["45 Mortality table", "Non-linear law", "A bias the law requires"],
            ["49 Complaint triage", "LLM application", "Guardrails and evaluation sets"],
        ],
        "col_w": [3.2, 3.0, 5.4],
        "size": 12.5,
    },
    {
        "kind": "numbered",
        "title": "Study 01 — a scorecard from three CSVs to a licence to run",
        "question": "“Can we put this probability-of-default scorecard into production, and prove "
        "how we got there?”",
        "items": [
            ("Ingest — dana", "Three features, with knowledge times; approved by mick."),
            ("Assemble and pin — devi", "The panel, cascade-pinned as of 2025-06-30: 9,600 rows."),
            (
                "Register — mona",
                "The logistic formula, four features, five parameters; approved by mgr.",
            ),
            ("Fit — devi", "Under a training warrant, by IRLS in twelve lines of numpy."),
            ("Score blind — MAYA", "The uploaded parameters scored on rows devi never saw."),
            ("Seal — lara", "An execution warrant, approved by a second person."),
        ],
        "head_w": 0.24,
        "insight": "Nothing in the study touches the database: every action goes through the "
        "SDK as a user with the role for it, so every refusal on the way is the platform's.",
    },
    {
        "kind": "stats",
        "title": "Study 09 — a bracket left out, found by reconciling every obligor",
        "stats": [
            ("0.00982", "RMSE of K for version 1 against the regulator's reference"),
            ("6.5m", "capital overstated on the year-end book: 179.6m against 173.1m"),
            ("1", "statement in the semantic diff that fixes it"),
            ("5.7e-17", "RMSE of K for version 2, floor and cap restored"),
        ],
        "items": [
            "A model with nothing to fit is proved by reconciliation; the leakage certificate "
            "records a written exception, because reporting uses figures finalised after the "
            "quarter by design.",
            "A high finding was raised, fixed as version 2, refused when the owner tried to close "
            "it herself, and closed by the validator.",
        ],
    },
    {
        "kind": "table",
        "title": "Study 19 — a bought score, validated blind, taken out of service by drift",
        "intro": "Imported from its MLflow signature, its code validated in the sandbox, scored "
        "blind on 171 held-out applications: Brier 0.082, utilisation 43% of the importance. "
        "Then three months in production:",
        "rows": [
            ["Month", "Mean utilisation", "PSI", "Warrant", "Dashboard"],
            ["January", "0.411", "0.009", "live", "ok"],
            ["February", "0.451", "0.109", "live", "watch"],
            ["March", "0.497", "0.438", "suspended", "breach"],
        ],
        "size": 15,
        "note": "Nobody had to notice. The covenant broke, the warrant suspended itself, and every "
        "consuming call failed closed naming whom to contact.",
    },
    {
        "kind": "stats",
        "title": "Study 42 — winning 60% of rows, and still clearly better",
        "stats": [
            ("0.2250", "blind RMSE of the linear champion on 657 escrowed rows"),
            ("0.1940", "blind RMSE of the log-log challenger, same rows"),
            ("[−0.040, −0.022]", "95% paired bootstrap interval"),
            ("−1.62", "the challenger's elasticity; the truth is −1.6"),
        ],
        "items": [
            "The challenger wins by more where it wins: at the deepest discount 0.276 against "
            "0.235. Two headline RMSEs hide that; a paired comparison shows it.",
            "A warrant with another seed was refused rather than compared; the challenger's "
            "developer was refused the decision; a second manager promoted it.",
        ],
    },
    {
        "kind": "stats",
        "title": "Study 45 — wrong by the same amount, in opposite directions",
        "stats": [
            ("1.08", "MAE ratio between the sexes: by size, nothing stands out"),
            ("+0.0259", "bias for women: the unisex table overstates"),
            ("−0.0240", "bias for men: it understates"),
            ("6.6 years", "for mortality to double, from the fitted slope"),
        ],
        "items": [
            "Both segments are marked systematic. The first version of MAYA's fairness evidence "
            "flagged on MAE alone and reported nothing; this study is why the systematic flag "
            "exists.",
            "The table must be unisex by law, so the finding is accepted, not fixed — by a "
            "manager, with the ruling cited.",
        ],
    },
    {
        "kind": "table",
        "title": "Study 49 — right about every category, and still not fit to use",
        "intro": "A triage application on the firm's own Azure OpenAI deployment. MAYA does not "
        "call it: answers are recorded where it runs and scored here.",
        "rows": [
            ["Run", "Passed", "What happened"],
            [
                "Version 1",
                "21 of 24",
                "Every category right; one promises a refund, two repeat phone and card numbers",
            ],
            [
                "Draft fixed",
                "24 of 24",
                "New definition hash: the failing run no longer describes it",
            ],
            [
                "Set extended",
                "refused",
                "A validator adds a Welsh complaint; the clean run no longer counts",
            ],
            ["Scored again", "25 of 25", "The owner refused approval; a model manager approved"],
        ],
        "col_w": [2.0, 1.6, 8.0],
        "size": 14,
    },
]

FORMAL: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "7",
        "title": "The formal core",
        "sub": "Why the facts above can be derived rather than typed. Proofs are in the research "
        "paper; this is the engineer's view.",
        "points": [
            "Four facts that rot",
            "One order",
            "The point-in-time read",
            "Where a machine may do the work",
        ],
    },
    {
        "kind": "table",
        "title": "Four declared facts, and how each one rots",
        "rows": [
            ["", "The declaration", "How it rots", "The damage"],
            [
                "Kind",
                "What sort of artefact this is",
                "Typed once, at registration",
                "A monitor that detects nothing reads as coverage",
            ],
            [
                "Fit",
                "Whether this data or version fits",
                "Four code paths drift apart",
                "Towards permitting more: nobody files that bug",
            ],
            [
                "Currency",
                "What a row could have known",
                "A convention in each query",
                "Look-ahead that improves every metric",
            ],
            [
                "Support",
                "What a conclusion rests on",
                "A log, not a derivation",
                "“Still supported?” needs a person to read it",
            ],
        ],
        "col_w": [1.4, 3.4, 3.2, 3.6],
        "size": 14,
        "note": "Each of the four is derivable from structure that has to exist anyway, and a "
        "derived fact cannot be typed wrong, cannot drift, and cannot disagree with its object.",
    },
    {
        "kind": "numbered",
        "title": "One order — “A can stand in for B” — written down once",
        "items": [
            (
                "A replacement version",
                "Its inputs accept at least what the incumbent's did; its "
                "outputs still provide what it provided.",
            ),
            (
                "Binding data to a model",
                "The feature set's schema can stand in for the model's input contract.",
            ),
            (
                "A dependency edge",
                "What the source produces can stand in for what the target reads.",
            ),
            ("One set, two models", "The set can stand in for the meet of the two contracts."),
        ],
        "head_w": 0.24,
        "insight": "Four implementations of one relation are four chances to disagree — always "
        "towards permitting more, because a wrong refusal is reported within the hour and a "
        "wrong permission never is.",
    },
    {
        "kind": "table",
        "title": "The point-in-time read, and the four properties it has",
        "intro": "The latest record whose event time is at or before the label, and whose "
        "knowledge time is at or before the earlier of the label and the observation.",
        "rows": [
            ["Property", "What it says", "Why it matters"],
            ["Idempotent", "Reading its own result returns it", "Cached and recomputed rows agree"],
            [
                "Commutes with projection",
                "Dropping columns first changes nothing",
                "A narrower query is the same query",
            ],
            [
                "Monotone in observation",
                "A later observation admits a superset",
                "Nothing knowable stops being knowable",
            ],
            [
                "Saturating at the label",
                "After the label, the same set always",
                "Reproducibility, as a property of the read",
            ],
        ],
        "col_w": [2.8, 4.2, 4.6],
        "size": 14,
    },
    {
        "kind": "split",
        "title": "Where a machine may do the work",
        "intro": "If an answer can be checked, it matters little what produced it. If it cannot, "
        "trusting the answer is trusting the producer.",
        "left": {
            "head": "A check exists: an error costs time",
            "items": [
                ("Encode a regime", "Truth is kept under translation, or it is not."),
                ("Bind data, wire models", "The one order; a refusal names the slot."),
                ("Assemble evidence", "Recomputed by a second route, then cited."),
            ],
        },
        "right": {
            "head": "No check exists: the answer is its producer",
            "items": [
                ("Choose the tiering rule", "It is the standard."),
                ("Conclude a validation", "An exercise of authority, not a property of text."),
                ("Accept residual risk", "Somebody's decision, recorded as theirs."),
            ],
        },
        "note": "MAYA's assistant sits entirely on the left: it proposes, never approves, never "
        "blocks, and never writes to a sealed object.",
    },
]

CLOSE: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "8",
        "title": "Built today, and what comes next",
        "sub": "What version 1.0.0 does, how it compares, what it does not do, and where it is "
        "going.",
        "points": ["Built", "Compared", "Limits", "Next", "Where to start"],
    },
    {
        "kind": "cards",
        "title": "Built: the evidence core",
        "cols": 3,
        "card_h": 2.3,
        "cards": [
            (
                "FEATURES AND PINS",
                "Two clocks, sealed data",
                "Restatements append; pins are byte-identical on re-resolution.",
            ),
            (
                "FORMULA IR",
                "Mathematics as data",
                "LaTeX, Python and spreadsheets parsed, rendered, diffed and turned into code.",
            ),
            (
                "WARRANTS",
                "The checksum cycle",
                "Leakage certificates, escrowed holdouts, covenants that suspend.",
            ),
            (
                "EVIDENCE BUNDLES",
                "Verify offline",
                "Signed, re-executed, refused on one changed byte.",
            ),
            (
                "WORKFLOW",
                "Policy as data",
                "Separation of duties, delegation, break-glass, campaigns.",
            ),
            (
                "AUDIT AND CUSTODY",
                "Hash-chained",
                "Anchored outside the database, timestamped on request.",
            ),
        ],
    },
    {
        "kind": "cards",
        "title": "Built: governance and reach",
        "cols": 3,
        "card_h": 2.3,
        "cards": [
            (
                "GOVERNANCE",
                "Findings to inventory",
                "Tiers, periodic review that suspends, the SR 11-7 and SS1/23 export.",
            ),
            ("MONITORING", "Graded dashboards", "ok, watch or breach from what executions report."),
            (
                "VALIDATION",
                "Challengers and fairness",
                "Paired intervals, segments, permutation importance.",
            ),
            (
                "BLACK BOXES",
                "Scored in the sandbox",
                "Six-rung validation; conformance where a formula exists.",
            ),
            (
                "CONNECTORS",
                "MLflow, SageMaker, OpenLineage",
                "Snowflake and Databricks as read-only sources.",
            ),
            (
                "LLM APPLICATIONS",
                "Sealed versions",
                "Evaluation sets, guardrails, approval on evidence.",
            ),
        ],
    },
    {
        "kind": "compare",
        "title": "How MAYA compares, by category",
        "rows": [
            ["Capability", "MRM platforms", "ML platforms", "Feature stores", "MAYA"],
            ["Inventory, approval workflow, separation of duties", "Yes", "Partial", "No", "Yes"],
            ["Overdue periodic review stops the model running", "Partial", "No", "No", "Yes"],
            [
                "Champion and challenger on the same sealed holdout",
                "Partial",
                "Partial",
                "No",
                "Yes",
            ],
            ["Point-in-time training data, two clocks", "No", "Partial", "Yes", "Yes"],
            [
                "Data sealed by content hash, reproducible years later",
                "No",
                "Partial",
                "Partial",
                "Yes",
            ],
            ["Mathematics as a specification code is checked against", "No", "No", "No", "Yes"],
            [
                "Licence to fit or run, granted in advance and refusable",
                "Partial",
                "Partial",
                "No",
                "Yes",
            ],
            ["Evidence verified without the platform installed", "No", "No", "No", "Yes"],
            ["Training infrastructure and model serving", "No", "Yes", "Partial", "No"],
            ["Scale of deployment, ecosystem, vendor support", "Yes", "Yes", "Yes", "No"],
        ],
        "col_w": [5.0, 1.65, 1.65, 1.65, 1.65],
        "us": 4,
        "size": 12.5,
        "insight": "Categories, not vendors: a feature-by-feature claim about a named product "
        "would be wrong by its next release. The last two rows are where MAYA loses, and it "
        "says so.",
    },
    {
        "kind": "table",
        "title": "What MAYA does not do, stated rather than discovered",
        "rows": [
            ["Limit", "Why, and what it costs"],
            [
                "It trains and serves nothing itself",
                "By design: it licenses what your platform does",
            ],
            [
                "Linux is what is tested",
                "Windows runs the case studies, but its sandbox has no OS isolation",
            ],
            [
                "Connectors not yet met live",
                "Tested against published documents and recorded exchanges",
            ],
            ["MAYA's own live LLM calls, stubbed", "Recorded runs are unaffected"],
            [
                "Not yet deployed at a supervised firm",
                "No external security review; one author's work, open to inspection",
            ],
        ],
        "col_w": [4.4, 7.2],
        "size": 14,
    },
    {
        "kind": "cards",
        "title": "What comes next",
        "cols": 3,
        "card_h": 2.3,
        "cards": [
            (
                "CERTIFY CONNECTORS",
                "Live MLflow and SageMaker",
                "Run the connector suites against live services, not only their documents.",
            ),
            (
                "SECURITY REVIEW",
                "An external one",
                "The one review a project cannot do for itself.",
            ),
            (
                "FIRST MODEL IN AN HOUR",
                "Timed, with real people",
                "The success criterion that needs a stopwatch and a newcomer.",
            ),
            (
                "WINDOWS ISOLATION",
                "A sandbox tier there",
                "So the tested platform list can grow past Linux.",
            ),
            (
                "RICHER BLIND SCORES",
                "AUC, Gini, log loss",
                "Discrimination and calibration for binary targets, on the escrowed holdout.",
            ),
            (
                "MORE EXTENSION POINTS",
                "Plugins in use",
                "Wire the remaining declared points the way LLM providers already are.",
            ),
        ],
    },
    {
        "kind": "numbered",
        "title": "Where to start",
        "question": "Fifteen minutes to a running MAYA with a model in it.",
        "items": [
            (
                "docs/getting-started/QUICKSTART.md",
                "Nine steps on Python 3.13, each saying what you should see.",
            ),
            (
                "docs/getting-started/IDE.md",
                "PyCharm or IntelliJ IDEA: run, debug and test the server and the UI.",
            ),
            (
                "case_studies/",
                "Fifteen worked models; any one fills the catalog in under a minute.",
            ),
            (
                "docs/reference/API_GUIDE.md",
                "The REST API from a first curl to a sealed "
                "warrant, every example executed by the tests.",
            ),
            (
                "Help, inside MAYA",
                "Every screen ends with what it is for and a link to the full guide.",
            ),
        ],
        "head_w": 0.36,
        "size": 14,
    },
    {
        "kind": "thanks",
        "title": "Thank you",
        "sub": "Evidence, not assertion.",
        "lines": ["Ashutosh Sinha", "ajsinha@gmail.com"],
    },
]

SLIDES = WORKED + FORMAL + CLOSE
