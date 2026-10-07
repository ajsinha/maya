"""
The deck, as data. Part 4, governance a model risk function works in; Part 5, beyond
formulas.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

GOVERNANCE: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "4",
        "title": "Governance a model risk function works in",
        "sub": "Nothing here is a new form. Every screen reads the warrants, pins, scores and "
        "reports the lifecycle already produced.",
        "points": [
            "Findings",
            "Materiality",
            "Periodic review",
            "Monitoring",
            "Champion and challenger",
            "Fairness",
            "The inventory",
        ],
    },
    {
        "kind": "shot",
        "title": "Findings and reviews, in one place",
        "image": "governance.png",
        "caption": "Governance: every model with its tier, next periodic review and findings",
        "items": [
            ("Tier", "How material a model is; it sets how often it is reviewed."),
            ("Findings", "Severity, owner, due date and history on every defect."),
            ("Periodic review", "Overdue means suspended, not a red cell."),
            ("Inventory", "Exported in SR 11-7 or SS1/23 layout, straight from the records."),
        ],
    },
    {
        "kind": "numbered",
        "title": "A finding has an owner, a due date — and an independent closer",
        "items": [
            (
                "Raised",
                "By a validator, with a severity; due in 30, 90, 180 or 365 days by default.",
            ),
            ("Remediated", "By the owner — often as a new model version."),
            ("Closed", "Only by someone who did not remediate it, or sent back as not fixed."),
            (
                "Or accepted",
                "The risk kept rather than fixed, with a written reason — never the owner's call.",
            ),
        ],
        "head_w": 0.18,
        "insight": "In study 09 the owner fixed a missing maturity floor and cap as version 2, "
        "tried to close the finding herself, and was refused; the validator closed it.",
    },
    {
        "kind": "table",
        "title": "Materiality: a tier derived from evidence",
        "intro": "Tier 1 is the most material. The tier is the highest driver's score, one tier "
        "higher for a black box; an override needs a reason, and one that lowers it is flagged.",
        "rows": [
            ["Driver", "Where it comes from", "Scores"],
            [
                "Use",
                "Declared by the owner: regulatory, reporting, decision, internal",
                "3 · 3 · 2 · 1",
            ],
            ["Exposure", "Declared by the owner", "3 over 1bn, 2 over 10m"],
            [
                "Reach",
                "Measured: live execution warrants and executions",
                "3 at three warrants or 10,000 runs",
            ],
            ["Transparency", "Measured: formula or black box", "+1 tier for a black box"],
            [
                "Questionnaire",
                "The firm's own file, config/tiering.yaml",
                "Highest answer, or points against thresholds",
            ],
        ],
        "col_w": [2.0, 6.0, 3.6],
        "size": 14,
    },
    {
        "kind": "numbered",
        "title": "An overdue review stops the model running",
        "items": [
            ("The tier sets the interval", "One, two or three years, or set per model."),
            ("The due date", "From the last review, or from the first approval."),
            ("The sweep", "Hourly: an overdue model's live execution warrants are suspended."),
            (
                "The review",
                "Recorded by a model manager, validator or administrator — never the owner.",
            ),
            ("Lifted", "Exactly the suspensions the sweep made, and no others."),
        ],
        "head_w": 0.22,
        "insight": "A review is not a reminder in someone's calendar; it is a condition of "
        "running. A warrant suspended for a breach stays suspended when a review is recorded.",
    },
    {
        "kind": "shot",
        "title": "Every live model graded ok, watch or breach",
        "image": "monitoring.png",
        "caption": "Monitoring: live models graded from what their executions report",
        "items": [
            ("Breach", "Suspended, or a covenant broken in the last seven days."),
            (
                "Watch",
                "Population stability above 0.10, a null rate doubling, or a live model "
                "silent for thirty days.",
            ),
            (
                "Per warrant",
                "Rows per day; drift, nulls and means per input, against the covenant's bounds.",
            ),
            (
                "Study 19",
                "A bureau score goes ok, watch, breach as utilisation drifts: PSI "
                "0.009, 0.109, 0.438.",
            ),
        ],
    },
    {
        "kind": "split",
        "title": "Champion and challenger, on evidence",
        "intro": "Two warrants on the same pin with the same seed hold the same escrowed rows. "
        "MAYA scores both and compares them row by row.",
        "left": {
            "head": "What is reported",
            "items": [
                ("The difference", "In RMSE or MAE, challenger minus champion."),
                ("A paired bootstrap interval", "95%, 2,000 draws, a fixed seed."),
                ("The verdict", "Challenger better only if the whole interval is below zero."),
            ],
        },
        "right": {
            "head": "What is refused",
            "items": [
                ("Different holdouts", "Not compared at all."),
                ("The author deciding", "The challenger's owner never decides."),
                (
                    "Study 42",
                    "Log-log beats linear: −0.031, interval [−0.040, −0.022], winning 60% of rows.",
                ),
            ],
        },
    },
    {
        "kind": "split",
        "title": "Fairness and explainability, on the holdout",
        "left": {
            "head": "Error by segment",
            "items": [
                ("Per segment", "RMSE, MAE, bias and mean prediction for each value of a column."),
                ("Flagged", "MAE a quarter above the overall figure."),
                ("Systematic", "Bias over half the MAE: wrong in one direction."),
                ("Suppressed", "Under twenty rows, no figures."),
            ],
        },
        "right": {
            "head": "What drives it",
            "items": [
                ("Permutation importance", "Each input shuffled; the rise in error is its weight."),
                ("Black boxes too", "Measured through the sandbox: it needs only predictions."),
                (
                    "Study 45",
                    "Men's and women's errors are the same size and opposite in sign — "
                    "both systematic.",
                ),
            ],
        },
    },
    {
        "kind": "table",
        "title": "The supervisory inventory, never re-typed",
        "intro": "Excel, CSV or JSON in an SR 11-7 or SS1/23 layout, built from the records MAYA "
        "keeps. The file says how many models the exporter could not see.",
        "rows": [
            ["Column group", "What it holds"],
            ["Identity", "Purpose, use, type, vendor or provider, owner"],
            ["Materiality", "Tier, derived tier, its basis, any override and why, exposure"],
            ["Approval and evidence", "Status, approval, what shows the code computes the model"],
            ["Review and findings", "Last review, next due, open, overdue and accepted findings"],
            ["Use", "Live warrants, environments, executions, monitoring grade, limits on use"],
        ],
        "col_w": [3.0, 8.6],
        "size": 14,
    },
]

BEYOND: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "5",
        "title": "Beyond formulas",
        "sub": "Most of what a bank now runs is not a formula anyone can read. Each gets the same "
        "chain, and forfeits exactly the evidence it cannot give — no more.",
        "points": [
            "Black boxes",
            "Is the code the mathematics?",
            "Connectors",
            "Beside your ML platform",
            "LLM applications",
        ],
    },
    {
        "kind": "numbered",
        "title": "A black box, scored blind where nobody sees the data",
        "items": [
            ("Declared", "It states what it estimates and how it is built."),
            ("Validated", "Its code through six rungs, then run twice in the sandbox."),
            (
                "Scored blind",
                "In the sandbox, on the holdout's inputs only — the target never enters.",
            ),
            (
                "Metrics out",
                "MAYA computes them; rows never leave; the artifact's hash is recorded.",
            ),
        ],
        "head_w": 0.18,
        "insight": "A black box with no validated artifact is refused by name, and one that reads "
        "the target as an input is refused rather than handed the answer.",
    },
    {
        "kind": "split",
        "title": "Is the code the mathematics?",
        "intro": "A model has two descriptions: the formula MAYA holds and the Python someone "
        "uploaded. MAYA compares them on numbers instead of asking anyone to assert it.",
        "left": {
            "head": "Conformance testing",
            "items": [
                (
                    "The comparison",
                    "Uploaded code against MAYA's own evaluation, to a relative 1e-9.",
                ),
                ("Counterexamples", "Up to ten disagreeing rows, expected and actual."),
                ("Tied to the artifact", "No advance until conformance ran on that hash."),
            ],
        },
        "right": {
            "head": "Honest about itself",
            "items": [
                ("Sampled, not proved", "The report says so in its first words."),
                ("Dials off-centre", "So a test cannot miss a bug on a round number."),
                ("Study 11", "A bug a recalibration absorbs exactly — only this test sees it."),
            ],
        },
    },
    {
        "kind": "table",
        "title": "Models trained elsewhere come in; lineage goes out",
        "rows": [
            ["System", "What MAYA does", "What it insists on"],
            [
                "MLflow",
                "Imports a model from its MLmodel file or tracking server",
                "A signature: the input contract is the vendor's",
            ],
            [
                "Amazon SageMaker",
                "Imports a model package: image, data, framework, approval",
                "Inputs named, since SageMaker records none",
            ],
            [
                "OpenLineage",
                "Every lineage edge as a RunEvent, to Marquez or any consumer",
                "Administrators only",
            ],
            [
                "Snowflake, Databricks",
                "Read-only SQL sources through their dialects",
                "A read-only role; SELECT only",
            ],
        ],
        "col_w": [2.6, 5.2, 3.8],
        "size": 14,
        "note": "Tested against each system's published documents and a recorded exchange — not "
        "yet against a live service, and the documentation says so.",
    },
    {
        "kind": "table",
        "title": "Beside your ML platform, not instead of it",
        "rows": [
            ["Step", "What MAYA does", "What it never does"],
            [
                "Registry",
                "Sets an MLflow alias while the execution warrant is live",
                "Deploy: your deployment follows the alias",
            ],
            [
                "Scoring call",
                "An SDK guard checks the warrant before and reports after",
                "Sit in your request path",
            ],
            [
                "Training",
                "Turns a warrant into a signed Kubernetes or SageMaker job",
                "Run the job: it goes to your compute",
            ],
            [
                "Batch scoring",
                "Scores a pinned table under a live warrant, output sealed",
                "Serve online",
            ],
        ],
        "col_w": [2.0, 5.6, 4.0],
        "size": 14,
    },
    {
        "kind": "shot",
        "title": "LLM applications: a prompt is a model's parameters",
        "image": "llm-app.png",
        "caption": "An LLM application: sealed versions, evaluation sets and runs",
        "items": [
            (
                "A version seals",
                "Provider, model, prompts, parameters and guardrails under one hash.",
            ),
            (
                "Evaluated",
                "Deterministic checks — contains, equals, regex, JSON, length — and "
                "guardrails for blocked terms and personal data.",
            ),
            (
                "Approved on evidence",
                "A clean run on exactly that hash, by a manager who is not the owner.",
            ),
            (
                "Study 49",
                "Version 1 gets every category right and still fails: it read a card number back.",
            ),
        ],
    },
]

SLIDES = GOVERNANCE + BEYOND
