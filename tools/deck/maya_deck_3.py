"""
The deck's fifth and sixth parts: four models carried the whole way, and the closing.

Every figure on these slides was reproduced by running the study it comes from against a
MAYA built from nothing. Where a study's README and its live run disagree, the run wins and
the discrepancy is not quoted.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from maya.core.version import VERSION

_SHAPE = (
    "Each study is told in the same four movements so they can be compared: what the model "
    "is, what MAYA was given, where it said no, and what the study found. The refusals and "
    "the findings are the point. A case study that only demonstrates success is a brochure."
)

STUDIES = [
    {
        "kind": "divider",
        "num": "5",
        "title": "Four models, carried the whole way",
        "sub": "Nine studies live in the repository as runnable scripts against a throwaway "
        "instance. Four are shown here, chosen to be different in kind rather than four of "
        "the same: a plain complete pass, a model nobody can see inside, a model written as "
        "mathematics, and a composite whose hardest numbers are judgements.",
        "points": [
            "How to read these four",
            "A retail scorecard, end to end",
            "Where it said no, and why each no was right",
            "A neural network nobody can see inside",
            "What governance still holds, and what is forfeited",
            "A yield curve written in LaTeX",
            "The bug that only a second reading finds",
            "An impairment composite, and two numbers a committee owns",
            "The finding the study refused to tune away",
        ],
    },
    {
        "kind": "cards",
        "kicker": "How to read these four",
        "title": "Different in kind, so that four studies say four things",
        "intro": _SHAPE,
        "cols": 2,
        "cards": [
            (
                "01",
                "Retail PD scorecard",
                "The plainest complete pass through the whole chain: data ingested and pinned, "
                "a feature set, a fitted model, both warrants, a blind score. This is where "
                "Part 1's vocabulary becomes a sequence of steps you can run.",
            ),
            (
                "07",
                "Card-fraud neural network",
                "A declared black box. MAYA cannot see inside it, so the study is about what "
                "governance still holds when the mathematics is unavailable — and what is "
                "forfeited, refused by name rather than quietly degraded.",
            ),
            (
                "11",
                "Nelson–Siegel yield curve",
                "Four lines of LaTeX become a typed tree, and MAYA generates its own reference "
                "implementation from it. The study then finds a bug that is invisible to every "
                "test the desk would have written.",
            ),
            (
                "06",
                "IFRS 9 expected credit loss",
                "A composite of three fitted members under a combiner whose two parameters "
                "belong to an accounting committee and to no member. The most demanding of the "
                "four, and the one with the most uncomfortable finding.",
            ),
        ],
        "note": "case_studies/ — nine built of a catalogued fifty; all data is synthetic and "
        "written by the make_data.py beside each study.",
    },
    # ---- 01 -----------------------------------------------------------------------------
    {
        "kind": "flow",
        "kicker": "Study 01 · retail credit",
        "title": "A scorecard from three CSVs to a sealed licence to run",
        "intro": "Seven scripts, run in order, each doing one step as a named person. Nothing "
        "in the study touches the database: every action goes through the SDK, as a user with "
        "the role for it.",
        "steps": [
            ("Ingest", "Three features by dana, approved by mick"),
            ("Assemble", "pd_panel by devi, approved by mick"),
            ("Pin", "Cascade, as of 2025-06-30, 9,600 rows"),
            ("Register", "The formula by mona, approved by mgr"),
            ("Fit", "Under a training warrant, by devi"),
            ("Approve", "Parameters by mgr; the run is blind-scored"),
            ("Seal", "Execution warrant, second approver lara"),
        ],
        "note": "case_studies/01-retail-credit-pd-scorecard — a twelve-month PD on revolving "
        "unsecured retail accounts, four drivers, fitted by IRLS in twelve lines of numpy.",
    },
    {
        "kind": "bullets",
        "kicker": "Study 01 · the centring",
        "title": "One line of the formula that had to be in the model",
        "intro": "The scorecard's first statement is b = (bureau − 680) / 60. It is part of the "
        "governed mathematics, not a step in the fitting script, and the reason is structural "
        "rather than stylistic.",
        "items": [
            (
                "Fit and scoring have to read the same statement",
                "MAYA scores the escrowed holdout by evaluating the tree itself. If the centring "
                "lived only in the fitting script, MAYA would feed a raw 300–850 score into a "
                "coefficient calibrated to standardised units. The blind score would be garbage "
                "and nothing in the platform would notice: the parameter set would still be "
                "checksum-verified and still be approved.",
            ),
            (
                "The coefficient becomes readable",
                "+0.132 is 'per 60 points away from 680', not 'per point'. Without the "
                "declaration a committee cannot read it and a reviewer comparing it with last "
                "quarter's cannot know whether the scale moved.",
            ),
            (
                "A second implementation cannot quietly choose another centre",
                "Because the tree is the specification, a desk implementation that centred at "
                "700 would be a spec–code disagreement — which is exactly what study 11 "
                "catches.",
            ),
        ],
        "note": "The constants are fixed by design and not fitted, and the specification says "
        "so in those words.",
    },
    {
        "kind": "table",
        "kicker": "Study 01 · where it said no",
        "title": "Five refusals, each one a rule rather than a convention",
        "rows": [
            ["Refused", "What MAYA said", "Why that is right"],
            [
                "dana approving her own feature",
                "role ceiling: no 'A' on feature in roles feature_designer",
                "A capability ceiling, not a workflow step. No grant raises it.",
            ],
            [
                "Submitting a model with an empty document",
                "required sections empty: Purpose, Scope and Limitations, Assumptions …",
                "The document is the gate. Two of the nine sections MAYA pre-fills from the "
                "parsed tree, so only seven are named.",
            ],
            [
                "A warrant whose leakage certificate was refused",
                "leakage certificate: refused; 9,600 violating row(s)",
                "The panel's clock is the latest of its members', and the twelve-month default "
                "flag is knowable a year and a day later. Every row, arithmetically.",
            ],
            [
                "Parameters that cannot prove their data",
                "the checksum does not match any download MAYA issued",
                "'Which data produced these numbers' gets a cryptographic answer instead of a "
                "changelog entry.",
            ],
            [
                "Serving while suspended",
                "null rate of 'bureau' 0.310 > 0.05",
                "The warrant suspended itself on a reported batch and named the number and the "
                "owner to contact.",
            ],
        ],
        "size": 12,
        "note": "The leakage refusal is resolved by writing the exception down, not by widening "
        "the rule: the justification names the target column and is recorded on the warrant.",
    },
    {
        "kind": "stats",
        "kicker": "Study 01 · what it found",
        "title": "Including the two findings nobody would put in a brochure",
        "stats": [
            (
                "0.754 / 0.763",
                "AUC train / validation — close together, which is the check that nothing leaked",
            ),
            ("683", "of 8,151 rows have no bureau score and are excluded rather than filled"),
            ("0.406", "blind holdout error on 1,449 rows the developer never saw"),
            ("26.7%", "realised twelve-month default rate in the generated book"),
        ],
        "items": [
            "The gap is not a bug and is not hidden: the earliest observation months precede "
            "the first bureau delivery, as-of alignment leaves a gap as a gap, and the model's "
            "Known Weaknesses section says the model has nothing to say about those accounts.",
            "The blind figure is read correctly rather than flatteringly. On a zero-one target "
            "the mean squared error is the Brier score, so 0.406 is a calibration statement and "
            "not a discrimination one; the AUCs above are discrimination and were computed on "
            "data the developer could see. The specification keeps the two claims apart.",
            "Declared and not tuned away: no macroeconomic driver, so it cannot answer a "
            "scenario question; the bureau score is stale by up to a quarter, which flatters it "
            "in a fast deterioration; the linear log-odds assumption fails in the tails.",
        ],
        "note": "All figures reproduced from a live run of the study.",
    },
    # ---- 07 -----------------------------------------------------------------------------
    {
        "kind": "split",
        "kicker": "Study 07 · card fraud",
        "title": "A model nobody can see inside, governed anyway",
        "intro": "A 6 → 12 → 8 → 1 network, 209 fitted values in eight arrays, declared to MAYA "
        "as a black box. There is no formula: MAYA's rendered mathematics for this version is "
        "the empty string.",
        "left": {
            "head": "What governance still holds",
            "items": [
                "The input contract, and a warrant that refuses a feature set which does not "
                "satisfy it",
                "The declared parameters — all eight arrays — checked for completeness at upload",
                "The leakage certificate over the training rows",
                "Covenants on the inputs, and a warrant that suspends itself",
                "An evidence bundle, which verifies its inputs",
            ],
        },
        "right": {
            "head": "What is forfeited, by name",
            "items": [
                "Blind scoring. MAYA will not score a declared black box, because it holds no "
                "executable specification to score it against",
                "Conformance testing against the mathematics, for the same reason",
                "Re-execution in the bundle. The verifier's third line says so in words rather "
                "than omitting the check",
                "Any explanation of a score. The model is declared to rank a review queue and "
                "to explain nothing",
            ],
        },
        "note": "Nothing quietly degrades: each of these is a refusal with a message, at the "
        "point a platform that wanted to look good would have said nothing.",
    },
    {
        "kind": "bullets",
        "kicker": "Study 07 · what it found",
        "title": "The study computes the case against its own model",
        "items": [
            (
                "A crafted challenger gets within 0.012",
                "A logistic regression told the three true conjunctions reaches 0.9624 against "
                "the network's 0.9745. What the network bought is discovering the conjunctions, "
                "not representing them — and a reviewer is entitled to ask for the crafted "
                "challenger before accepting the opaque one.",
            ),
            (
                "The weights are not identified; the procedure is",
                "Refitting with the same seed reproduces all 209 values exactly. Refitting with "
                "a different seed moves a weight by 3.69 and changes validation AUC by 0.001. "
                "So comparing this quarter's weights with last quarter's tells you nothing "
                "unless the seed was held.",
            ),
            (
                "The validation score is above the training score, and is quoted anyway",
                "0.9745 against 0.9526, on 92 confirmed frauds: that gap is noise. A study that "
                "only quoted the flattering direction would not be worth reading.",
            ),
            (
                "The failure mode will look like silence",
                "The network learned two fraud patterns and will not recognise a third — and "
                "because it cannot explain itself, that failure will not look like an error.",
            ),
        ],
        "note": "The study also found a platform defect: a black box's declared parameters were "
        "recorded as an empty schema and checked by nothing, so a set missing an entire layer "
        "was accepted. Both halves guarded on the formula body instead of the declaration.",
    },
    # ---- 11 -----------------------------------------------------------------------------
    {
        "kind": "bullets",
        "kicker": "Study 11 · the yield curve",
        "title": "Written as mathematics, and checked as mathematics",
        "intro": "Nelson–Siegel, registered from four lines of LaTeX. MAYA parses it into a "
        "typed tree, generates its own reference implementation from that tree, and the "
        "calibrator asks the model for its own factor loadings rather than writing them down "
        "again.",
        "items": [
            (
                "There is no second curve to be wrong differently",
                "The design matrix is obtained by evaluating the approved tree with one factor "
                "at 1 and the others at 0. Superposition against the model's own output holds "
                "to exactly zero, and the curve the calibration fits is the curve the blind "
                "score reprices with.",
            ),
            (
                "A constraint a table of bounds cannot hold",
                "β₀ + β₁ is the instantaneous short rate and cannot be negative. A bound belongs "
                "to one parameter; this spans two. The offending set satisfies every single "
                "bound and implies a short rate of −6.7%.",
            ),
            (
                "Joint constraints exist because this study asked for them",
                "Before the fix, the only thing between that curve and production was that "
                "somebody had to approve it. The constraint now carries a mandatory written "
                "reason, because the reason is the only thing the modeller sees when it fires.",
            ),
            (
                "The parameter is barely identified, and the specification says so",
                "Trebling the decay constant from 1.06 to 3.37 costs less than half a basis "
                "point over 7,683 pillars. Read day by day the best value wanders over a factor "
                "of four on data whose value never moved. That is not the market; it is an "
                "unidentified parameter reading its own noise.",
            ),
        ],
        "note": "So the specification records the decay constant as a convention approved once "
        "and revisited annually, not as a measurement — and says 'it is flat' in those words.",
    },
    {
        "kind": "table",
        "kicker": "Study 11 · the loading bug",
        "title": "The same code, three comparisons, two different answers",
        "intro": "The desk's implementation divides by τ where it should divide by τ/λ — the "
        "commonest error there is in this model. The wrong loading is the right one divided by "
        "λ, so at λ = 1 the two are identical. λ = 1 is the round number a developer puts in a "
        "smoke test, and MAYA's differential test uses the developer's own sample.",
        "rows": [
            ["Comparison", "At which parameter values", "Agreement"],
            [
                "Default domain, on upload",
                "The desk's own: λ = 1",
                "2,000 of 2,000",
            ],
            [
                "The pinned curve, 10,962 rows",
                "The desk's own: λ = 1",
                "2,000 of 2,000",
            ],
            [
                "The pinned curve, 10,962 rows",
                "MAYA's, drawn from the declared bounds: λ = 3.804",
                "0 of 2,000",
            ],
        ],
        "note": "The gate passes on the first two, because it asks whether the last comparison "
        "agreed everywhere it looked — and it did, at one parameter value chosen by the "
        "developer. The reviewer catches it, and what she needs is now printed beside the "
        "count: the values it was run at.",
    },
    {
        "kind": "bullets",
        "kicker": "Study 11 · why it is invisible",
        "title": "The wrong loadings span the same space, so the fit absorbs the bug exactly",
        "items": [
            (
                "Recalibration hides it completely",
                "Both wrong loadings are combinations of the same three functions the correct "
                "model spans. Least squares against the buggy code lands on exactly the same "
                "curve at shifted coordinates, so in-sample error is identical to a millionth "
                "of a basis point.",
            ),
            (
                "Every test the desk would write, passes",
                "Smoke test at λ = 1: passes. Refit and check the residuals: passes. Compare "
                "against yesterday's curve: passes. Backtest: passes.",
            ),
            (
                "Only reading the code against the specification finds it",
                "Which is what a differential test is — and it finds it only when it is run at "
                "values the developer did not choose. On the validation pillars, scored blind "
                "with the approved parameters, the buggy code is out by 54 basis points against "
                "the 18 it reports in sample.",
            ),
        ],
        "note": "This is the clearest argument in the repository for generating the reference "
        "implementation from the mathematics rather than reviewing the code by eye.",
    },
    # ---- 06 -----------------------------------------------------------------------------
    {
        "kind": "split",
        "kicker": "Study 06 · IFRS 9",
        "title": "Three models and two decisions, governed as one object",
        "intro": "Expected credit loss is the product of three estimates, taken over twelve "
        "months or a lifetime according to a stage test. Three of those are models. Two — the "
        "significant-increase threshold and the lifetime multiple — are decisions an impairment "
        "committee argues about, and they belong to no member.",
        "left": {
            "head": "What MAYA computed for itself",
            "items": [
                "The composite's input contract, as the union of its members' — seven inputs, "
                "each naming which members need it",
                "Which of those are features the feature set must supply, and which are "
                "parameters somebody has to approve",
                "The maturity of the whole, capped at its least mature member",
                "That the seal was still owed the combiner's own two parameters",
            ],
        },
        "right": {
            "head": "What the study had to change",
            "items": [
                "The union contract took only the members' declarations, so the combiner's own "
                "parameters were declared nowhere",
                "The bounds check therefore had nothing to look for, and the warrant would seal "
                "with the two most argued-over numbers in the model unapproved",
                "They are part of the contract now, and the refusal names what is outstanding: "
                "'the combiner's own parameters'",
            ],
        },
        "note": "The committee's decision is uploaded as an approved parameter set with a "
        "written justification, because its provenance is minutes rather than a download MAYA "
        "issued — and quoting the training data's checksum to clear the flag would have been a "
        "small lie.",
    },
    {
        "kind": "stats",
        "kicker": "Study 06 · what it found",
        "title": "The test that can actually fail, and did",
        "stats": [
            ("2.67×", "the allowance the model implies, against the loss actually realised"),
            ("82.8%", "of accounts in stage 2, contributing 99.5% of the allowance"),
            ("−90.7%", "the blind per-account error against holding no allowance at all"),
            ("31%", "still over realised loss at a threshold nobody would defend"),
        ],
        "items": [
            "The per-account error is worse than predicting zero for everybody, and it should "
            "be: realised loss is zero on 92.4% of rows, so predicting zero is the best "
            "per-account guess and an expected-loss model deliberately does not make it. A "
            "per-account error cannot distinguish a well-levelled allowance from a badly "
            "levelled one, and quoting one as accuracy would mislead. Both attempts are counted "
            "on the warrant, so the comparison is on the record rather than in a README.",
            "The threshold grid shows the committee's choice explains part of the coverage gap "
            "and not the rest of it: even at forty times the threshold the allowance is still a "
            "third above realised loss. The study records the residual as an open finding "
            "rather than choosing the number that would have closed it.",
            "Every fitted coefficient is attenuated toward the generating process's, which the "
            "study notes rather than presenting the fit as a recovery of truth.",
        ],
        "note": "case_studies/06-ifrs9-expected-credit-loss — figures from a live run.",
    },
    {
        "kind": "cards",
        "kicker": "Four studies, one lesson each",
        "title": "What each of them is actually evidence for",
        "cols": 2,
        "cards": [
            (
                "01",
                "The chain holds under a real model",
                "Every object in Part 1 appears, every refusal is a rule somebody wrote down, "
                "and the two unflattering findings are in the specification rather than in a "
                "footnote.",
            ),
            (
                "07",
                "Opacity is a declaration with consequences",
                "MAYA governs what it can and refuses the rest by name. The study argues "
                "against its own model, and the platform defect it found was a check guarding "
                "on the wrong thing.",
            ),
            (
                "11",
                "A specification you can execute catches what review cannot",
                "A one-character error that survives every test a desk would write, found by "
                "comparing code against mathematics at values the developer did not choose.",
            ),
            (
                "06",
                "The hardest numbers are the ones nobody fitted",
                "A committee's two judgements drive 99.5% of the allowance. They are now "
                "declared, bounded, approved and on the record — and the finding they leave "
                "open is recorded as open.",
            ),
        ],
        "note": "All nine studies run in seconds against a throwaway instance: "
        ".venv/bin/python case_studies/<study>/run.py",
    },
]

CLOSING = [
    {
        "kind": "divider",
        "num": "6",
        "title": "What is measured, and what MAYA does not do",
        "sub": "A design without stated losses is a sales pitch. This part gives the numbers as "
        "they were measured, including the one target that is not met reliably, and then the "
        "things a buyer would otherwise have to find out for themselves.",
        "points": [
            "What this version is",
            "Seven targets met, one not reliably",
            "The run that fell short, in full",
            "Out of scope by decision",
            "Not yet, stated so nobody discovers it",
            "Accepted risks, and where MAYA chooses to lose",
            "In one slide",
        ],
    },
    {
        "kind": "stats",
        "kicker": "Status",
        "title": f"Version {VERSION}, built from specification revision 2.6",
        "stats": [
            (VERSION, "released 19 September 2026, from specification revision 2.6"),
            ("1,706", "tests on Linux; 1,696 pass on SQLite and 10 are opt-in or need PostgreSQL"),
            ("215", "endpoints, each with an SDK method, checked both ways by a gate"),
            ("92.9%", "line coverage, against a 90% floor in the gate ladder"),
        ],
        "items": [
            "The whole spine runs through all four surfaces: source, feature, feature set, pin, "
            "model, training warrant, parameter set, execution warrant, evidence bundle.",
            "The suite last ran green on PostgreSQL 16, 17 and 18 at 1,262 tests; the ones added "
            "since have run on SQLite only. With every optional accelerator on its fallback it "
            "passed at 1,150 tests and has not been rerun since.",
            "It includes real-browser tests in headless Chrome, several web processes on one "
            "node over PostgreSQL, and a two-year-old training run reproduced byte for byte "
            "from its evidence bundle alone.",
        ],
        "note": "README status row and tools/ci/gates.py, both re-read for this deck.",
    },
]

SLIDES = STUDIES + CLOSING
