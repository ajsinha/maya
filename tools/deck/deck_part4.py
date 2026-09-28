"""
The deck, as data. Parts 8 and 9: fifteen case studies, what is measured, and where to start.

One deck split across four modules only to keep each file under the repository's file-size gate; read them in order (see GUIDE.md).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

SLIDES: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "8",
        "title": "Fifteen models, carried the whole way",
        "sub": "Each case study is a real modelling problem taken through MAYA end to end, by named "
        "people with real roles, so the refusals are the platform's. Each is chosen for a "
        "different thing it makes MAYA do, and the suite runs every one from nothing.",
        "points": [
            "The fifteen, and what each is about",
            "A time series, split by date",
            "A prescribed formula, and a finding",
            "A bought score that drifts",
            "A challenger that earns its place",
            "A fairness question the law answers",
            "An LLM application",
            "Two of the originals",
        ],
    },
    {
        "kind": "table",
        "kicker": "The studies",
        "title": "Fifteen, different in kind",
        "rows": [
            ["Study", "Model", "What it is really about"],
            [
                "01 Retail PD scorecard",
                "Fitted logistic",
                "Bitemporality; a certificate that refuses every row",
            ],
            [
                "02 Mortgage cashflow",
                "Closed form, no fit",
                "Whether the desk's code is the approved mathematics",
            ],
            [
                "03 Mortgage prepayment",
                "Fitted hazard",
                "A change priced by shadow replay before approval",
            ],
            ["04 HELOC exposure", "Composite router", "Two members, two parameter sets, one seal"],
            ["05 Option pricing", "Calibrated closed form", "A parameter nobody can observe"],
            ["06 IFRS 9 ECL", "Composite", "Committee judgements as approved parameter sets"],
            ["07 Card-fraud network", "Declared black box", "What is left to hold to account"],
            [
                "08 AR(2) and GARCH",
                "Formula and black box",
                "The last dates held out; joint stationarity constraints",
            ],
            [
                "09 Basel IRB capital",
                "Prescribed formula",
                "Reconciliation, a finding, independent closure",
            ],
            ["10 Factor models", "Two versions", "A semantic diff and the maturity ladder"],
            ["11 Nelson–Siegel", "Non-linear", "A bug a recalibration absorbs exactly"],
            [
                "19 Vendor bureau score",
                "Bought, from MLflow",
                "Blind scoring in the sandbox; drift to breach",
            ],
            [
                "42 Demand elasticity",
                "Linear vs log-log",
                "Champion and challenger with a paired interval",
            ],
            [
                "45 Mortality table",
                "Non-linear law",
                "A bias the law requires, accepted in writing",
            ],
            [
                "49 Complaint triage",
                "LLM application",
                "Guardrails, evaluation sets, approval on evidence",
            ],
        ],
    },
    {
        "kind": "stats",
        "kicker": "Study 08 · AR(2) and GARCH(1,1)",
        "title": "A recursion MAYA cannot write, scored blind on the last dates",
        "stats": [
            ("0.9754", "fitted GARCH persistence alpha + beta; the generating process has 0.972"),
            ("840", "escrowed rows: the last 280 days of each index, in date order"),
            ("1.05", "a persistence offered and refused: each parameter fine, the pair explosive"),
            ("8.7e-4", "forecast variance in a crash week, over the 6e-4 covenant: suspended"),
        ],
        "items": [
            "The lags of the AR(2) are transforms on the governed feature, so the mean model is a "
            "formula. GARCH carries yesterday's variance as a state no column holds, so it is a "
            "declared black box, run in the sandbox on 840 rows the developer never saw.",
            "The warrants split by date: the earliest dates train and the last are the test. A random "
            "split trains on the future and scatters the rows a recursion must run through in order.",
        ],
    },
    {
        "kind": "stats",
        "kicker": "Study 09 · Basel IRB capital",
        "title": "A bracket left out, found by reconciling every obligor",
        "stats": [
            (
                "0.00982",
                "RMSE of K for version 1, reconciled blind against the regulator's reference",
            ),
            ("1.2e-16", "largest miss with maturity inside one to five years: exact"),
            ("6.5m", "capital overstated on the year-end book: 179.6m against 173.1m"),
            (
                "5.7e-17",
                "RMSE of K for version 2, with the maturity floored at one year and capped at five",
            ),
        ],
        "items": [
            "A model with nothing to fit is proved by reconciliation, and MAYA's leakage "
            "certificate records a written exception, because a reporting calculation uses figures "
            "finalised after the quarter-end by design.",
            "The validator raised a high finding; the owner fixed it as version 2, whose semantic "
            "diff is one statement; the owner was refused when she tried to close it herself, and "
            "the validator closed it.",
        ],
    },
    {
        "kind": "table",
        "kicker": "Study 19 · Vendor bureau score",
        "title": "A bought score, validated blind and taken out of service by drift",
        "intro": "Imported from its MLflow signature, its code run through the ladder in the strong "
        "sandbox, scored blind on 171 held-out applications: Brier 0.082, utilisation 43% of "
        "the importance. Then three months in production:",
        "rows": [
            ["Month", "Mean utilisation", "PSI", "Warrant", "Dashboard"],
            ["January", "0.411", "0.009", "live", "ok"],
            ["February", "0.451", "0.109", "live", "watch"],
            ["March", "0.497", "0.438", "suspended", "breach"],
        ],
    },
    {
        "kind": "stats",
        "kicker": "Study 42 · Demand elasticity",
        "title": "Winning 60% of rows, and still clearly better",
        "stats": [
            ("0.2250", "blind RMSE of the linear champion on 657 escrowed rows"),
            ("0.1940", "blind RMSE of the log-log challenger on the same rows"),
            ("[−0.040, −0.022]", "95% paired bootstrap interval for the difference"),
            ("−1.62", "the challenger's elasticity; the data's true value is −1.6"),
        ],
        "items": [
            "The challenger wins only 60% of rows, but by more where it wins: at the deepest "
            "discount the straight line's error is 0.276 against 0.235, at the steepest rise 0.170 "
            "against 0.079. Two headline RMSEs hide that; a paired comparison shows it.",
            "A warrant drawn with another seed was refused rather than compared, and the "
            "challenger's developer was refused the decision; a second manager promoted it, and "
            "the champion's live use was untouched.",
        ],
    },
    {
        "kind": "stats",
        "kicker": "Study 45 · Gompertz–Makeham mortality",
        "title": "Wrong by the same amount, in opposite directions",
        "stats": [
            ("1.08", "MAE ratio between the sexes: by error size, nothing stands out"),
            ("+0.0259", "bias for women: the unisex table overstates their mortality"),
            ("−0.0240", "bias for men: it understates theirs"),
            ("6.6 years", "of age for mortality to double, from the calibrated Gompertz slope"),
        ],
        "items": [
            "For each sex the bias is nearly the whole error, so both segments are marked "
            "systematic. The first version of MAYA's fairness evidence flagged on MAE alone, ran "
            "this study, and reported nothing; the systematic flag is what it found.",
            "The table must be unisex by law, so the finding is accepted, not fixed: by a manager, "
            "not the owner, with the ruling cited and the cross-subsidy reserved for.",
        ],
    },
    {
        "kind": "table",
        "kicker": "Study 49 · LLM complaint triage",
        "title": "Right about every category, and still not fit to use",
        "intro": "A triage application on the firm's own Azure OpenAI deployment, which MAYA does not "
        "call: answers are recorded where it runs and scored here.",
        "rows": [
            ["Run", "Passed", "What happened"],
            [
                "Version 1",
                "21 of 24",
                "Every category right; one promises a refund, two give or repeat phone and card "
                "numbers",
            ],
            [
                "Draft fixed",
                "24 of 24",
                "Same version, new definition hash: the failing run no longer describes it",
            ],
            [
                "Set extended",
                "refused",
                "A validator adds a Welsh complaint; the clean run no longer counts",
            ],
            [
                "Scored again",
                "25 of 25",
                "Submitted, the owner refused approval, approved by a model manager",
            ],
            [
                "A later change",
                "v2 draft",
                "An approved definition never changes; version 1 stays in use",
            ],
        ],
    },
    {
        "kind": "flow",
        "kicker": "Study 01 · retail credit",
        "title": "A scorecard from three CSVs to a sealed licence to run",
        "intro": "Seven scripts, run in order, each doing one step as a named person. Nothing in the "
        "study touches the database: every action goes through the SDK, as a user with the role "
        "for it.",
        "steps": [
            ("Ingest", "Three features by dana, approved by mick"),
            ("Assemble", "The panel by devi, approved by mick"),
            ("Pin", "Cascade, as of 2025-06-30, 9,600 rows"),
            ("Register", "The formula by mona, approved by mgr"),
            ("Fit", "Under a training warrant, by devi"),
            ("Approve", "Parameters by mgr; the run is blind-scored"),
            ("Seal", "Execution warrant, second approver lara"),
        ],
        "note": "case_studies/01-retail-credit-pd-scorecard — a twelve-month PD on revolving unsecured "
        "retail accounts, four drivers, fitted by IRLS in twelve lines of numpy.",
    },
    {
        "kind": "bullets",
        "kicker": "Study 11 · why it is invisible",
        "title": "The wrong loadings span the same space, so the fit absorbs the bug exactly",
        "items": [
            (
                "Recalibration hides it completely",
                "Both wrong loadings are combinations of the same three functions the correct model "
                "spans. Least squares against the buggy code lands on exactly the same curve at "
                "shifted coordinates, so in-sample error is identical to a millionth of a basis "
                "point.",
            ),
            (
                "Every test the desk would write, passes",
                "Smoke test at λ = 1: passes. Refit and check the residuals: passes. Compare against "
                "yesterday's curve: passes. Backtest: passes.",
            ),
            (
                "Only reading the code against the specification finds it",
                "Which is what a differential test is — and it finds it only when it is run at values "
                "the developer did not choose. On the validation pillars, scored blind with the "
                "approved parameters, the buggy code is out by 54 basis points against the 18 it "
                "reports in sample.",
            ),
        ],
        "note": "This is the clearest argument in the repository for generating the reference "
        "implementation from the mathematics rather than reviewing the code by eye.",
    },
    {
        "kind": "divider",
        "num": "9",
        "title": "What is measured, and what MAYA does not do",
        "sub": "The numbers a reviewer can check, the limits stated as decisions rather than left to be "
        "discovered, and where to start.",
        "points": ["What is measured", "What MAYA does not do", "Where to start"],
    },
    {
        "kind": "stats",
        "kicker": "Measured",
        "title": "Version 1.0.0, and the evidence for it",
        "stats": [
            (
                "2,109",
                "tests: 2,084 pass on SQLite and 25 are skipped by design (Keycloak, PostgreSQL-only, "
                "opt-in)",
            ),
            (
                "18",
                "gates that fail the build: typing, boundaries, parity, contrast, the API snapshot, "
                "security",
            ),
            ("252", "API endpoints, each with an SDK method and a way to reach it from the UI"),
            ("15", "case studies, each run from nothing by the suite"),
        ],
        "items": [
            "Every example in the API guide and every step of the quick start was executed against "
            "a fresh install before it was written down.",
            "Benchmarks, the capacity targets and their measurement machine are in "
            "docs/BENCHMARKS.md; the one target not met reliably on a shared workstation, 200 "
            "users on one node, is stated there.",
        ],
    },
    {
        "kind": "table",
        "kicker": "Limits",
        "title": "What MAYA does not do, stated rather than discovered",
        "rows": [
            ["Limit", "Why, and what it costs"],
            [
                "It trains and serves nothing itself",
                "By design: it licenses what an ML platform does, and batch-scores only what it can "
                "attest",
            ],
            [
                "Linux is what is tested",
                "The case studies have run on Windows, but it is outside the test matrix and its "
                "sandbox has no OS isolation",
            ],
            [
                "Connectors not met live",
                "MLflow, SageMaker, OpenLineage, Snowflake, Databricks tested against published "
                "documents only",
            ],
            [
                "Live LLM runs, stubbed",
                "MAYA's own calls to a provider are tested against a stub; recorded runs are unaffected",
            ],
            [
                "Not yet deployed at a supervised firm",
                "No external security review; one author's work, open for inspection",
            ],
        ],
    },
    {
        "kind": "bullets",
        "kicker": "Where to start",
        "title": "Fifteen minutes to a running MAYA with a model in it",
        "intro": "Three commands on a Linux machine with Python 3.13, then a case study to fill it.",
        "items": [
            (
                "docs/QUICKSTART.md",
                "Nine steps, each saying what you should see and what to do if you do not; followed "
                "literally on a fresh clone.",
            ),
            (
                "case_studies/",
                "Fifteen worked models; any one runs in well under a minute and fills the catalog.",
            ),
            (
                "docs/API_GUIDE.md",
                "The REST API from first curl to a sealed execution warrant, every example executed "
                "by the tests.",
            ),
            (
                "docs/research/",
                "The research paper: the formal account, with the proofs this deck points to.",
            ),
        ],
    },
]
