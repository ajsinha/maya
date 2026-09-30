"""
The deck, as data. Parts 3 to 5: the lifecycle, the governance layer, and models beyond formulas.

One deck split across four modules only to keep each file under the repository's file-size gate; read them in order (see GUIDE.md).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

SLIDES: list[dict[str, Any]] = [
    {
        "kind": "divider",
        "num": "3",
        "title": "The lifecycle, end to end",
        "sub": "One chain, from a delivered file to a model running under a live licence and reporting "
        "back. Each link is a governed object with an owner, a version and an approval, and each "
        "one refuses something on purpose.",
        "points": [
            "What MAYA sits between",
            "The chain, in one picture",
            "Writing the mathematics",
            "Fitting under a warrant",
            "Running under a licence",
        ],
    },
    {
        "kind": "context",
        "kicker": "System context",
        "title": "What MAYA sits between",
        "intro": "MAYA is a system of record, not an execution engine: it never trains a model and never "
        "serves a prediction.",
        "nodes": [
            {
                "id": "src",
                "x": 0.0,
                "y": 0.0,
                "w": 0.22,
                "h": 0.3,
                "head": "Source systems",
                "body": "Pulled, never read through.",
            },
            {
                "id": "people",
                "x": 0.39,
                "y": 0.0,
                "w": 0.26,
                "h": 0.3,
                "head": "People, with roles",
                "body": "Designers, managers, owners.",
            },
            {
                "id": "idp",
                "x": 0.78,
                "y": 0.0,
                "w": 0.22,
                "h": 0.3,
                "head": "Identity provider",
                "body": "OIDC or SAML.",
            },
            {
                "id": "maya",
                "x": 0.1,
                "y": 0.38,
                "w": 0.8,
                "h": 0.22,
                "head": "MAYA — one API, four ways to reach it",
                "body": "Web, SDK, CLI and REST over 246 operations.",
            },
            {
                "id": "lake",
                "x": 0.0,
                "y": 0.72,
                "w": 0.22,
                "h": 0.28,
                "head": "maya_delta",
                "body": "Data and sealed pins.",
            },
            {
                "id": "db",
                "x": 0.26,
                "y": 0.72,
                "w": 0.22,
                "h": 0.28,
                "head": "Metadata database",
                "body": "SQLite, or PostgreSQL.",
            },
            {
                "id": "sandbox",
                "x": 0.52,
                "y": 0.72,
                "w": 0.22,
                "h": 0.28,
                "head": "The sandbox",
                "body": "Where an artifact runs.",
            },
            {
                "id": "bundle",
                "x": 0.78,
                "y": 0.72,
                "w": 0.22,
                "h": 0.28,
                "head": "Evidence bundles",
                "body": "Verified without MAYA.",
            },
        ],
        "edges": [
            ["src", "maya", "pulled"],
            ["people", "maya", "act through a role"],
            ["idp", "maya", "sign-in"],
            ["maya", "lake", "rows and pins"],
            ["maya", "db", "objects and audit"],
            ["maya", "sandbox", "artifact runs"],
            ["maya", "bundle", "exported"],
        ],
        "note": "Outside the line, deliberately: whatever trains the model and whatever serves it. A "
        "platform that ran the artefacts it governs would be checking its own work.",
    },
    {
        "kind": "flow",
        "kicker": "The chain",
        "title": "From a delivered file to a model reporting back",
        "steps": [
            (
                "Feature",
                "A feed defined, loaded with its knowledge times, approved by somebody else",
            ),
            ("Pin", "A feature set frozen as of a date, sealed by the hash of its rows"),
            ("Model", "The mathematics as a typed tree, with its specification, approved"),
            ("Training warrant", "Model and pin bound; the holdout escrowed; leakage certified"),
            (
                "Execution warrant",
                "Approved parameters licensed to run, with covenants, until a date",
            ),
        ],
        "box_h": 1.9,
        "items": [
            "Every arrow is a refusal waiting to happen: an unapproved feature cannot be pinned, "
            "an unpinned set cannot be warranted, a model whose inputs the pin lacks cannot be "
            "bound, and parameters fitted on data MAYA did not issue cannot be approved.",
            "The chain is the same whether the model is a two-line formula, a neural network, a "
            "vendor's score or an LLM application — what changes is which evidence each link can "
            "produce.",
        ],
    },
    {
        "kind": "flow",
        "kicker": "The compute-kernel wizard",
        "title": "Write the mathematics; read back what MAYA made of it",
        "steps": [
            ("Write", "As LaTeX or plain text, and say which symbols are the dials"),
            ("Translate", "MAYA parses it into the typed tree, or refuses and names the position"),
            (
                "Read back",
                "The tree, the LaTeX it renders as, each input with the role it was given, the "
                "intermediates in order",
            ),
            ("Take the function", "One portable function, or the full reference module"),
        ],
        "box_h": 2.0,
        "items": [
            "It reads nothing and writes nothing. Whoever wrote the mathematics sees what MAYA "
            "made of it before a model version exists to attach it to; the alternative is finding "
            "out at registration, which is later and more expensive.",
            "The emitted kernel is one self-contained function taking the inputs and the dials and "
            "returning one value per row. Imports and helpers sit inside the function body, and it "
            "needs numpy alone unless the formula uses a normal distribution.",
            "The same parser and the same code emitter serve registration, so the wizard shows "
            "what a registered version would hold rather than a mock-up of it. Black–Scholes, a "
            "logistic probability of default and a Nelson–Siegel curve ship as worked examples on "
            "the page.",
        ],
        "note": "Web page /models/kernel; API POST /formula/kernel; SDK client.models.kernel. "
        "maya/formula/parse.py and codegen.py; "
        "tests/test_compute_kernel.py::test_the_kernel_is_one_function_and_nothing_else.",
    },
    {
        "kind": "flow",
        "kicker": "Training warrants",
        "title": "The checksum cycle that turns paperwork into a control",
        "steps": [
            (
                "Draw",
                "An approved model against a pinned feature set; the contract is checked and every "
                "miss listed",
            ),
            ("Certify", "A signed leakage certificate is issued with the warrant, or refuses it"),
            ("Download", "Train and validation only; who, when and the content hash recorded"),
            (
                "Upload",
                "Dials checked against that hash, against their bounds, and against any joint "
                "constraint",
            ),
            ("Seal", "Approval by policy; every referenced object becomes undeletable"),
        ],
        "box_h": 2.1,
        "items": [
            "The test partition is escrowed: hashed and its row count fixed when the warrant is "
            "drawn, and not included in the download. MAYA scores uploaded dials against it, "
            "returns metrics only, and numbers every attempt on the warrant.",
            "Dials fitted on data matching no checksum MAYA issued are flagged and cannot be "
            "approved without an explicit written justification. That is how a judgement, as "
            "distinct from a fit, gets recorded honestly rather than disguised as one.",
            "A warrant defaults to a 70 / 15 / 15 split, seed 42, an escrowed holdout and a year's "
            "expiry — all overridable, and all recorded on the warrant rather than remembered.",
        ],
        "note": "maya/services/warrants.py; "
        "tests/test_warrants.py::test_the_checksum_cycle_seal_score_execute_and_bundle and "
        "::test_contract_mismatch_is_refused_listing_every_attribute.",
    },
    {
        "kind": "split",
        "kicker": "Look-ahead, and the holdout",
        "title": "The leakage certificate, and what the developer never receives",
        "left": {
            "head": "The leakage certificate",
            "items": [
                (
                    "The rule",
                    "Every row's ingest time is at or before its event date plus the declared "
                    "lag, one day by default. That is Part 6's operator, checked over the frame "
                    "that was actually assembled.",
                ),
                (
                    "Three verdicts",
                    "Certified; certified with exceptions, where every exception carries a "
                    "written justification; or refused.",
                ),
                (
                    "Signed, and specific",
                    "Rows examined, the violations with up to twenty example rows, and each "
                    "exception's reason. Without a signing backend it says it is unsigned, and "
                    "why.",
                ),
                (
                    "Honest about its own scope",
                    "It examines the rows the frame carries an ingest time for, and states how "
                    "many it read rather than implying it read them all.",
                ),
            ],
        },
        "right": {
            "head": "The escrowed holdout",
            "items": [
                (
                    "Fixed when the warrant is drawn",
                    "The test partition is hashed and its row count recorded at that moment, so "
                    "the set cannot move afterwards.",
                ),
                (
                    "Scored by MAYA, not by the developer",
                    "MAYA re-derives the split, refuses if the escrowed set has moved, "
                    "evaluates the mathematics in process, and returns metrics only.",
                ),
                (
                    "Every attempt numbered",
                    "Because “scored forty times, best reported” is a fact a reviewer should be "
                    "able to see, and it is not visible anywhere else.",
                ),
                (
                    "The one runtime exception MAYA concedes",
                    "It scores the mathematics and never the uploaded artifact — and for a "
                    "declared black box there is no mathematics to score, so it refuses by "
                    "name.",
                ),
            ],
        },
        "note": "maya/services/warrants.py; "
        "tests/test_warrants.py::test_leakage_certificate_refuses_late_knowledge; ADR-007, which "
        "states that exception and no more.",
    },
    {
        "kind": "table",
        "kicker": "Execution warrants",
        "title": "A live licence: it expires, it is revoked, and it suspends itself",
        "rows": [
            ["Control", "Behaviour"],
            [
                "Drawn from",
                "A training warrant and an approved parameter set, or straight from a model that takes "
                "no dials at all",
            ],
            [
                "Environments",
                "dev, uat, prod — each permitted explicitly, and an approval may be required only for "
                "prod",
            ],
            [
                "Covenants",
                "Input null rate, input range, input population stability, output range, maximum rows "
                "per day, staleness in days. A breach suspends the warrant at once, writes a custody "
                "event and notifies the owner",
            ],
            [
                "Population drift",
                "A population stability index against a baseline fixed when the warrant was drawn, so "
                "the baseline cannot move later; the default ceiling is 0.25 over ten bins",
            ],
            [
                "Limits",
                "Calls per day, rows per call, rows per day — these throttle and record overage; they "
                "do not suspend",
            ],
            [
                "Reinstatement",
                "By the model owner or an administrator, with a written reason. A covenant naming no "
                "output on a multi-output model is refused at creation: a covenant with nothing to "
                "compare against is worse than none",
            ],
            [
                "Offline use",
                "Permitted, and both the copy and the warrant are labelled unattested for good",
            ],
        ],
        "col_w": [2.0, 9.6],
        "note": "maya/services/execution.py; tests/test_security_regressions.py::test_each_covenant and "
        "::test_execution_limits. A revoked, expired or suspended warrant fails every consuming "
        "call closed, naming the covenant that broke or the person to contact.",
    },
    {
        "kind": "split",
        "kicker": "Evidence",
        "title": "A bundle that proves itself on a machine with no MAYA",
        "left": {
            "head": "What is in the archive",
            "items": [
                (
                    "The subject and its data",
                    "Warrant, model version and mathematics, the specification source, the code "
                    "artifact and its report, the dials, the leakage certificate, the training "
                    "frame, the feature-set pin's manifest and its member pins, the Python "
                    "version and the resolved backends.",
                ),
                (
                    "The definition of the hash",
                    "MAYA's own canonical encoder and fragment chunker ship inside the bundle, "
                    "because they are the definition of the hash rather than a description of "
                    "it.",
                ),
                (
                    "A signed manifest",
                    "Every file's digest, the data's content hash, the expected output hash, and "
                    "whether re-execution is possible — with the reason when it is not.",
                ),
            ],
        },
        "right": {
            "head": "What the verifier does",
            "items": [
                ("Needs Python, pyarrow and numpy", "Nothing from MAYA, and no network."),
                (
                    "Bounds the archive first",
                    "Entry count, expanded size, compression ratio and path traversal, before a "
                    "byte is read.",
                ),
                (
                    "Recomputes, then re-executes",
                    "Every file digest, the signature, the data's content hash using the "
                    "shipped encoder, and the model's outputs against the expected hash.",
                ),
                (
                    "Refuses on one changed byte",
                    "A tampered bundle is refused before anything is served, not partly served.",
                ),
            ],
        },
        "note": "maya/services/bundle.py, sdk/maya/sdk/offline.py; "
        "tests/test_sdk_modes.py::test_a_tampered_bundle_is_refused_before_anything_is_read and "
        "tests/test_sc2_aged_warrant.py, which reproduces a warrant aged two years in the "
        "fixture.",
    },
    {
        "kind": "divider",
        "num": "4",
        "title": "Governance a model risk function works in",
        "sub": "Version 1.0.0 adds the layer a model risk function spends its days in. Nothing in it is "
        "a new form: every screen reads the warrants, pins, scores and reports the lifecycle "
        "already produced.",
        "points": [
            "Findings, tracked to independent closure",
            "Materiality, derived",
            "Periodic review, with teeth",
            "Monitoring dashboards",
            "Champion and challenger",
            "Fairness and explainability",
            "The supervisory inventory",
        ],
    },
    {
        "kind": "split",
        "kicker": "Findings",
        "title": "A defect has an owner, a due date — and an independent closer",
        "intro": "A validator finds something wrong; the owner fixes it; somebody who did not make the "
        "fix confirms it, or the risk is accepted in writing. Every move is kept on the finding "
        "and in the audit chain.",
        "left": {
            "head": "The lifecycle",
            "items": [
                (
                    "Raised",
                    "With a severity; the owner defaults to the model's, the due date to the "
                    "severity's window: 30, 90, 180 or 365 days.",
                ),
                ("Remediated", "By the owner, often as a new model version."),
                ("Closed", "Only by someone who did not remediate it — or sent back as not fixed."),
                (
                    "Accepted",
                    "The risk kept rather than fixed: a written reason, never the model owner's "
                    "call.",
                ),
            ],
        },
        "right": {
            "head": "In a case study",
            "items": [
                (
                    "Study 09",
                    "Version 1 of the Basel formula misses the maturity floor and cap: a high "
                    "finding, fixed as version 2, the owner refused when she tries to close her "
                    "own fix.",
                ),
                (
                    "Study 45",
                    "A unisex mortality table's bias by sex: a finding accepted by a manager, "
                    "citing the ruling that forbids pricing by sex.",
                ),
            ],
        },
    },
    {
        "kind": "table",
        "kicker": "Materiality",
        "title": "A tier derived from evidence, then from the firm's own questionnaire",
        "intro": "Tier 1 is the most material. The tier is the highest driver's score — one tier higher "
        "for a black box — and every driver is shown beside it. An override needs a reason, and "
        "one that lowers materiality is flagged.",
        "rows": [
            ["Driver", "Where it comes from", "Scores"],
            [
                "Use",
                "Declared by the owner: regulatory, financial reporting, business decision, internal",
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
                "The firm's file, config/tiering.yaml: automation, customer impact, reporting, "
                "complexity",
                "The highest answer, or points against thresholds",
            ],
        ],
    },
    {
        "kind": "flow",
        "kicker": "Periodic review",
        "title": "An overdue review stops the model running",
        "steps": [
            ("Tier sets the interval", "One, two or three years, or per model"),
            ("Due date", "From the last review, or the first approval"),
            ("The sweep", "Hourly: an overdue model's live warrants are suspended"),
            ("The review", "Recorded by someone other than the owner"),
            ("Lifted", "Exactly the suspensions the sweep made, and no others"),
        ],
        "box_h": 1.9,
        "items": [
            "Suspension is the same mechanism a covenant breach uses, so a production service "
            "asking for its bundle is refused and told whom to contact. A review is not a reminder "
            "in someone's calendar; it is a condition of running.",
            "A warrant suspended for a breach stays suspended when a review is recorded: lifting "
            "one kind of suspension never lifts another.",
        ],
    },
    {
        "kind": "split",
        "kicker": "Ongoing monitoring",
        "title": "Every live model graded ok, watch or breach",
        "intro": "Each attested run reports its row count and per-input statistics. The dashboards read "
        "those reports as series, and grade every sealed warrant.",
        "left": {
            "head": "The grades",
            "items": [
                ("Breach", "Suspended, or a covenant broken in the last seven days."),
                (
                    "Watch",
                    "A population stability index between 0.10 and the covenant; a null rate at "
                    "least double its median; a live model silent for thirty days.",
                ),
                ("Ok", "None of those."),
            ],
        },
        "right": {
            "head": "Per warrant",
            "items": [
                ("Volume", "Rows and runs per day."),
                (
                    "Per input and output",
                    "PSI against the baseline the covenant was drawn with, null rate, mean — "
                    "covenant bounds drawn as lines, breaches marked on the time axis.",
                ),
                (
                    "Study 19",
                    "A bureau score goes ok, watch, breach over three months as utilisation "
                    "drifts: PSI 0.009, 0.109, 0.438.",
                ),
            ],
        },
    },
    {
        "kind": "split",
        "kicker": "Champion and challenger",
        "title": "Replacing a model on evidence, not on two numbers",
        "intro": "Two warrants drawn on the same pin with the same seed hold the same escrowed rows. "
        "MAYA scores both, keeps the per-row errors to itself, and compares them row by row.",
        "left": {
            "head": "What is reported",
            "items": [
                ("The difference", "In RMSE or MAE, challenger minus champion."),
                (
                    "A paired bootstrap interval",
                    "95%, 2,000 draws, a fixed seed: the same challenge gives the same interval "
                    "anywhere.",
                ),
                ("The verdict", "Challenger better only if the whole interval is below zero."),
            ],
        },
        "right": {
            "head": "What is refused",
            "items": [
                (
                    "Different holdouts",
                    "Warrants whose holdout hashes differ are not compared at all.",
                ),
                (
                    "The author deciding",
                    "Whoever owns the challenger does not decide whether it replaces the champion.",
                ),
                (
                    "Study 42",
                    "A log-log demand model beats the linear champion: −0.031, interval "
                    "[−0.040, −0.022], winning only 60% of rows.",
                ),
            ],
        },
    },
    {
        "kind": "split",
        "kicker": "Fairness and explainability",
        "title": "Error by segment, and what the model leans on",
        "intro": "Computed on the escrowed holdout, so each run counts as a holdout attempt; only "
        "aggregates are kept.",
        "left": {
            "head": "By segment",
            "items": [
                (
                    "Per segment",
                    "RMSE, MAE, bias and mean prediction for each value of a column you name.",
                ),
                ("Flagged", "MAE more than a quarter above the overall figure."),
                (
                    "Systematic",
                    "Bias more than half the MAE: wrong mostly in one direction, which equal "
                    "MAEs hide.",
                ),
                (
                    "Suppressed",
                    "A segment under twenty rows gets no figures: a mean over three rows is "
                    "three rows.",
                ),
            ],
        },
        "right": {
            "head": "What drives it",
            "items": [
                (
                    "Permutation importance",
                    "Each input shuffled, seeded and repeated; the rise in error is its "
                    "importance.",
                ),
                (
                    "Black boxes too",
                    "It needs only predictions, so a black box is measured through the sandbox.",
                ),
                (
                    "Study 45",
                    "Men's and women's errors are the same size — MAE ratio 1.08 — and in "
                    "opposite directions: both segments systematic.",
                ),
            ],
        },
    },
    {
        "kind": "table",
        "kicker": "The supervisory inventory",
        "title": "One row per model, in the layout the supervisor asks for",
        "intro": "Exported as Excel, CSV or JSON in an SR 11-7 or SS1/23 layout, built from the records "
        "MAYA keeps, so it cannot drift from them. The file says how many models the exporter "
        "could not see.",
        "rows": [
            ["Column group", "What it holds"],
            ["Identity", "Purpose, use, type, vendor or provider, owner"],
            ["Materiality", "Tier, derived tier, its basis, any override and its reason, exposure"],
            [
                "Approval and evidence",
                "Status, approval, and what shows the implementation computes the model",
            ],
            [
                "Review and findings",
                "Last review and outcome, next due, open, overdue and accepted findings",
            ],
            [
                "Use",
                "Live warrants, environments, executions, monitoring grade, restrictions on use",
            ],
        ],
    },
    {
        "kind": "divider",
        "num": "5",
        "title": "Beyond formulas",
        "sub": "Most of what a bank now runs is not a formula anyone can read: bought scores, networks, "
        "and applications built on a large language model. Each gets the same chain, and each "
        "forfeits exactly the evidence it cannot give — and no more.",
        "points": [
            "Black boxes, scored blind",
            "Models from MLflow and SageMaker",
            "Beside your ML platform",
            "LLM applications",
            "Evaluation sets and guardrails",
        ],
    },
    {
        "kind": "flow",
        "kicker": "Black boxes",
        "title": "A model nobody can read, run where nobody can see the data",
        "steps": [
            ("Declared", "A black box states what it estimates and how it is built"),
            ("Validated", "Its code through six rungs, run twice in the sandbox"),
            ("Scored blind", "The code, in the sandbox, on the holdout's inputs only"),
            ("Metrics out", "MAYA computes them; rows never leave"),
        ],
        "box_h": 1.9,
        "items": [
            "MAYA cannot evaluate a model it cannot read, but it can run one it has validated. The "
            "target never enters the sandbox; the sandbox has no network and no view of storage; "
            "the score records the artifact's hash and the sandbox tier.",
            "A black box with no validated artifact is refused by name, and one that reads the "
            "target as an input is refused rather than handed the answer.",
        ],
    },
    {
        "kind": "split",
        "kicker": "Is the code the mathematics?",
        "title": "Differential testing, and what a black box forfeits",
        "intro": "The model has two descriptions: the tree MAYA holds, and the Python somebody uploaded. "
        "Nothing guarantees they agree, so MAYA compares them on numbers rather than asking "
        "anybody to assert it.",
        "left": {
            "head": "Conformance testing",
            "items": [
                (
                    "The comparison",
                    "The uploaded code is run against MAYA's own evaluation of the documented "
                    "mathematics on sampled inputs, to a relative tolerance of 1e-9.",
                ),
                (
                    "Counterexamples, not a verdict",
                    "Up to ten disagreeing rows with the expected and the actual value, so the "
                    "argument is about numbers.",
                ),
                (
                    "Tied to the exact artifact",
                    "A version with code cannot advance until conformance has run against that "
                    "artifact hash and agreed everywhere sampled.",
                ),
                (
                    "Honest about itself, in its first four words",
                    "Sampled agreement is not proof, and MAYA cannot know whether a feature set "
                    "is representative. An undeclared dial is placed off-centre inside its "
                    "bounds so a comparison cannot miss a bug by landing on a round number.",
                ),
            ],
        },
        "right": {
            "head": "Declared black boxes",
            "items": [
                (
                    "Registered, not excluded",
                    "With the estimate and the architecture declared, the input contract "
                    "enforced, and warrants that behave exactly as they do for anything else.",
                ),
                (
                    "Conformance is skipped and says so",
                    "There is no documented closed form to test against, and the report states "
                    "that rather than passing quietly.",
                ),
                (
                    "Blind scoring is refused by name",
                    "Scoring evaluates the mathematics in process and never runs the uploaded "
                    "artifact, so for a declared black box there is nothing to score.",
                ),
                (
                    "Covenants become the control",
                    "For an opaque model they are the only one available, which is exactly "
                    "where Part 6 said the review effort belongs.",
                ),
            ],
        },
        "note": "maya/formula/conformance.py and maya/services/models.py; ADR-007. Part 8 carries two "
        "studies through on these terms: a card-fraud network as a declared black box, and a "
        "yield curve whose planted bug only conformance testing can see.",
    },
    {
        "kind": "table",
        "kicker": "Connectors",
        "title": "Models trained elsewhere come in; lineage goes out",
        "intro": "Tested against the documents each system publishes and a recorded HTTP exchange — not "
        "yet against a live service, which the documentation says.",
        "rows": [
            ["System", "What MAYA does", "What it insists on"],
            [
                "MLflow",
                "Imports a model from its MLmodel file, or fetches it from the configured tracking "
                "server",
                "A signature: the input contract is the vendor's, never a guess",
            ],
            [
                "Amazon SageMaker",
                "Imports a model package from its description: image, data, framework, approval",
                "Inputs named, since SageMaker records none",
            ],
            [
                "OpenLineage",
                "Every lineage edge as a RunEvent, downloaded or posted to Marquez or any consumer",
                "Administrators only",
            ],
            [
                "Snowflake, Databricks",
                "Read-only SQL sources through their SQLAlchemy dialects",
                "A named read-only role; SELECT only",
            ],
        ],
    },
    {
        "kind": "table",
        "kicker": "Beside your ML platform",
        "title": "The licence reaches the platform that trains and serves",
        "intro": "MAYA trains and serves nothing itself. It licenses what your platform does, and "
        "keeps the evidence of each step.",
        "rows": [
            ["Step", "What MAYA does", "What it never does"],
            [
                "Registry",
                "Sets an MLflow alias on a version while its execution warrant is live, removes it "
                "when not",
                "Deploy: the alias is what your deployment follows",
            ],
            [
                "Scoring call",
                "An SDK guard checks the warrant before each call and reports the run after it",
                "Sit in the request path of your service",
            ],
            [
                "Training",
                "Turns a training warrant into a signed Kubernetes or SageMaker job with a one-day key",
                "Run the job: it goes to your compute",
            ],
            [
                "A second fit",
                "Fits a closed-form model itself on the training rows and compares, as evidence",
                "Supply the parameters it checks",
            ],
            [
                "Batch scoring",
                "Scores a pinned table under a live warrant: output sealed by hash, run reported, custody "
                "updated",
                "Serve online",
            ],
        ],
    },
    {
        "kind": "split",
        "kicker": "LLM applications",
        "title": "A prompt is a model's parameters, so it is versioned like them",
        "intro": "MAYA cannot read the weights, so it governs what can be pinned down — and approves "
        "only on evidence gathered on exactly that definition.",
        "left": {
            "head": "What a version seals",
            "items": [
                (
                    "Provider and model",
                    "OpenAI, Azure, Bedrock, Vertex, a self-hosted model, or any other.",
                ),
                (
                    "System prompt and template",
                    "The template's placeholders filled from each evaluation case.",
                ),
                (
                    "Parameters and guardrails",
                    "Temperature and limits; blocked terms, a length cap, personal data.",
                ),
                (
                    "One definition hash",
                    "Change anything and it is a new definition, judged again.",
                ),
            ],
        },
        "right": {
            "head": "How it is approved",
            "items": [
                ("A run on this definition", "Against the evaluation set as it now stands."),
                ("Clean", "Meeting the pass rate, with no guardrail violation."),
                ("Independent", "A model manager who neither owns nor submitted it."),
                (
                    "Study 49",
                    "Version 1 gets every category right and still fails: it read a customer's "
                    "card number back.",
                ),
            ],
        },
    },
    {
        "kind": "table",
        "kicker": "Evaluation",
        "title": "Deterministic checks, because a judgement MAYA cannot reproduce is not evidence",
        "intro": "No model grades another model. Runs are recorded — answers produced wherever the "
        "application runs — or live, where MAYA calls the provider itself.",
        "rows": [
            ["Check or guardrail", "Passes when"],
            [
                "contains · not_contains · equals",
                "The answer does, or does not, contain the value; or equals the reference",
            ],
            ["regex · max_chars", "The pattern matches; the answer is short enough"],
            ["json", "The answer parses, with the required keys"],
            ["Blocked terms", "None of the version's forbidden phrases appears"],
            ["Personal data", "No e-mail address, Luhn-valid card number or phone number"],
        ],
    },
]
