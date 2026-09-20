"""
The executive briefing: what MAYA is, what a firm gets from it, what has been
measured, and what it does not do — for a reader deciding whether to adopt it.

Every figure is taken from the code, ``maya/core/version.py``, the README's
"What's shipped" and docs/BENCHMARKS.md, and each slide's note names its source.
Nothing here is a projection: where something is not measured or not built, the
slide says so.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""

from __future__ import annotations

from maya.core.version import VERSION

CHAPTER = "MAYA · Executive Briefing"
TITLE = "MAYA — Executive Briefing"
SUBJECT = "What MAYA is, what a firm gets from it, and what it does not do"

SLIDES = [
    {
        "kind": "title",
        "kicker": "MODEL RISK  ·  REPRODUCIBILITY  ·  EXECUTIVE BRIEFING",
        "title": ["Any number a model produced,", "rebuilt exactly, years later"],
        "sub": "MAYA — Model & AI Lifecycle Assurance.  Evidence, not assertion.",
        "agenda": [
            "What MAYA is, and the four failures it removes",
            "The spine, and the warrant that runs down it",
            "What this version delivers, and what it was exercised on",
            "What has been measured, and what fell short",
            "What MAYA does not do",
        ],
    },
    {
        "kind": "bullets",
        "kicker": "What MAYA is",
        "title": "One system of record for the whole chain behind a model's number",
        "intro": "MAYA holds the features, feature sets, models and warrants of a quantitative "
        "shop in one place: definition, data, documentation, approval and evidence.",
        "items": [
            (
                "Definitions are code; data is a consequence",
                "MAYA stores how a number is produced and materialises values only when asked. "
                "A version freezes how; a pin freezes what — the same bytes forever, verified "
                "against a content hash.",
            ),
            (
                "A model is mathematics, code, parameters and a document, versioned together",
                "The formula is a typed expression tree, so MAYA type-checks the inputs, renders "
                "the specification document from it, and tells a reviewer what changed "
                "mathematically between two versions.",
            ),
            (
                "A warrant binds model, data and parameters into one object",
                "Who was allowed to run what, on which data, with whose approval becomes a query "
                "instead of an archaeology project.",
            ),
            (
                "It does not train models and does not serve predictions",
                "Training runs on the firm's own compute. MAYA issues the licence, scores the "
                "escrowed holdout, and keeps the evidence.",
            ),
        ],
        "note": "Specification §1–§2 and README, “What makes it different”. The specification is the authority; this deck describes the code built from it.",
    },
    {
        "kind": "cards",
        "kicker": "The problem",
        "title": "Four failures found in almost every quantitative shop",
        "cols": 2,
        "cards": [
            (
                "1",
                "Feature logic lives in notebooks and SQL snippets",
                "Two desks compute “adjusted close” differently and neither is wrong. MAYA holds "
                "one versioned, approved definition and an algebra for building on it.",
            ),
            (
                "2",
                "Training data is a file on a share drive",
                "When a result is challenged nobody can produce the exact rows. A MAYA pin is "
                "immutable and content-addressed, and the warrant records the checksum that was "
                "downloaded.",
            ),
            (
                "3",
                "Mathematics, code and parameters drift apart",
                "A PDF, a repository and a spreadsheet, each a little out of date. MAYA versions "
                "the formula, the artifact, the parameter sets and the document against each "
                "other.",
            ),
            (
                "4",
                "Nothing binds model, data and parameters",
                "The warrant does: one auditable, transferable object — sealed, expiring, and "
                "revocable the day the model is found to be wrong.",
            ),
        ],
        "note": "Specification §1. Each of the four is a reproducibility failure waiting to be found by somebody who is not on your side.",
    },
    {
        "kind": "flow",
        "kicker": "The spine",
        "title": "One path, and every surface walks the whole of it",
        "steps": [
            ("Source", "Files, a read-only SQL query, a reviewed Python producer, or derived"),
            ("Feature", "A governed bitemporal dataset; pinned into the lake"),
            ("Feature set", "Attributes mapped from members onto one grid, pinned as a whole"),
            ("Model", "Formula, code, parameters and a specification document"),
            ("Warrants", "Training, then an approved parameter set, then execution"),
            ("Bundle", "Signed; verifies and re-executes on a machine with no MAYA"),
        ],
        "box_h": 1.95,
        "items": [
            "The same spine runs through the web UI, the REST API, the Python SDK and the command line — and the UI is itself an SDK client, with no private path of its own.",
            "Features and feature sets are closed under their operators, so a derived object re-enters the flow as an ordinary object: named, versioned, pinnable, permissioned, visible in lineage.",
            "A composite model is an ordinary model: one warrant over one feature set, however many members it has.",
        ],
        "note": "README, “The shape of the thing”. The UI boundary is held by a gate, not by review (tests/test_web.py::test_web_imports_only_the_sdk).",
    },
    {
        "kind": "flow",
        "kicker": "The distinguishing primitive",
        "title": "The warrant: a licence to compute, not a document about one",
        "steps": [
            (
                "Training warrant",
                "Drawn against a pinned feature set once the input contract is satisfied and a "
                "signed leakage certificate is issued.",
            ),
            (
                "Offline training",
                "The team downloads train and validation only, with a checksum, and fits on its "
                "own compute.",
            ),
            (
                "Parameter set",
                "Uploaded against that checksum. Data that does not match is flagged and cannot "
                "be approved quietly.",
            ),
            (
                "Execution warrant",
                "Model, parameters and contract as a live licence: it expires, it is revoked, and "
                "a breached covenant suspends it.",
            ),
            (
                "Bundle",
                "A signed archive that verifies offline, re-executes the model, and refuses on one "
                "changed byte.",
            ),
        ],
        "box_h": 2.2,
        "items": [
            "A revoked, expired or suspended warrant fails every consuming call closed, naming the covenant that broke or the person to contact.",
            "The test partition is escrowed: MAYA scores uploaded parameters against it and returns metrics only, and every attempt is numbered on the warrant, because twenty attempts against a holdout is a fact a reviewer should be able to see.",
            "Proved end to end by tests/test_warrants.py (the checksum cycle, the leakage certificate, the counted scoring attempt) and tests/test_security_regressions.py::test_each_covenant.",
        ],
        "note": "Specification §29.4 and §29.5; ADR-007 states the one runtime exception MAYA concedes and no more.",
    },
    {
        "kind": "table",
        "kicker": "Why not buy it",
        "title": "What each adjacent category does well, and where it stops",
        "rows": [
            ["Category", "Good at", "Where it stops"],
            [
                "Feature stores",
                "Point-in-time joins, online serving, streaming, scale",
                "No approval workflow, no model side, no immutable snapshot an auditor can hold",
            ],
            [
                "Lakehouse versioning",
                "Branch, tag and time travel over data",
                "Versions bytes, not meaning: no owner, no approval, no linkage to a model",
            ],
            [
                "ML registries",
                "Run tracking, artifact lineage, metrics",
                "A run records what happened; it is not a licence for what may happen next",
            ],
            [
                "Catalogs and lineage",
                "Discovery, ownership, column lineage",
                "Observe pipelines rather than gate them, and hold no data of their own",
            ],
            [
                "Model-risk tools",
                "Inventory, validation workflow, regulator-shaped reporting",
                "Store a document saying a model was validated, not the artefacts that let you re-run it",
            ],
        ],
        "col_w": [2.3, 4.2, 5.2],
        "note": "Specification §27, which names the products in each category. MAYA's position is the seam between them: hash-verified pinned data, an algebra over definitions, model mathematics as data, and a transferable licence to compute.",
    },
    {
        "kind": "stats",
        "kicker": "Status",
        "title": f"Version {VERSION}, built from specification revision 2.3",
        "stats": [
            (VERSION, "released 19 September 2026, from specification revision 2.3"),
            ("1,684", "tests on Linux; 1,674 pass on SQLite and 10 are opt-in"),
            ("215", "endpoints, each with an SDK method, checked both ways by a gate"),
            ("92.9%", "line coverage, against a 90% floor in the gate ladder"),
        ],
        "items": [
            "The whole spine runs through all four surfaces: source, feature, feature set, pin, model, training warrant, parameter set, execution warrant, reproducibility bundle.",
            "The suite has run green on PostgreSQL 16, 17 and 18 as well as SQLite, and passed with every optional accelerator replaced by its pure-Python fallback.",
            "It includes real-browser tests in headless Chrome, several web processes on one node, a worker process, LibreOffice Calc as a judge of lifted spreadsheets, and a real openssl timestamp authority.",
            "Single sign-on is driven against a real identity provider, Keycloak 26.4, by opt-in tests skipped unless a URL is supplied.",
        ],
        "note": "README, “Status — read this first”, and maya/core/version.py, the only place a version string is allowed to live.",
    },
    {
        "kind": "table",
        "kicker": "What's shipped",
        "title": "Delivered by milestone, each row with the tests that prove it",
        "rows": [
            ["Milestone", "Delivered", "Proved by"],
            [
                "M0–M1",
                "The gate ladder, each gate seen to fail on a planted fault; canonical bytes and content-defined fragments; two generated schema files; a hash-chained audit; one authorization function; single sign-on, TOTP and WebAuthn",
                "test_api_and_gates.py, test_foundation.py, test_workflow_and_estate.py, test_authz_matrix.py, test_sso_mfa.py",
            ],
            [
                "M2–M3",
                "The lakehouse layer on two backends; byte-identical re-resolution; point-in-time after a restatement; resolution rules and calendars; the feature algebra; sources; catalog search",
                "test_maya_delta.py, test_features.py, test_resolution_*.py, test_properties.py, test_search.py",
            ],
            [
                "M4–M5",
                "Feature sets with policy precedence and alignment; cascade pin that rolls back entirely; materialization policies; grant conditions; workflow as data with segregation of duties; workspaces and shadow replay",
                "test_materialization.py, test_conditions.py, test_workflow_matrix.py, test_workspaces.py",
            ],
            [
                "M6–M7",
                "The formula IR with its kernel, artifact ladder and sandbox; specification documents; spreadsheets as models; warrants, covenants and signed bundles",
                "test_formula.py, test_sandbox_linux.py, test_spreadsheet.py, test_warrants.py, test_sdk_modes.py",
            ],
            [
                "M8 and §29",
                "SDK record and replay, server-side paging, several web processes, observability; the licence algebra, custody anchoring, and the assistant as a recorded challenger",
                "test_paging.py, test_web_processes.py, test_custody.py, test_assistant.py",
            ],
        ],
        "col_w": [1.3, 5.7, 4.7],
        "note": "README, “What's shipped”, which names the module and the tests for every row. A capability with no test that exercises it is not listed there, because an untested claim is an assertion.",
    },
    {
        "kind": "table",
        "kicker": "Exercised, not demonstrated",
        "title": "Nine worked models, each carried through MAYA end to end",
        "intro": "Every study defines features, pins data point-in-time, registers a model with "
        "its document, draws a warrant, approves parameters and seals an execution warrant — "
        "through the SDK, as a named user with that user's roles, so the refusals in them are real.",
        "rows": [
            ["Study", "What it is really about"],
            [
                "01  Retail credit PD scorecard",
                "A leakage certificate that refuses every row of a panel, and the written exception that lets the work proceed",
            ],
            [
                "02  Scheduled mortgage cashflow",
                "Whether the code the desk runs is the mathematics that was approved: a valid implementation with the commonest mortgage bug in it, caught",
            ],
            [
                "03  Mortgage prepayment",
                "A change proposed underneath a live model and priced before anyone approves it: 60% of the book moves",
            ],
            [
                "06  IFRS 9 expected credit loss",
                "Committee judgements as approved parameter sets, and a portfolio test that finds a 2.67× over-provision the per-account error cannot see",
            ],
            [
                "11  Nelson–Siegel yield curve",
                "A planted bug that recalibration absorbs exactly, so only a blind score against the specification can see it",
            ],
        ],
        "col_w": [2.9, 8.7],
        "note": "case_studies/ and README, “Case studies”: nine are complete of a planned fifty, every input feed synthetic and committed. Writing them has been the most productive source of platform defects so far — twelve, each fixed with a test that would fail without the fix.",
    },
    {
        "kind": "stats",
        "kicker": "Measured",
        "title": "Seven targets met on a shared workstation, one not met reliably",
        "stats": [
            ("0.98 s", "resolution p95 warm: 50 attributes × 10 years × 500 symbols"),
            ("0.18 s", "worst metadata page p95, PostgreSQL, 8 web processes"),
            ("59.7 MB/s", "pin write throughput, one worker, against a 50 MB/s target"),
            ("0.34 s", "median of three runs at 200 users, against 0.3 s"),
        ],
        "rows": [
            ["Criterion", "Target", "Result", "Verdict"],
            [
                "SC-5 resolution p95",
                "15 s warm",
                "No rules: warm 0.98 s, cold 1.0 s. Forward fill on all 50 attributes: warm 6.1 s",
                "pass",
            ],
            ["SC-4 page latency p95", "0.3 s", "0.15 s on SQLite; 0.18 s on PostgreSQL", "pass"],
            [
                "Catalog search p95",
                "0.5 s",
                "0.16 s over 100,000 objects, 800,010 index rows",
                "pass",
            ],
            [
                "§24.3 capacity, four targets",
                "see spec",
                "Pin write 59.7 MB/s; 134,962 jobs an hour; cold start 1.26 s; every page under 30 ms after seeding 20k sets, 10k models and 100k pins",
                "pass",
            ],
            [
                "SC-3, 200 users",
                "0.3 s p95",
                "Three runs: 0.34 s, 0.22 s, 0.43 s",
                "not met reliably",
            ],
        ],
        "col_w": [2.1, 1.1, 6.6, 1.5],
        "note": "docs/BENCHMARKS.md, from the unedited result files in docs/benchmarks/. One developer workstation with the database and the load generator on it, not a benchmark host.",
    },
    {
        "kind": "table",
        "kicker": "What fell short",
        "title": "SC-3: one run of three meets the target, and the median does not",
        "intro": "200 users, each with a session of their own, browsing random screens with 1–3 s "
        "of think time for 60 seconds, on PostgreSQL with 8 web processes and the two-second "
        "principal cache.",
        "rows": [
            ["Run", "Throughput", "p50", "p95", "Max", "Errors", "p95 ÷ single user"],
            ["1", "95.3 req/s", "0.056 s", "0.345 s", "1.73 s", "0", "1.97"],
            ["2", "96.6 req/s", "0.033 s", "0.215 s", "0.80 s", "0", "1.22"],
            ["3", "93.4 req/s", "0.054 s", "0.425 s", "3.37 s", "0", "2.16"],
        ],
        "col_w": [0.8, 1.9, 1.5, 1.5, 1.5, 1.2, 2.2],
        "note": "docs/BENCHMARKS.md. The configuration was identical across the three runs, so the spread is most likely the machine — but that is an inference, and only a quiet dedicated host would make it a measurement. A dedicated host is out of scope by decision, so SC-3 stands as not met reliably.",
    },
    {
        "kind": "bullets",
        "kicker": "What MAYA does not do",
        "title": "Three things that will not be done, and what each costs",
        "items": [
            (
                "The assistant's hosted provider is tested against a stub of its client only",
                "Whether the live service answers the way the stub does is unproven. The default "
                "deterministic provider, which is what ships on, is unaffected.",
            ),
            (
                "Windows and macOS are not exercised; only Linux is",
                "SC-14 — the whole suite green on all three platforms — is therefore not met, and "
                "the code paths that exist only for those two have never run. There is no hosted "
                "CI either: the gate ladder runs locally and in the pre-commit hook.",
            ),
            (
                "There is no dedicated benchmark host",
                "Every published figure comes from one shared workstation, so a verdict close to "
                "its target — SC-3 above all — is a verdict about that machine and will not be "
                "settled elsewhere.",
            ),
        ],
        "note": "README, “Out of scope by decision”. Written as decisions rather than as work in progress, because a roadmap is not a control.",
    },
    {
        "kind": "bullets",
        "kicker": "Not yet",
        "title": "Stated so that nobody has to discover it",
        "items": [
            "PostgreSQL 14 and 15 have not been run. The suite passes on 16.15, 17.11 and 18.6, and on SQLite; 14 is the documented floor.",
            "Single sign-on is proven against one real identity provider, Keycloak 26.4, over http on loopback. No commercial provider has been tried, and SAML back-channel logout is not supported, so a SAML provider that signs someone out without their browser does not reach MAYA.",
            "The strong sandbox tier is Linux-only; elsewhere MAYA declares a weaker tier and records it on every artifact validated under it.",
            "True specification PDFs need Tectonic installed on each server; without it MAYA renders a watermarked draft and forbids approval on one outside dev.",
            "Resolution, search and the capacity targets were measured on SQLite only; nothing in §24.3 has been run on PostgreSQL, and the per-pod figure has not been measured at all.",
            "Spreadsheet import is v1 scope: checked against LibreOffice Calc's own results, not against workbooks saved by Microsoft Excel.",
            "A custody anchor is only as external as the file it is written to; point it at off-host or write-once storage.",
            "SC-9 — a new designer publishing a first model inside an hour — has not been timed with a real person, no external security review has been done, and the restore drill has been performed on a small estate only.",
        ],
        "note": "README, “Not yet — stated so nobody has to discover it”, and the specification audit at docs/audit/, which reads the specification against the code requirement by requirement and ranks the gaps.",
    },
    {
        "kind": "split",
        "kicker": "Deliberate non-goals",
        "title": "Where MAYA chooses to lose, and the risks it accepts",
        "left": {
            "head": "Beaten on, by design",
            "items": [
                "Online serving latency",
                "Streaming freshness",
                "Raw scale",
                "Connector breadth",
                "Out-of-the-box regulatory report templates",
                (
                    "Where sub-10 ms serving is needed",
                    "MAYA governs the definition and a serving layer consumes a sealed execution "
                    "warrant. It does not grow a serving tier.",
                ),
            ],
        },
        "right": {
            "head": "Accepted risks, mitigated not removed",
            "items": [
                (
                    "Two-store consistency on pin",
                    "A saga and a reaper make a half-written pin invisible, not impossible.",
                ),
                (
                    "Python's concurrency ceiling",
                    "Several web processes over PostgreSQL; still the SC-3 shortfall.",
                ),
                (
                    "Execution outside MAYA",
                    "Some lineage escapes. The warrant narrows the gap; nothing closes it.",
                ),
                (
                    "A catalog nobody seeds",
                    "The platform cannot create its own critical mass of curated features.",
                ),
            ],
        },
        "note": "Specification §2, §27.4 and §28.11, and README, “Deliberate non-goals”. A design without stated losses is a sales pitch.",
    },
    {
        "kind": "cards",
        "kicker": "Security posture",
        "title": "Specified before it was built, which is the only order that works",
        "cols": 3,
        "cards": [
            (
                "",
                "No silent defaults",
                "Where a setting materially changes behaviour there is no default outside dev; "
                "MAYA fails at startup naming it.",
            ),
            (
                "",
                "No secret in a tracked file",
                "The tracked configuration carries none, and a gate checks that it still does not.",
            ),
            (
                "",
                "The default admin password is a speed bump",
                "MAYA refuses to start with it outside dev unless that is explicitly allowed.",
            ),
            (
                "",
                "User Python is hostile until proved otherwise",
                "Static validation, an import allowlist, a sandboxed subprocess with no network, "
                "resource caps, and a determinism probe.",
            ),
            (
                "",
                "The sandbox tier is declared, not assumed",
                "Claimed only when a probe child fails to escape; named on the health page and "
                "recorded on every artifact.",
            ),
            (
                "",
                "An audit log nobody can edit",
                "Append-only and hash-chained, with the chain head signed and anchored outside "
                "the database.",
            ),
        ],
        "note": "README, “Security posture”, and specification §12 and §21; tests/test_foundation.py, tests/test_api_contract.py, tests/test_sandbox_linux.py, tests/test_custody.py.",
    },
    {
        "kind": "table",
        "kicker": "Model risk",
        "title": "MAYA holds the evidence; the firm's policy decides what is enough",
        "rows": [
            ["What a supervisor expects", "What MAYA holds"],
            [
                "Inventory",
                "A queryable register of models, versions, owners, maturity and dependencies, with lineage in both directions",
            ],
            [
                "Documentation",
                "A LaTeX specification per model version, its formula blocks rendered from the same tree the code is checked against; submission is blocked while a required section is empty",
            ],
            [
                "Independent review",
                "Segregation of duties enforced by the workflow engine, not by etiquette; review comments and decisions on the record",
            ],
            [
                "Reproducibility",
                "Pins and warrants, and a signed bundle that verifies and re-executes on a machine with no MAYA installed",
            ],
            [
                "Change control",
                "Every version change classified breaking, behavioral or additive, with its measured impact shown to the approver before they decide",
            ],
            [
                "Effective challenge",
                "A recorded challenger's memo on every review: it never approves and never blocks, and the reviewer records whether they agreed",
            ],
        ],
        "col_w": [2.6, 9.1],
        "note": "Specification §21.3, mapped there onto SR 26-2 and its non-US equivalents. This is an engineering description, not legal, regulatory or financial advice (NOTICE §4).",
    },
    {
        "kind": "bullets",
        "kicker": "What adoption takes",
        "title": "Two questions the software cannot answer for you",
        "items": [
            (
                "Which separation-of-duties preset the first namespaces get",
                "Small team, standard or regulated — all three ship, and strictness is a namespace "
                "setting stated on every review screen. It is a policy decision, made once, "
                "visibly.",
            ),
            (
                "Who seeds the first two namespaces",
                "A catalog nobody seeds is an empty shop, and the platform cannot create its own "
                "critical mass of curated features. This is a sponsorship question, not an "
                "engineering one.",
            ),
            (
                "And the first five minutes, which the software does answer",
                "A personal scratch namespace with no ceremony: one command makes a typed, "
                "resolvable feature from a CSV. Ceremony scales with consequence, and the "
                "platform loses if it is more trouble than a notebook.",
            ),
        ],
        "note": "Specification §26.3 and §28.1; tests/test_features.py::test_scratch_quick_feature_has_zero_ceremony and tests/test_cli.py::test_quick_upload_and_restatement.",
    },
    {
        "kind": "bullets",
        "kicker": "In one slide",
        "title": "Evidence, not assertion",
        "items": [
            "One place that answers what the firm runs, who approved it and what it was fitted on — and lets that answer be checked rather than asserted.",
            "A warrant is a live licence, not a certificate: it expires, it is revoked, and it suspends itself when a covenant is breached.",
            "A bundle leaves the building and still proves itself: every hash recomputed and the model re-executed, on a machine that has never heard of MAYA.",
            "Nine worked models have been carried through the platform end to end, and found twelve defects in it, each fixed with a test.",
            "Seven performance targets pass on one workstation; SC-3 does not pass reliably, and this deck says so rather than rounding it.",
            "What is out of scope, and what is not yet done, is written down before anyone has to discover it.",
        ],
        "note": "Specification: docs/MAYA_Requirements_and_Design.md · Plan: docs/IMPLEMENTATION_PLAN.md · Measurements: docs/BENCHMARKS.md · Worked models: case_studies/",
    },
]
